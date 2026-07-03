from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple

import numpy as np
import pandas as pd


CASH_NAMES = {"_CASH", "CASH", "cash", "Cash"}


# =========================
# WCZYTYWANIE
# =========================

def parse_weights(raw: str) -> Dict[str, float]:
    if pd.isna(raw):
        return {}

    data = json.loads(raw)

    out: Dict[str, float] = {}

    for ticker, weight in data.items():
        out[str(ticker).strip()] = float(weight)

    return out


def load_daily_close(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)

    # Czyścimy nazwy kolumn, np. BOM z Excela / Windowsa
    df.columns = [
        str(c).strip().replace("\ufeff", "")
        for c in df.columns
    ]

    # Akceptujemy date / DATE / Date itd.
    date_col = None
    for col in df.columns:
        if col.lower() == "date":
            date_col = col
            break

    if date_col is None:
        raise ValueError(
            "daily_close.csv musi mieć kolumnę date/DATE. "
            f"Znalezione kolumny: {list(df.columns)[:10]}"
        )

    df = df.rename(columns={date_col: "date"})

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    df = df.set_index("date")

    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.sort_index()


def load_monthly_replay(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)

    required = {"date", "weights_used_json"}
    missing = required - set(df.columns)

    if missing:
        raise ValueError(f"Brakuje kolumn w monthly replay: {missing}")

    df["date"] = pd.to_datetime(df["date"])

    if "strategy" not in df.columns:
        df["strategy"] = "strategy"

    return df.sort_values(["strategy", "date"]).reset_index(drop=True)


# =========================
# DATY / EQUITY
# =========================

def first_trading_day_on_or_after(
    index: pd.DatetimeIndex,
    date: pd.Timestamp,
) -> pd.Timestamp | None:
    pos = index.searchsorted(date, side="left")

    if pos >= len(index):
        return None

    return index[pos]


