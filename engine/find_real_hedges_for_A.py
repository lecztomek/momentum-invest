from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd


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


def normalize_ticker(x: str) -> str:
    return str(x).strip().lower()


def calc_drawdown(equity: pd.Series) -> pd.Series:
    peak = equity.cummax()
    return equity / peak - 1.0


def calc_cagr(
    start_equity: float,
    end_equity: float,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> float:
    days = (end_date - start_date).days

    if days <= 0:
        return np.nan

    years = days / 365.25

    if start_equity <= 0 or end_equity <= 0:
        return np.nan

    return (end_equity / start_equity) ** (1.0 / years) - 1.0


def safe_calmar(cagr: float, maxdd: float) -> float:
    if pd.isna(cagr) or pd.isna(maxdd):
        return np.nan

    if maxdd >= 0:
        return np.nan

    return cagr / abs(maxdd)


def compound_returns_to_equity(r: pd.Series) -> pd.Series:
    return (1.0 + r.fillna(0.0)).cumprod()


def period_return(r: pd.Series) -> float:
    if len(r) == 0:
        return np.nan

    return float((1.0 + r.fillna(0.0)).prod() - 1.0)


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


def load_strategy_daily(path: Path, strategy: str | None) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = clean_columns(df)

    date_col = find_date_column(df)
    df = df.rename(columns={date_col: "date"})

    df["date"] = pd.to_datetime(df["date"])

    if "strategy" in df.columns and strategy is not None:
        df = df[df["strategy"].astype(str) == strategy].copy()

        if df.empty:
            raise ValueError(f"Nie znaleziono strategii '{strategy}' w pliku {path}")

    if "portfolio_daily_return" not in df.columns:
        if "equity_daily" not in df.columns:
            raise ValueError(
                "Plik strategii musi mieć portfolio_daily_return albo equity_daily."
            )

        df = df.sort_values("date")
        df["portfolio_daily_return"] = df["equity_daily"].pct_change().fillna(0.0)

    if "equity_daily" not in df.columns:
        df = df.sort_values("date")
        df["equity_daily"] = compound_returns_to_equity(df["portfolio_daily_return"])

    df = df.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    df = df.set_index("date")

    df["portfolio_daily_return"] = pd.to_numeric(
        df["portfolio_daily_return"],
        errors="coerce",
    )

    df["equity_daily"] = pd.to_numeric(
        df["equity_daily"],
        errors="coerce",
    )

    return df[["portfolio_daily_return", "equity_daily"]].dropna()


# =========================
# HEDGE METRICS
# =========================

def build_ticker_returns(daily_close: pd.DataFrame) -> pd.DataFrame:
    prices = daily_close.copy().ffill()
    rets = prices.pct_change()
    rets = rets.replace([np.inf, -np.inf], np.nan)

    return rets


def monthly_returns_from_daily_returns(daily_returns: pd.DataFrame) -> pd.DataFrame:
    return daily_returns.resample("M").apply(period_return)


def calc_single_ticker_metrics(
    ticker: str,
    a_ret: pd.Series,
    ticker_ret: pd.Series,
    min_obs: int,
    worst_quantile: float,
) -> Dict[str, Any] | None:
    pair = pd.concat(
        [
            a_ret.rename("A"),
            ticker_ret.rename("HEDGE"),
        ],
        axis=1,
    ).dropna()

    if len(pair) < min_obs:
        return None

    a = pair["A"]
    h = pair["HEDGE"]

    h_equity = compound_returns_to_equity(h)
    h_dd = calc_drawdown(h_equity)

    start_date = pd.Timestamp(pair.index[0])
    end_date = pd.Timestamp(pair.index[-1])

    h_final = float(h_equity.iloc[-1])
    h_cagr = calc_cagr(1.0, h_final, start_date, end_date)
    h_maxdd = float(h_dd.min())

    monthly = monthly_returns_from_daily_returns(pair)
    corr_monthly = (
        monthly["A"].corr(monthly["HEDGE"])
        if monthly.dropna().shape[0] > 3
        else np.nan
    )

    a_negative = pair[pair["A"] < 0]

    threshold = pair["A"].quantile(worst_quantile)
    a_worst = pair[pair["A"] <= threshold]

    a_worst_avg = float(a_worst["A"].mean()) if len(a_worst) else np.nan
    h_worst_avg = float(a_worst["HEDGE"].mean()) if len(a_worst) else np.nan

    if pd.isna(a_worst_avg) or abs(a_worst_avg) < 1e-12:
        protection_ratio = np.nan
    else:
        protection_ratio = h_worst_avg / abs(a_worst_avg)

    return {
        "ticker": ticker,
        "start_date": start_date,
        "end_date": end_date,
        "obs_days": len(pair),

        "corr_daily": float(pair["A"].corr(pair["HEDGE"])),
        "corr_monthly": float(corr_monthly) if not pd.isna(corr_monthly) else np.nan,

        "ticker_final_equity": h_final,
        "ticker_cagr": h_cagr,
        "ticker_maxdd": h_maxdd,
        "ticker_calmar": safe_calmar(h_cagr, h_maxdd),
        "ticker_vol_daily": float(h.std()),
        "ticker_vol_annualized": float(h.std() * np.sqrt(252)),

        "a_avg_return": float(a.mean()),
        "ticker_avg_return": float(h.mean()),

        "ticker_avg_when_a_negative": (
            float(a_negative["HEDGE"].mean()) if len(a_negative) else np.nan
        ),
        "ticker_positive_pct_when_a_negative": (
            float((a_negative["HEDGE"] > 0).mean()) if len(a_negative) else np.nan
        ),

        "a_worst_quantile": worst_quantile,
        "a_worst_threshold": float(threshold),
        "a_avg_return_worst": a_worst_avg,
        "ticker_avg_when_a_worst": h_worst_avg,
        "ticker_positive_pct_when_a_worst": (
            float((a_worst["HEDGE"] > 0).mean()) if len(a_worst) else np.nan
        ),
        "protection_ratio_when_a_worst": protection_ratio,
    }


def add_hedge_score(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()

    def rank_high(col: str) -> pd.Series:
        return out[col].rank(pct=True, ascending=True)

    def rank_low(col: str) -> pd.Series:
        return out[col].rank(pct=True, ascending=False)

    # Wyższe lepsze:
    # - ticker_avg_when_a_worst
    # - ticker_positive_pct_when_a_worst
    # - ticker_avg_when_a_negative
    # - ticker_cagr
    # - ticker_maxdd, bo -10% jest lepsze niż -40%
    #
    # Niższe lepsze:
    # - corr_daily
    # - corr_monthly
    out["hedge_score"] = (
        0.35 * rank_high("ticker_avg_when_a_worst")
        + 0.20 * rank_high("ticker_positive_pct_when_a_worst")
        + 0.15 * rank_high("ticker_avg_when_a_negative")
        + 0.15 * rank_low("corr_daily")
        + 0.05 * rank_low("corr_monthly")
        + 0.05 * rank_high("ticker_cagr")
        + 0.05 * rank_high("ticker_maxdd")
    )

    return out.sort_values("hedge_score", ascending=False)


def build_hedge_candidates(
    strategy_daily: pd.DataFrame,
    daily_close: pd.DataFrame,
    min_obs: int,
    worst_quantile: float,
    exclude_tickers: set[str],
) -> pd.DataFrame:
    a_ret = strategy_daily["portfolio_daily_return"].copy()
    ticker_returns = build_ticker_returns(daily_close)

    rows: List[Dict[str, Any]] = []

    for ticker in ticker_returns.columns:
        if normalize_ticker(ticker) in exclude_tickers:
            continue

        metrics = calc_single_ticker_metrics(
            ticker=str(ticker),
            a_ret=a_ret,
            ticker_ret=ticker_returns[ticker],
            min_obs=min_obs,
            worst_quantile=worst_quantile,
        )

        if metrics is not None:
            rows.append(metrics)

    out = pd.DataFrame(rows)

    if out.empty:
        return out

    out = add_hedge_score(out)

    return out


# =========================
# BLEND TESTS
# =========================

def summarize_return_stream(
    r: pd.Series,
    label_prefix: str,
) -> Dict[str, Any]:
    r = r.dropna()

    if r.empty:
        return {
            f"{label_prefix}_final_equity": np.nan,
            f"{label_prefix}_cagr": np.nan,
            f"{label_prefix}_maxdd": np.nan,
            f"{label_prefix}_calmar": np.nan,
            f"{label_prefix}_vol_annualized": np.nan,
        }

    equity = compound_returns_to_equity(r)
    dd = calc_drawdown(equity)

    start_date = pd.Timestamp(r.index[0])
    end_date = pd.Timestamp(r.index[-1])

    final_equity = float(equity.iloc[-1])
    cagr = calc_cagr(1.0, final_equity, start_date, end_date)
    maxdd = float(dd.min())

    return {
        f"{label_prefix}_final_equity": final_equity,
        f"{label_prefix}_cagr": cagr,
        f"{label_prefix}_maxdd": maxdd,
        f"{label_prefix}_calmar": safe_calmar(cagr, maxdd),
        f"{label_prefix}_vol_annualized": float(r.std() * np.sqrt(252)),
    }


def build_blend_grid_with_hedges(
    strategy_daily: pd.DataFrame,
    daily_close: pd.DataFrame,
    candidates: pd.DataFrame,
    top_n: int,
    hedge_weights: List[float],
) -> pd.DataFrame:
    a_ret_all = strategy_daily["portfolio_daily_return"].copy()
    ticker_returns = build_ticker_returns(daily_close)

    candidate_tickers = list(candidates.head(top_n)["ticker"])

    rows: List[Dict[str, Any]] = []

    for ticker in candidate_tickers:
        if ticker not in ticker_returns.columns:
            continue

        pair = pd.concat(
            [
                a_ret_all.rename("A"),
                ticker_returns[ticker].rename("HEDGE"),
            ],
            axis=1,
        ).dropna()

        if pair.empty:
            continue

        a_same = pair["A"]
        h = pair["HEDGE"]

        a_summary = summarize_return_stream(a_same, "a_same_period")
        h_summary = summarize_return_stream(h, "hedge_only")

        for hedge_weight in hedge_weights:
            a_weight = 1.0 - hedge_weight

            blend_ret = a_weight * a_same + hedge_weight * h
            blend_summary = summarize_return_stream(blend_ret, "blend")

            row: Dict[str, Any] = {
                "ticker": ticker,
                "weight_a": a_weight,
                "weight_hedge": hedge_weight,
                "start_date": pd.Timestamp(pair.index[0]),
                "end_date": pd.Timestamp(pair.index[-1]),
                "obs_days": len(pair),
            }

            row.update(a_summary)
            row.update(h_summary)
            row.update(blend_summary)

            row["delta_cagr_vs_a"] = (
                row["blend_cagr"] - row["a_same_period_cagr"]
            )

            # Dodatnie = poprawa, bo np. -0.20 - (-0.30) = +0.10
            row["delta_maxdd_vs_a"] = (
                row["blend_maxdd"] - row["a_same_period_maxdd"]
            )

            row["delta_calmar_vs_a"] = (
                row["blend_calmar"] - row["a_same_period_calmar"]
            )

            row["delta_final_equity_vs_a"] = (
                row["blend_final_equity"] - row["a_same_period_final_equity"]
            )

            rows.append(row)

    out = pd.DataFrame(rows)

    if out.empty:
        return out

    out = out.sort_values(
        [
            "delta_calmar_vs_a",
            "delta_maxdd_vs_a",
            "blend_calmar",
            "blend_cagr",
        ],
        ascending=[False, False, False, False],
    )

    return out


def build_best_blend_by_ticker(blend_grid: pd.DataFrame) -> pd.DataFrame:
    if blend_grid.empty:
        return blend_grid

    rows: List[pd.DataFrame] = []

    for ticker, group in blend_grid.groupby("ticker", sort=False):
        g = group.copy()

        # Preferujemy poprawę Calmar, potem poprawę MaxDD.
        g = g.sort_values(
            [
                "delta_calmar_vs_a",
                "delta_maxdd_vs_a",
                "blend_calmar",
            ],
            ascending=[False, False, False],
        )

        rows.append(g.head(1))

    out = pd.concat(rows, ignore_index=True)

    return out.sort_values(
        [
            "delta_calmar_vs_a",
            "delta_maxdd_vs_a",
            "blend_calmar",
        ],
        ascending=[False, False, False],
    )


# =========================
# CRISIS WINDOWS
# =========================

def build_crisis_windows_for_candidates(
    strategy_daily: pd.DataFrame,
    daily_close: pd.DataFrame,
    candidates: pd.DataFrame,
    top_n: int,
) -> pd.DataFrame:
    windows = [
        ("GFC_2008_2009", "2008-09-01", "2009-03-31"),
        ("COVID_CRASH_2020", "2020-02-19", "2020-03-23"),
        ("INFLATION_BEAR_2022", "2022-01-03", "2022-10-14"),
        ("FULL_2020", "2020-01-01", "2020-12-31"),
        ("FULL_2022", "2022-01-01", "2022-12-31"),
    ]

    a_ret_all = strategy_daily["portfolio_daily_return"].copy()
    ticker_returns = build_ticker_returns(daily_close)

    tickers = list(candidates.head(top_n)["ticker"])

    rows: List[Dict[str, Any]] = []

    for ticker in tickers:
        if ticker not in ticker_returns.columns:
            continue

        pair_all = pd.concat(
            [
                a_ret_all.rename("A"),
                ticker_returns[ticker].rename("HEDGE"),
            ],
            axis=1,
        ).dropna()

        for window_name, start_raw, end_raw in windows:
            start = pd.Timestamp(start_raw)
            end = pd.Timestamp(end_raw)

            pair = pair_all.loc[
                (pair_all.index >= start)
                & (pair_all.index <= end)
            ].copy()

            if len(pair) < 2:
                continue

            a_ret = pair["A"]
            h_ret = pair["HEDGE"]

            a_eq = compound_returns_to_equity(a_ret)
            h_eq = compound_returns_to_equity(h_ret)

            a_dd = calc_drawdown(a_eq)
            h_dd = calc_drawdown(h_eq)

            rows.append({
                "window": window_name,
                "ticker": ticker,
                "start": pair.index[0],
                "end": pair.index[-1],
                "days": len(pair),

                "a_window_return": float(a_eq.iloc[-1] - 1.0),
                "a_window_maxdd": float(a_dd.min()),

                "hedge_window_return": float(h_eq.iloc[-1] - 1.0),
                "hedge_window_maxdd": float(h_dd.min()),

                "hedge_minus_a_return": float((h_eq.iloc[-1] - 1.0) - (a_eq.iloc[-1] - 1.0)),
                "hedge_maxdd_minus_a_maxdd": float(h_dd.min() - a_dd.min()),
            })

    return pd.DataFrame(rows)


# =========================
# MAIN
# =========================

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Szuka realnych hedge tickerów dla strategii A na podstawie "
            "daily_close.csv i dziennych zwrotów strategii."
        )
    )

    parser.add_argument(
        "--strategy-daily",
        required=True,
        help=(
            "Plik daily_equity_all.csv z compare_monthly_replays_daily.py "
            "albo daily_equity_drawdown.csv dla jednej strategii."
        ),
    )

    parser.add_argument(
        "--strategy",
        default="A",
        help="Nazwa strategii w pliku strategy-daily. Domyślnie: A.",
    )

    parser.add_argument(
        "--daily-close",
        required=True,
        help="daily_close.csv z cenami wszystkich tickerów.",
    )

    parser.add_argument(
        "--output-dir",
        default="output_hedge_scan_A",
        help="Folder wyjściowy.",
    )

    parser.add_argument(
        "--min-obs",
        type=int,
        default=756,
        help=(
            "Minimalna liczba wspólnych dni obserwacji. "
            "Domyślnie 756, czyli ok. 3 lata sesyjne."
        ),
    )

    parser.add_argument(
        "--worst-quantile",
        type=float,
        default=0.05,
        help="Najgorszy kwantyl dni A. Domyślnie 0.05 = najgorsze 5% dni.",
    )

    parser.add_argument(
        "--top-n",
        type=int,
        default=30,
        help="Ile najlepszych kandydatów testować w blendach.",
    )

    parser.add_argument(
        "--hedge-weights",
        nargs="+",
        type=float,
        default=[0.05, 0.10, 0.15, 0.20, 0.30],
        help="Wagi hedge do testu blendów, np. 0.05 0.10 0.15 0.20.",
    )

    parser.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        help="Tickery do wykluczenia, np. vt.us qqq.us.",
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    strategy_daily = load_strategy_daily(
        path=Path(args.strategy_daily),
        strategy=args.strategy,
    )

    daily_close = load_daily_close(Path(args.daily_close))

    exclude_tickers = {normalize_ticker(x) for x in args.exclude}

    candidates = build_hedge_candidates(
        strategy_daily=strategy_daily,
        daily_close=daily_close,
        min_obs=args.min_obs,
        worst_quantile=args.worst_quantile,
        exclude_tickers=exclude_tickers,
    )

    if candidates.empty:
        raise SystemExit("Brak kandydatów. Zmniejsz --min-obs albo sprawdź dane.")

    blend_grid = build_blend_grid_with_hedges(
        strategy_daily=strategy_daily,
        daily_close=daily_close,
        candidates=candidates,
        top_n=args.top_n,
        hedge_weights=args.hedge_weights,
    )

    best_blend = build_best_blend_by_ticker(blend_grid)

    crisis = build_crisis_windows_for_candidates(
        strategy_daily=strategy_daily,
        daily_close=daily_close,
        candidates=candidates,
        top_n=args.top_n,
    )

    candidates_file = output_dir / "hedge_candidates.csv"
    blend_file = output_dir / "hedge_blend_grid.csv"
    best_blend_file = output_dir / "hedge_best_blend_by_ticker.csv"
    crisis_file = output_dir / "hedge_crisis_windows.csv"

    candidates.to_csv(candidates_file, index=False, float_format="%.10f")
    blend_grid.to_csv(blend_file, index=False, float_format="%.10f")
    best_blend.to_csv(best_blend_file, index=False, float_format="%.10f")
    crisis.to_csv(crisis_file, index=False, float_format="%.10f")

    print(f"[OK] zapisano: {candidates_file}")
    print(f"[OK] zapisano: {blend_file}")
    print(f"[OK] zapisano: {best_blend_file}")
    print(f"[OK] zapisano: {crisis_file}")

    print("\n=== TOP HEDGE CANDIDATES ===")
    cols = [
        "ticker",
        "hedge_score",
        "corr_daily",
        "corr_monthly",
        "ticker_avg_when_a_worst",
        "ticker_positive_pct_when_a_worst",
        "ticker_avg_when_a_negative",
        "ticker_positive_pct_when_a_negative",
        "ticker_cagr",
        "ticker_maxdd",
        "obs_days",
        "start_date",
    ]

    print(candidates[cols].head(30).to_string(index=False))

    if not best_blend.empty:
        print("\n=== BEST BLEND BY TICKER ===")
        cols2 = [
            "ticker",
            "weight_a",
            "weight_hedge",
            "blend_cagr",
            "blend_maxdd",
            "blend_calmar",
            "delta_cagr_vs_a",
            "delta_maxdd_vs_a",
            "delta_calmar_vs_a",
            "obs_days",
            "start_date",
        ]

        print(best_blend[cols2].head(30).to_string(index=False))


if __name__ == "__main__":
    main()