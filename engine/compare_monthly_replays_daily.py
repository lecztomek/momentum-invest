from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd


CASH_NAMES = {"_CASH", "CASH", "cash", "Cash"}


# =========================
# HELPERS
# =========================

def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().replace("\ufeff", "") for c in df.columns]
    return df


def find_date_column(df: pd.DataFrame) -> str:
    for col in df.columns:
        if str(col).lower() == "date":
            return col

    raise ValueError(
        "Nie znaleziono kolumny date/DATE. "
        f"Pierwsze kolumny: {list(df.columns)[:15]}"
    )


def parse_weights(raw: str) -> Dict[str, float]:
    if pd.isna(raw):
        return {}

    data = json.loads(raw)

    out: Dict[str, float] = {}

    for ticker, weight in data.items():
        out[str(ticker).strip()] = float(weight)

    return out


def first_trading_day_on_or_after(
    index: pd.DatetimeIndex,
    date: pd.Timestamp,
) -> pd.Timestamp | None:
    pos = index.searchsorted(date, side="left")

    if pos >= len(index):
        return None

    return index[pos]


def calc_cagr(start_equity: float, end_equity: float, start_date: pd.Timestamp, end_date: pd.Timestamp) -> float:
    days = (end_date - start_date).days

    if days <= 0:
        return np.nan

    years = days / 365.25

    if start_equity <= 0 or end_equity <= 0:
        return np.nan

    return (end_equity / start_equity) ** (1.0 / years) - 1.0


def calc_drawdown(equity: pd.Series) -> pd.Series:
    peak = equity.cummax()
    return equity / peak - 1.0


def normalize_ticker(ticker: str) -> str:
    return str(ticker).strip().lower()


# =========================
# LOADERS
# =========================