def infer_initial_equity(group: pd.DataFrame) -> float:
    """
    Zakładamy, że source_combined_equity w monthly replay to equity PO zwrocie
    z danego miesięcznego okresu.

    Czyli:
        equity_start = source_combined_equity / (1 + source_combined_return)

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

    if abs(1.0 + period_return) < 1e-12:
        return 1.0

    return float(equity_after / (1.0 + period_return))


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

        key = ticker.lower()
        col = column_map.get(key)

        if col is None:
            missing.append(ticker)
            continue

        r = daily_return_row.get(col, np.nan)

        if pd.isna(r):
            r = 0.0

        port_ret += float(weight) * float(r)

    return port_ret, missing


# =========================
# STRATEGIA DAILY EQUITY
# =========================

def build_daily_equity_for_strategy(
    group: pd.DataFrame,
    daily_close: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame, List[str]]:
    strategy = str(group["strategy"].iloc[0])

    prices = daily_close.copy().ffill()

    daily_returns = prices.pct_change()
    daily_returns = daily_returns.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    column_map = {str(c).lower(): str(c) for c in daily_returns.columns}

    nominal_dates = list(group["date"])

    rebalance_dates: List[pd.Timestamp | None] = [
        first_trading_day_on_or_after(daily_returns.index, pd.Timestamp(d))
        for d in nominal_dates
    ]

    if len(group) < 2:
        raise ValueError(
            f"Strategia {strategy}: potrzeba co najmniej 2 miesięcznych wierszy."
        )

    first_rebalance = rebalance_dates[0]

    if first_rebalance is None:
        raise ValueError(f"Strategia {strategy}: brak dziennej daty startowej.")

    equity = infer_initial_equity(group)

    daily_rows: List[Dict[str, Any]] = []
    period_rows: List[Dict[str, Any]] = []
    warnings: List[str] = []

    daily_rows.append({
        "date": first_rebalance,
        "strategy": strategy,
        "equity_daily": equity,
        "period_start": nominal_dates[0],
        "period_end": pd.NaT,
        "rebalance_date": first_rebalance,
        "next_rebalance_date": pd.NaT,
        "portfolio_daily_return": 0.0,
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
                "period_start": nominal_start,
                "period_end": nominal_end,
                "rebalance_date": start_rebalance,
                "next_rebalance_date": end_rebalance,
                "portfolio_daily_return": port_ret,
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
        p["period_peak"] = p["equity_daily"].cummax()
        p["period_drawdown"] = p["equity_daily"] / p["period_peak"] - 1.0

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
    column_map = {str(c).lower(): str(c) for c in daily_close.columns}

    key = benchmark_ticker.lower()

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
    out = out[[
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

    return out


def add_benchmark_to_summary(
    summary: pd.DataFrame,
    benchmark_daily: pd.DataFrame,
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []

    for strategy, group in benchmark_daily.groupby("strategy", sort=False):
        g = group.sort_values("date").reset_index(drop=True)

        maxdd_idx = g["benchmark_drawdown"].idxmin()

        rows.append({
            "strategy": strategy,
            "benchmark_ticker": g["benchmark_ticker"].iloc[0],
            "benchmark_final_equity": float(g["benchmark_equity"].iloc[-1]),
            "benchmark_daily_maxdd": float(g["benchmark_drawdown"].min()),
            "benchmark_maxdd_date": g.loc[maxdd_idx, "date"],
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

    return out


# =========================
# SUMMARY
# =========================

def build_strategy_summary(daily_out: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []

    for strategy, group in daily_out.groupby("strategy", sort=False):
        g = group.sort_values("date").reset_index(drop=True)

        maxdd_idx = g["daily_drawdown"].idxmin()

        rows.append({
            "strategy": strategy,
            "start_date": g["date"].iloc[0],
            "end_date": g["date"].iloc[-1],
            "final_equity_daily": float(g["equity_daily"].iloc[-1]),
            "total_return_daily": float(g["equity_daily"].iloc[-1] / g["equity_daily"].iloc[0] - 1.0),
            "maxdd_daily": float(g["daily_drawdown"].min()),
            "maxdd_daily_date": g.loc[maxdd_idx, "date"],
        })

    return pd.DataFrame(rows)


# =========================
# MAIN
# =========================

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Liczy dzienną krzywą equity, dzienny MaxDD oraz opcjonalnie "
            "porównanie do benchmarku na podstawie miesięcznych wag strategii."
        )
    )

    parser.add_argument(
        "--monthly-replay",
        required=True,
        help="CSV z miesięcznym replayem strategii: date, strategy, weights_used_json.",
    )

    parser.add_argument(
        "--daily-close",
        required=True,
        help="daily_close.csv wygenerowany Twoim skryptem.",
    )

    parser.add_argument(
        "--benchmark-ticker",
        default=None,
        help="Opcjonalny ticker benchmarku z daily_close.csv, np. vt.us, spy.us, iwda.uk.",
    )

    parser.add_argument(
        "--output-dir",
        default="output_daily_maxdd",
        help="Folder wyjściowy.",
    )

    args = parser.parse_args()

    monthly_replay_path = Path(args.monthly_replay)
    daily_close_path = Path(args.daily_close)
    output_dir = Path(args.output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    monthly = load_monthly_replay(monthly_replay_path)
    daily_close = load_daily_close(daily_close_path)

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

    daily_file = output_dir / "daily_equity_drawdown.csv"
    period_file = output_dir / "period_daily_maxdd.csv"
    summary_file = output_dir / "summary_daily_maxdd.csv"
    warnings_file = output_dir / "warnings.txt"

    daily_out.to_csv(daily_file, index=False, float_format="%.10f")
    period_out.to_csv(period_file, index=False, float_format="%.10f")
    summary.to_csv(summary_file, index=False, float_format="%.10f")

    if benchmark_out is not None:
        benchmark_file = output_dir / "benchmark_daily_equity_drawdown.csv"
        benchmark_out.to_csv(benchmark_file, index=False, float_format="%.10f")
        print(f"[OK] zapisano: {benchmark_file}")

    with warnings_file.open("w", encoding="utf-8") as f:
        for w in all_warnings:
            f.write(w + "\n")

    print(f"[OK] zapisano: {daily_file}")
    print(f"[OK] zapisano: {period_file}")
    print(f"[OK] zapisano: {summary_file}")

    if all_warnings:
        print(f"[UWAGA] Są ostrzeżenia: {warnings_file}")

    print("\nPodsumowanie:")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()