def load_daily_close(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = clean_columns(df)

    date_col = find_date_column(df)
    df = df.rename(columns={date_col: "date"})

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    df = df.set_index("date")

    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.sort_index()


def load_monthly_replay(path: Path, label: str | None = None) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = clean_columns(df)

    date_col = find_date_column(df)
    df = df.rename(columns={date_col: "date"})

    required = {"date", "weights_used_json"}
    missing = required - set(df.columns)

    if missing:
        raise ValueError(f"{path}: brakuje kolumn: {missing}")

    df["date"] = pd.to_datetime(df["date"])

    if label is not None:
        df["strategy"] = label
    elif "strategy" not in df.columns:
        df["strategy"] = path.stem

    df["source_file"] = path.name

    return df.sort_values(["strategy", "date"]).reset_index(drop=True)


def parse_replay_arg(raw: str) -> Tuple[str, Path]:
    """
    Obsługuje:
        A=path.csv
        B=path.csv
        COMBINED=path.csv

    Jeśli nie dasz etykiety, etykietą będzie stem pliku.
    """
    if "=" in raw:
        label, path = raw.split("=", 1)
        label = label.strip()
        path = path.strip()

        if not label:
            raise ValueError(f"Pusta etykieta w argumencie: {raw}")

        return label, Path(path)

    path = Path(raw)
    return path.stem, path


# =========================
# DAILY EQUITY STRATEGY
# =========================

def infer_initial_equity(group: pd.DataFrame) -> float:
    """
    Jeśli replay ma:
        source_combined_equity
        source_combined_return

    to odtwarzamy equity startowe jako:
        equity_start = equity_after_first_period / (1 + first_period_return)

    Jeśli kolumn nie ma, startujemy od 1.0.
    """
    if "source_combined_equity" not in group.columns:
        return 1.0

    if "source_combined_return" not in group.columns:
        return 1.0

    first = group.iloc[0]

    equity_after = pd.to_numeric(first["source_combined_equity"], errors="coerce")
    period_return = pd.to_numeric(first["source_combined_return"], errors="coerce")

    if pd.isna(equity_after) or pd.isna(period_return):
        return 1.0

    if abs(1.0 + float(period_return)) < 1e-12:
        return 1.0

    return float(equity_after) / (1.0 + float(period_return))


def weighted_daily_return(
    daily_return_row: pd.Series,
    weights: Dict[str, float],
    column_map: Dict[str, str],
) -> Tuple[float, List[str]]:
    port_ret = 0.0
    missing: List[str] = []

    for ticker, weight in weights.items():
        if ticker in CASH_NAMES:
            continue

        key = normalize_ticker(ticker)
        col = column_map.get(key)

        if col is None:
            missing.append(ticker)
            continue

        r = daily_return_row.get(col, np.nan)

        if pd.isna(r):
            r = 0.0

        port_ret += float(weight) * float(r)

    return port_ret, missing


def build_daily_equity_for_strategy(
    group: pd.DataFrame,
    daily_close: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame, List[str]]:
    strategy = str(group["strategy"].iloc[0])

    prices = daily_close.copy().ffill()

    daily_returns = prices.pct_change()
    daily_returns = daily_returns.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    column_map = {normalize_ticker(c): str(c) for c in daily_returns.columns}

    nominal_dates = list(pd.to_datetime(group["date"]))

    rebalance_dates: List[pd.Timestamp | None] = [
        first_trading_day_on_or_after(daily_returns.index, pd.Timestamp(d))
        for d in nominal_dates
    ]

    if len(group) < 2:
        raise ValueError(f"{strategy}: potrzeba co najmniej 2 miesięcznych wierszy.")

    first_rebalance = rebalance_dates[0]

    if first_rebalance is None:
        raise ValueError(f"{strategy}: brak dziennej daty startowej.")

    equity = infer_initial_equity(group)

    daily_rows: List[Dict[str, Any]] = []
    period_rows: List[Dict[str, Any]] = []
    warnings: List[str] = []

    daily_rows.append({
        "date": first_rebalance,
        "strategy": strategy,
        "equity_daily": equity,
        "portfolio_daily_return": 0.0,
        "period_start": nominal_dates[0],
        "period_end": pd.NaT,
        "rebalance_date": first_rebalance,
        "next_rebalance_date": pd.NaT,
    })

    for i in range(len(group) - 1):
        row = group.iloc[i]

        nominal_start = pd.Timestamp(nominal_dates[i])
        nominal_end = pd.Timestamp(nominal_dates[i + 1])

        start_rebalance = rebalance_dates[i]
        end_rebalance = rebalance_dates[i + 1]

        if start_rebalance is None or end_rebalance is None:
            warnings.append(
                f"{strategy}: pominięto okres {nominal_start.date()} -> "
                f"{nominal_end.date()}, bo brakuje dziennych dat rebalancingu."
            )
            continue

        weights = parse_weights(row["weights_used_json"])

        period_equity_start = equity

        period_path = [{
            "date": start_rebalance,
            "equity_daily": equity,
        }]

        days = daily_returns.index[
            (daily_returns.index > start_rebalance)
            & (daily_returns.index <= end_rebalance)
        ]

        all_missing: set[str] = set()

        for day in days:
            port_ret, missing = weighted_daily_return(
                daily_return_row=daily_returns.loc[day],
                weights=weights,
                column_map=column_map,
            )

            all_missing.update(missing)

            equity *= 1.0 + port_ret

            daily_rows.append({
                "date": day,
                "strategy": strategy,
                "equity_daily": equity,
                "portfolio_daily_return": port_ret,
                "period_start": nominal_start,
                "period_end": nominal_end,
                "rebalance_date": start_rebalance,
                "next_rebalance_date": end_rebalance,
            })

            period_path.append({
                "date": day,
                "equity_daily": equity,
            })

        if all_missing:
            warnings.append(
                f"{strategy} {nominal_start.date()}: brak tickerów w daily_close.csv: "
                + ", ".join(sorted(all_missing))
            )

        p = pd.DataFrame(period_path)
        p["period_drawdown"] = calc_drawdown(p["equity_daily"])

        csv_equity = np.nan
        equity_diff = np.nan

        if "source_combined_equity" in group.columns:
            csv_equity = pd.to_numeric(row["source_combined_equity"], errors="coerce")

            if not pd.isna(csv_equity):
                equity_diff = equity - float(csv_equity)

        csv_return = np.nan
        daily_rebuilt_return = np.nan
        return_diff = np.nan

        if "source_combined_return" in group.columns:
            csv_return = pd.to_numeric(row["source_combined_return"], errors="coerce")

        if abs(period_equity_start) > 1e-12:
            daily_rebuilt_return = equity / period_equity_start - 1.0

        if not pd.isna(csv_return) and not pd.isna(daily_rebuilt_return):
            return_diff = daily_rebuilt_return - float(csv_return)

        period_rows.append({
            "strategy": strategy,
            "period_start": nominal_start,
            "period_end": nominal_end,
            "rebalance_date": start_rebalance,
            "next_rebalance_date": end_rebalance,
            "equity_start": period_equity_start,
            "equity_end_daily_rebuilt": equity,
            "equity_end_from_monthly_csv": csv_equity,
            "equity_diff_vs_monthly_csv": equity_diff,
            "return_daily_rebuilt": daily_rebuilt_return,
            "return_from_monthly_csv": csv_return,
            "return_diff_vs_monthly_csv": return_diff,
            "period_daily_maxdd": float(p["period_drawdown"].min()),
            "period_min_equity": float(p["equity_daily"].min()),
        })

    daily_df = pd.DataFrame(daily_rows)
    period_df = pd.DataFrame(period_rows)

    daily_df = daily_df.sort_values(["strategy", "date"]).drop_duplicates(
        subset=["strategy", "date"],
        keep="last",
    )

    daily_df["daily_peak"] = daily_df.groupby("strategy")["equity_daily"].cummax()
    daily_df["daily_drawdown"] = daily_df["equity_daily"] / daily_df["daily_peak"] - 1.0
    daily_df["maxdd_daily_to_date"] = daily_df.groupby("strategy")["daily_drawdown"].cummin()

    return daily_df, period_df, warnings


# =========================
# BENCHMARK
# =========================

def build_benchmark_for_strategy(
    strategy_daily: pd.DataFrame,
    daily_close: pd.DataFrame,
    benchmark_ticker: str,
) -> pd.DataFrame:
    column_map = {normalize_ticker(c): str(c) for c in daily_close.columns}

    key = normalize_ticker(benchmark_ticker)

    if key not in column_map:
        available = ", ".join(sorted(map(str, daily_close.columns)))
        raise ValueError(
            f"Benchmark '{benchmark_ticker}' nie istnieje w daily_close.csv.\n"
            f"Dostępne kolumny:\n{available}"
        )

    benchmark_col = column_map[key]

    strategy = str(strategy_daily["strategy"].iloc[0])
    dates = pd.to_datetime(strategy_daily["date"]).sort_values().drop_duplicates()

    b = daily_close[[benchmark_col]].copy().ffill()
    b = b.reindex(dates).ffill().dropna()

    if b.empty:
        raise ValueError(
            f"Brak danych benchmarku {benchmark_ticker} dla zakresu strategii {strategy}."
        )

    start_price = float(b[benchmark_col].iloc[0])

    if abs(start_price) < 1e-12:
        raise ValueError(f"Cena startowa benchmarku {benchmark_ticker} wynosi 0.")

    b["strategy"] = strategy
    b["benchmark_ticker"] = benchmark_ticker
    b["benchmark_price"] = b[benchmark_col]
    b["benchmark_equity"] = b["benchmark_price"] / start_price
    b["benchmark_daily_return"] = b["benchmark_equity"].pct_change().fillna(0.0)
    b["benchmark_peak"] = b["benchmark_equity"].cummax()
    b["benchmark_drawdown"] = b["benchmark_equity"] / b["benchmark_peak"] - 1.0
    b["benchmark_maxdd_to_date"] = b["benchmark_drawdown"].cummin()

    out = b.reset_index().rename(columns={"index": "date"})

    return out[[
        "date",
        "strategy",
        "benchmark_ticker",
        "benchmark_price",
        "benchmark_equity",
        "benchmark_daily_return",
        "benchmark_peak",
        "benchmark_drawdown",
        "benchmark_maxdd_to_date",
    ]]


# =========================
# SUMMARY
# =========================

def build_strategy_summary(daily_out: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []

    for strategy, group in daily_out.groupby("strategy", sort=False):
        g = group.sort_values("date").reset_index(drop=True)

        maxdd_idx = g["daily_drawdown"].idxmin()

        start_equity = float(g["equity_daily"].iloc[0])
        end_equity = float(g["equity_daily"].iloc[-1])
        start_date = pd.Timestamp(g["date"].iloc[0])
        end_date = pd.Timestamp(g["date"].iloc[-1])

        cagr = calc_cagr(start_equity, end_equity, start_date, end_date)
        maxdd = float(g["daily_drawdown"].min())

        rows.append({
            "strategy": strategy,
            "start_date": start_date,
            "end_date": end_date,
            "final_equity_daily": end_equity,
            "total_return_daily": end_equity / start_equity - 1.0,
            "cagr": cagr,
            "maxdd_daily": maxdd,
            "maxdd_daily_date": g.loc[maxdd_idx, "date"],
            "calmar_cagr_absmaxdd": cagr / abs(maxdd) if maxdd < 0 else np.nan,
            "vol_daily": float(g["portfolio_daily_return"].std()),
            "vol_annualized": float(g["portfolio_daily_return"].std() * np.sqrt(252)),
        })

    return pd.DataFrame(rows)


def add_benchmark_to_summary(
    summary: pd.DataFrame,
    benchmark_daily: pd.DataFrame,
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []

    for strategy, group in benchmark_daily.groupby("strategy", sort=False):
        g = group.sort_values("date").reset_index(drop=True)

        maxdd_idx = g["benchmark_drawdown"].idxmin()

        start_equity = float(g["benchmark_equity"].iloc[0])
        end_equity = float(g["benchmark_equity"].iloc[-1])
        start_date = pd.Timestamp(g["date"].iloc[0])
        end_date = pd.Timestamp(g["date"].iloc[-1])

        cagr = calc_cagr(start_equity, end_equity, start_date, end_date)
        maxdd = float(g["benchmark_drawdown"].min())

        rows.append({
            "strategy": strategy,
            "benchmark_ticker": g["benchmark_ticker"].iloc[0],
            "benchmark_final_equity": end_equity,
            "benchmark_total_return": end_equity / start_equity - 1.0,
            "benchmark_cagr": cagr,
            "benchmark_daily_maxdd": maxdd,
            "benchmark_maxdd_date": g.loc[maxdd_idx, "date"],
            "benchmark_calmar": cagr / abs(maxdd) if maxdd < 0 else np.nan,
        })

    bsum = pd.DataFrame(rows)

    out = summary.merge(bsum, on="strategy", how="left")

    out["relative_return_vs_benchmark"] = (
        out["final_equity_daily"] / out["benchmark_final_equity"] - 1.0
    )

    out["excess_final_equity_vs_benchmark"] = (
        out["final_equity_daily"] - out["benchmark_final_equity"]
    )

    out["maxdd_diff_vs_benchmark"] = (
        out["maxdd_daily"] - out["benchmark_daily_maxdd"]
    )

    out["cagr_diff_vs_benchmark"] = (
        out["cagr"] - out["benchmark_cagr"]
    )

    return out


# =========================
# PAIRWISE COMPARISON
# =========================

def build_pairwise_strategy_comparison(daily_out: pd.DataFrame) -> pd.DataFrame:
    d = daily_out.copy()
    d["date"] = pd.to_datetime(d["date"])

    ret_pivot = (
        d.pivot_table(
            index="date",
            columns="strategy",
            values="portfolio_daily_return",
            aggfunc="last",
        )
        .sort_index()
    )

    equity_pivot = (
        d.pivot_table(
            index="date",
            columns="strategy",
            values="equity_daily",
            aggfunc="last",
        )
        .sort_index()
    )

    monthly_ret = equity_pivot.resample("M").last().pct_change()

    rows: List[Dict[str, Any]] = []

    strategies = list(ret_pivot.columns)

    for a, b in combinations(strategies, 2):
        pair = ret_pivot[[a, b]].dropna()

        if pair.empty:
            continue

        corr_daily = pair[a].corr(pair[b])

        m_pair = monthly_ret[[a, b]].dropna()
        corr_monthly = m_pair[a].corr(m_pair[b]) if len(m_pair) > 2 else np.nan

        a_negative = pair[pair[a] < 0]
        b_negative = pair[pair[b] < 0]

        a_worst_5pct_threshold = pair[a].quantile(0.05)
        b_worst_5pct_threshold = pair[b].quantile(0.05)

        a_worst_5pct = pair[pair[a] <= a_worst_5pct_threshold]
        b_worst_5pct = pair[pair[b] <= b_worst_5pct_threshold]

        both_negative_pct = ((pair[a] < 0) & (pair[b] < 0)).mean()

        rows.append({
            "strategy_a": a,
            "strategy_b": b,

            "days_compared": len(pair),

            "corr_daily_returns": corr_daily,
            "corr_monthly_returns": corr_monthly,

            "avg_daily_return_a": pair[a].mean(),
            "avg_daily_return_b": pair[b].mean(),

            "vol_daily_a": pair[a].std(),
            "vol_daily_b": pair[b].std(),

            "both_negative_pct": both_negative_pct,

            "b_avg_return_when_a_negative": (
                a_negative[b].mean() if len(a_negative) else np.nan
            ),
            "b_positive_pct_when_a_negative": (
                (a_negative[b] > 0).mean() if len(a_negative) else np.nan
            ),

            "a_avg_return_when_b_negative": (
                b_negative[a].mean() if len(b_negative) else np.nan
            ),
            "a_positive_pct_when_b_negative": (
                (b_negative[a] > 0).mean() if len(b_negative) else np.nan
            ),

            "a_worst_5pct_threshold": a_worst_5pct_threshold,
            "b_avg_return_when_a_worst_5pct": (
                a_worst_5pct[b].mean() if len(a_worst_5pct) else np.nan
            ),
            "b_positive_pct_when_a_worst_5pct": (
                (a_worst_5pct[b] > 0).mean() if len(a_worst_5pct) else np.nan
            ),

            "b_worst_5pct_threshold": b_worst_5pct_threshold,
            "a_avg_return_when_b_worst_5pct": (
                b_worst_5pct[a].mean() if len(b_worst_5pct) else np.nan
            ),
            "a_positive_pct_when_b_worst_5pct": (
                (b_worst_5pct[a] > 0).mean() if len(b_worst_5pct) else np.nan
            ),
        })

    return pd.DataFrame(rows)


def build_rolling_correlations(
    daily_out: pd.DataFrame,
    windows: List[int],
) -> pd.DataFrame:
    d = daily_out.copy()
    d["date"] = pd.to_datetime(d["date"])

    ret_pivot = (
        d.pivot_table(
            index="date",
            columns="strategy",
            values="portfolio_daily_return",
            aggfunc="last",
        )
        .sort_index()
    )

    rows: List[pd.DataFrame] = []

    strategies = list(ret_pivot.columns)

    for a, b in combinations(strategies, 2):
        pair = ret_pivot[[a, b]].dropna()

        if pair.empty:
            continue

        for window in windows:
            rc = pair[a].rolling(window).corr(pair[b])

            tmp = pd.DataFrame({
                "date": rc.index,
                "strategy_a": a,
                "strategy_b": b,
                "window_days": window,
                "rolling_corr": rc.values,
            })

            rows.append(tmp)

    if not rows:
        return pd.DataFrame()

    return pd.concat(rows, ignore_index=True)


# =========================
# CRISIS WINDOWS
# =========================

def build_crisis_windows_report(daily_out: pd.DataFrame) -> pd.DataFrame:
    windows = [
        ("GFC_2008_2009", "2008-09-01", "2009-03-31"),
        ("COVID_CRASH_2020", "2020-02-19", "2020-03-23"),
        ("INFLATION_BEAR_2022", "2022-01-03", "2022-10-14"),
        ("FULL_2020", "2020-01-01", "2020-12-31"),
        ("FULL_2022", "2022-01-01", "2022-12-31"),
    ]

    rows: List[Dict[str, Any]] = []

    d = daily_out.copy()
    d["date"] = pd.to_datetime(d["date"])

    for strategy, group in d.groupby("strategy", sort=False):
        g = group.sort_values("date").set_index("date")

        for name, start_raw, end_raw in windows:
            start = pd.Timestamp(start_raw)
            end = pd.Timestamp(end_raw)

            w = g.loc[(g.index >= start) & (g.index <= end)].copy()

            if len(w) < 2:
                continue

            eq = w["equity_daily"]
            dd = calc_drawdown(eq)

            rows.append({
                "window": name,
                "strategy": strategy,
                "start": w.index[0],
                "end": w.index[-1],
                "window_return": float(eq.iloc[-1] / eq.iloc[0] - 1.0),
                "window_maxdd": float(dd.min()),
                "window_min_date": dd.idxmin(),
                "days": len(w),
            })

    return pd.DataFrame(rows)


# =========================
# BLEND GRID A/B
# =========================

def build_blend_grid(
    daily_out: pd.DataFrame,
    strategy_a: str,
    strategy_b: str,
    step: float,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    d = daily_out.copy()
    d["date"] = pd.to_datetime(d["date"])

    ret_pivot = (
        d.pivot_table(
            index="date",
            columns="strategy",
            values="portfolio_daily_return",
            aggfunc="last",
        )
        .sort_index()
    )

    if strategy_a not in ret_pivot.columns:
        raise ValueError(f"Brak strategii A w daily_out: {strategy_a}")

    if strategy_b not in ret_pivot.columns:
        raise ValueError(f"Brak strategii B w daily_out: {strategy_b}")

    pair = ret_pivot[[strategy_a, strategy_b]].dropna()

    if pair.empty:
        raise ValueError("Brak wspólnych dat dla blend grid.")

    weights = np.arange(0.0, 1.0 + step / 2.0, step)
    weights = np.clip(weights, 0.0, 1.0)

    daily_rows: List[pd.DataFrame] = []
    summary_rows: List[Dict[str, Any]] = []

    for wa in weights:
        wb = 1.0 - wa

        label = f"A{int(round(wa * 100)):03d}_B{int(round(wb * 100)):03d}"

        r = wa * pair[strategy_a] + wb * pair[strategy_b]
        equity = (1.0 + r).cumprod()
        dd = calc_drawdown(equity)

        tmp = pd.DataFrame({
            "date": pair.index,
            "blend": label,
            "weight_a": wa,
            "weight_b": wb,
            "daily_return": r.values,
            "equity": equity.values,
            "drawdown": dd.values,
        })

        daily_rows.append(tmp)

        start_date = pd.Timestamp(pair.index[0])
        end_date = pd.Timestamp(pair.index[-1])
        final_equity = float(equity.iloc[-1])
        maxdd = float(dd.min())
        cagr = calc_cagr(1.0, final_equity, start_date, end_date)

        summary_rows.append({
            "blend": label,
            "strategy_a": strategy_a,
            "strategy_b": strategy_b,
            "weight_a": wa,
            "weight_b": wb,
            "start_date": start_date,
            "end_date": end_date,
            "final_equity": final_equity,
            "total_return": final_equity - 1.0,
            "cagr": cagr,
            "maxdd": maxdd,
            "calmar_cagr_absmaxdd": cagr / abs(maxdd) if maxdd < 0 else np.nan,
            "vol_daily": float(r.std()),
            "vol_annualized": float(r.std() * np.sqrt(252)),
        })

    blend_daily = pd.concat(daily_rows, ignore_index=True)
    blend_summary = pd.DataFrame(summary_rows)

    return blend_daily, blend_summary


# =========================
# MAIN
# =========================

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Porównuje wiele miesięcznych replayów strategii na dziennej krzywej equity: "
            "A, B, combined, benchmark, korelacje, kryzysy i blend grid."
        )
    )

    parser.add_argument(
        "--replay",
        nargs="+",
        required=True,
        help=(
            "Lista replayów w formacie LABEL=plik.csv, np. "
            "A=aaa.csv B=bbb.csv COMBINED=combined.csv"
        ),
    )

    parser.add_argument(
        "--daily-close",
        required=True,
        help="daily_close.csv z cenami dziennymi.",
    )

    parser.add_argument(
        "--benchmark-ticker",
        default=None,
        help="Opcjonalny benchmark, np. vt.us.",
    )

    parser.add_argument(
        "--blend-pair",
        default=None,
        help="Opcjonalnie para do siatki blendów, np. A,B.",
    )

    parser.add_argument(
        "--blend-step",
        type=float,
        default=0.1,
        help="Krok siatki blendów, domyślnie 0.1.",
    )

    parser.add_argument(
        "--output-dir",
        default="output_compare_daily",
        help="Folder wyjściowy.",
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    daily_close = load_daily_close(Path(args.daily_close))

    monthly_parts: List[pd.DataFrame] = []

    for raw in args.replay:
        label, path = parse_replay_arg(raw)

        if not path.exists():
            raise FileNotFoundError(f"Nie istnieje plik replay: {path}")

        part = load_monthly_replay(path, label=label)
        monthly_parts.append(part)

    monthly = pd.concat(monthly_parts, ignore_index=True)

    all_daily: List[pd.DataFrame] = []
    all_periods: List[pd.DataFrame] = []
    all_warnings: List[str] = []

    for strategy, group in monthly.groupby("strategy", sort=False):
        daily_df, period_df, warnings = build_daily_equity_for_strategy(
            group=group.copy(),
            daily_close=daily_close,
        )

        all_daily.append(daily_df)
        all_periods.append(period_df)
        all_warnings.extend(warnings)

    daily_out = pd.concat(all_daily, ignore_index=True)
    period_out = pd.concat(all_periods, ignore_index=True)

    summary = build_strategy_summary(daily_out)

    benchmark_out = None

    if args.benchmark_ticker is not None:
        all_benchmarks: List[pd.DataFrame] = []

        for strategy, strategy_daily in daily_out.groupby("strategy", sort=False):
            b = build_benchmark_for_strategy(
                strategy_daily=strategy_daily.copy(),
                daily_close=daily_close,
                benchmark_ticker=args.benchmark_ticker,
            )

            all_benchmarks.append(b)

        benchmark_out = pd.concat(all_benchmarks, ignore_index=True)
        summary = add_benchmark_to_summary(summary, benchmark_out)

    pairwise = build_pairwise_strategy_comparison(daily_out)
    rolling_corr = build_rolling_correlations(daily_out, windows=[63, 126, 252])
    crisis = build_crisis_windows_report(daily_out)

    daily_file = output_dir / "daily_equity_all.csv"
    period_file = output_dir / "period_daily_maxdd_all.csv"
    summary_file = output_dir / "strategy_summary.csv"
    pairwise_file = output_dir / "pairwise_correlation.csv"
    rolling_file = output_dir / "rolling_correlations.csv"
    crisis_file = output_dir / "crisis_windows.csv"
    warnings_file = output_dir / "warnings.txt"

    daily_out.to_csv(daily_file, index=False, float_format="%.10f")
    period_out.to_csv(period_file, index=False, float_format="%.10f")
    summary.to_csv(summary_file, index=False, float_format="%.10f")
    pairwise.to_csv(pairwise_file, index=False, float_format="%.10f")
    rolling_corr.to_csv(rolling_file, index=False, float_format="%.10f")
    crisis.to_csv(crisis_file, index=False, float_format="%.10f")

    if benchmark_out is not None:
        benchmark_file = output_dir / "benchmark_daily_all.csv"
        benchmark_out.to_csv(benchmark_file, index=False, float_format="%.10f")
        print(f"[OK] zapisano: {benchmark_file}")

    if args.blend_pair is not None:
        parts = [x.strip() for x in args.blend_pair.split(",")]

        if len(parts) != 2:
            raise ValueError("--blend-pair musi mieć format A,B")

        blend_daily, blend_summary = build_blend_grid(
            daily_out=daily_out,
            strategy_a=parts[0],
            strategy_b=parts[1],
            step=args.blend_step,
        )

        blend_daily_file = output_dir / "blend_grid_daily.csv"
        blend_summary_file = output_dir / "blend_grid_summary.csv"

        blend_daily.to_csv(blend_daily_file, index=False, float_format="%.10f")
        blend_summary.to_csv(blend_summary_file, index=False, float_format="%.10f")

        print(f"[OK] zapisano: {blend_daily_file}")
        print(f"[OK] zapisano: {blend_summary_file}")

    with warnings_file.open("w", encoding="utf-8") as f:
        for w in all_warnings:
            f.write(w + "\n")

    print(f"[OK] zapisano: {daily_file}")
    print(f"[OK] zapisano: {period_file}")
    print(f"[OK] zapisano: {summary_file}")
    print(f"[OK] zapisano: {pairwise_file}")
    print(f"[OK] zapisano: {rolling_file}")
    print(f"[OK] zapisano: {crisis_file}")

    if all_warnings:
        print(f"[UWAGA] Są ostrzeżenia: {warnings_file}")

    print("\n=== STRATEGY SUMMARY ===")
    print(summary.to_string(index=False))

    if not pairwise.empty:
        print("\n=== PAIRWISE CORRELATION ===")
        print(pairwise.to_string(index=False))

    if not crisis.empty:
        print("\n=== CRISIS WINDOWS ===")
        print(crisis.to_string(index=False))


if __name__ == "__main__":
    main()