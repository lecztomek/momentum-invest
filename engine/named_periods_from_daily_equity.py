from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

EPS = 1e-12


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def load_equity_csv(path: Path, equity_col: str) -> pd.Series:
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])

    if "strategy" in df.columns and df["strategy"].nunique() > 1:
        raise ValueError(
            f"{path} zawiera więcej niż jedną strategię: {sorted(df['strategy'].unique())}. "
            "Ten skrypt liczy analitykę dla jednej krzywej equity naraz."
        )

    df = df.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    return df.set_index("date")[equity_col].astype(float)


def slice_period(equity: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> Optional[pd.Series]:
    sub = equity.loc[(equity.index >= start) & (equity.index <= end)]
    if len(sub) < 2:
        return None
    return sub


def total_return_from_equity(equity: pd.Series) -> float:
    return float(equity.iloc[-1] / equity.iloc[0] - 1.0)


def cagr_from_equity(equity: pd.Series) -> float:
    total_ret = total_return_from_equity(equity)
    days = (equity.index[-1] - equity.index[0]).days
    years = days / 365.25
    if years <= 0:
        return float("nan")
    base = 1.0 + total_ret
    if base <= 0:
        return -1.0
    return float(base ** (1.0 / years) - 1.0)


def max_drawdown_from_equity(equity: pd.Series) -> float:
    normalized = equity / equity.iloc[0]
    peak = normalized.cummax()
    dd = normalized / peak - 1.0
    return float(dd.min())


def sharpe_from_equity(equity: pd.Series) -> float:
    ret = equity.pct_change().dropna()
    if len(ret) < 2:
        return float("nan")
    vol = ret.std(ddof=1)
    if vol <= EPS:
        return float("nan")
    return float(ret.mean() / vol * np.sqrt(252.0))


# =========================
# NAMED PERIODS
# =========================

def summarize_named_period(
    strategy_name: str,
    benchmark_ticker: str,
    period_name: str,
    strategy_equity: pd.Series,
    benchmark_equity: pd.Series,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> Optional[Dict[str, Any]]:
    strat_sub = slice_period(strategy_equity, start, end)
    bench_sub = slice_period(benchmark_equity, start, end)

    if strat_sub is None or bench_sub is None:
        return None

    common_index = strat_sub.index.intersection(bench_sub.index)
    if len(common_index) < 2:
        return None

    strat_sub = strat_sub.loc[common_index]
    bench_sub = bench_sub.loc[common_index]

    total_return = total_return_from_equity(strat_sub)
    cagr = cagr_from_equity(strat_sub)
    max_drawdown = max_drawdown_from_equity(strat_sub)

    benchmark_total_return = total_return_from_equity(bench_sub)
    benchmark_cagr = cagr_from_equity(bench_sub)
    benchmark_max_drawdown = max_drawdown_from_equity(bench_sub)

    strat_daily_ret = strat_sub.pct_change().dropna()
    bench_daily_ret = bench_sub.pct_change().dropna()
    hit_rate_excess = float((strat_daily_ret > bench_daily_ret).mean()) if len(strat_daily_ret) else float("nan")

    calmar = float(cagr / abs(max_drawdown)) if abs(max_drawdown) > EPS else float("nan")

    start_actual = common_index.min()
    end_actual = common_index.max()
    months = (end_actual.year - start_actual.year) * 12 + (end_actual.month - start_actual.month) + 1

    return {
        "strategy": strategy_name,
        "benchmark": benchmark_ticker,
        "period_name": period_name,
        "start": start_actual.strftime("%Y-%m-%d"),
        "end": end_actual.strftime("%Y-%m-%d"),
        "months": int(months),
        "days": int(len(common_index)),
        "total_return": total_return,
        "cagr": cagr,
        "max_drawdown": max_drawdown,
        "calmar": calmar,
        "benchmark_total_return": benchmark_total_return,
        "benchmark_cagr": benchmark_cagr,
        "benchmark_max_drawdown": benchmark_max_drawdown,
        "cagr_vs_benchmark": cagr - benchmark_cagr,
        "maxdd_vs_benchmark": max_drawdown - benchmark_max_drawdown,
        "hit_rate_excess": hit_rate_excess,
    }


def build_named_periods(
    strategy_name: str,
    benchmark_ticker: str,
    strategy_equity: pd.Series,
    benchmark_equity: pd.Series,
    named_periods: List[Dict[str, Any]],
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for item in named_periods:
        row = summarize_named_period(
            strategy_name=strategy_name,
            benchmark_ticker=benchmark_ticker,
            period_name=str(item["name"]),
            strategy_equity=strategy_equity,
            benchmark_equity=benchmark_equity,
            start=pd.Timestamp(item["start"]),
            end=pd.Timestamp(item["end"]),
        )
        if row is not None:
            rows.append(row)

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("start")


# =========================
# ROLLING WINDOWS
# =========================

def month_start_anchors(index: pd.DatetimeIndex) -> List[pd.Timestamp]:
    month_starts = pd.date_range(index.min().normalize(), index.max().normalize(), freq="MS")
    anchors: List[pd.Timestamp] = []
    for m in month_starts:
        pos = index.searchsorted(m, side="left")
        if pos < len(index):
            anchors.append(index[pos])
    dedup = sorted(set(anchors))
    return dedup


def build_rolling_windows_detail(
    strategy_name: str,
    benchmark_ticker: str,
    strategy_equity: pd.Series,
    benchmark_equity: pd.Series,
    window_months_list: List[int],
) -> pd.DataFrame:
    common_index = strategy_equity.index.intersection(benchmark_equity.index)
    strat = strategy_equity.loc[common_index]
    bench = benchmark_equity.loc[common_index]

    anchors = month_start_anchors(common_index)
    rows: List[Dict[str, Any]] = []

    for window in window_months_list:
        window = int(window)
        for i in range(len(anchors) - window):
            start = anchors[i]
            end = anchors[i + window]

            strat_sub = strat.loc[(strat.index >= start) & (strat.index <= end)]
            bench_sub = bench.loc[(bench.index >= start) & (bench.index <= end)]

            if len(strat_sub) < 2 or len(bench_sub) < 2:
                continue

            strat_ret = total_return_from_equity(strat_sub)
            bench_ret = total_return_from_equity(bench_sub)
            strat_cagr = cagr_from_equity(strat_sub)
            bench_cagr = cagr_from_equity(bench_sub)
            strat_dd = max_drawdown_from_equity(strat_sub)
            bench_dd = max_drawdown_from_equity(bench_sub)

            strat_daily_ret = strat_sub.pct_change().dropna()
            bench_daily_ret = bench_sub.pct_change().dropna()
            common_ret_idx = strat_daily_ret.index.intersection(bench_daily_ret.index)

            rows.append({
                "strategy": strategy_name,
                "benchmark": benchmark_ticker,
                "window_months": window,
                "window_start": start.strftime("%Y-%m-%d"),
                "window_end": end.strftime("%Y-%m-%d"),
                "strategy_total_return": strat_ret,
                "benchmark_total_return": bench_ret,
                "total_return_vs_benchmark": strat_ret - bench_ret,
                "strategy_cagr": strat_cagr,
                "benchmark_cagr": bench_cagr,
                "cagr_vs_benchmark": strat_cagr - bench_cagr,
                "strategy_max_drawdown": strat_dd,
                "benchmark_max_drawdown": bench_dd,
                "maxdd_vs_benchmark": strat_dd - bench_dd,
                "strategy_final_equity": float(strat_sub.iloc[-1] / strat_sub.iloc[0]),
                "benchmark_final_equity": float(bench_sub.iloc[-1] / bench_sub.iloc[0]),
                "hit_rate_excess": (
                    float((strat_daily_ret.loc[common_ret_idx] > bench_daily_ret.loc[common_ret_idx]).mean())
                    if len(common_ret_idx) else float("nan")
                ),
            })

    return pd.DataFrame(rows)


def build_rolling_summary(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame()

    rows: List[Dict[str, Any]] = []
    for window, g in detail.groupby("window_months"):
        rows.append({
            "strategy": g["strategy"].iloc[0],
            "benchmark": g["benchmark"].iloc[0],
            "window_months": int(window),
            "n_windows": int(len(g)),
            "pct_windows_total_return_beats_benchmark": float((g["total_return_vs_benchmark"] > 0).mean()),
            "pct_windows_cagr_beats_benchmark": float((g["cagr_vs_benchmark"] > 0).mean()),
            "median_strategy_cagr": float(g["strategy_cagr"].median()),
            "median_benchmark_cagr": float(g["benchmark_cagr"].median()),
            "median_cagr_vs_benchmark": float(g["cagr_vs_benchmark"].median()),
            "worst_cagr_vs_benchmark": float(g["cagr_vs_benchmark"].min()),
            "best_cagr_vs_benchmark": float(g["cagr_vs_benchmark"].max()),
            "worst_strategy_max_drawdown": float(g["strategy_max_drawdown"].min()),
            "worst_benchmark_max_drawdown": float(g["benchmark_max_drawdown"].min()),
            "median_hit_rate_excess": float(g["hit_rate_excess"].median()),
        })

    return pd.DataFrame(rows).sort_values("window_months")


# =========================
# UNDERWATER PERIODS
# =========================

def summarize_underwater_from_equity(
    strategy_name: str,
    benchmark_ticker: str,
    strategy_equity: pd.Series,
    benchmark_equity: pd.Series,
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    series_specs = [("strategy", strategy_equity), ("benchmark", benchmark_equity)]

    for series_type, equity in series_specs:
        eq = equity / equity.iloc[0]
        peak = eq.cummax()
        dd = eq / peak - 1.0

        in_underwater = False
        start_date = None
        bottom_date = None
        bottom_dd = 0.0
        start_equity = None
        bottom_equity = None
        dates = list(eq.index)

        for dt in dates:
            current_dd = float(dd.loc[dt])
            current_equity = float(eq.loc[dt])
            current_peak = float(peak.loc[dt])

            if not in_underwater:
                if current_dd < -EPS:
                    in_underwater = True
                    start_date = dt
                    bottom_date = dt
                    bottom_dd = current_dd
                    start_equity = current_peak
                    bottom_equity = current_equity
                continue

            if current_dd < bottom_dd:
                bottom_dd = current_dd
                bottom_date = dt
                bottom_equity = current_equity

            if current_dd >= -EPS:
                duration_days = (dt - start_date).days
                days_to_bottom = (bottom_date - start_date).days
                rows.append({
                    "strategy": strategy_name,
                    "benchmark": benchmark_ticker,
                    "series_type": series_type,
                    "underwater_start": start_date.strftime("%Y-%m-%d"),
                    "underwater_bottom": bottom_date.strftime("%Y-%m-%d"),
                    "underwater_recovery": dt.strftime("%Y-%m-%d"),
                    "duration_days": int(duration_days),
                    "duration_months": round(duration_days / 30.44, 1),
                    "days_to_bottom": int(days_to_bottom),
                    "max_drawdown": float(bottom_dd),
                    "start_equity": float(start_equity),
                    "bottom_equity": float(bottom_equity),
                    "recovery_equity": current_equity,
                    "is_recovered": 1,
                })
                in_underwater = False
                start_date = None
                bottom_date = None
                bottom_dd = 0.0
                start_equity = None
                bottom_equity = None

        if in_underwater:
            last_dt = dates[-1]
            duration_days = (last_dt - start_date).days
            days_to_bottom = (bottom_date - start_date).days
            rows.append({
                "strategy": strategy_name,
                "benchmark": benchmark_ticker,
                "series_type": series_type,
                "underwater_start": start_date.strftime("%Y-%m-%d"),
                "underwater_bottom": bottom_date.strftime("%Y-%m-%d"),
                "underwater_recovery": None,
                "duration_days": int(duration_days),
                "duration_months": round(duration_days / 30.44, 1),
                "days_to_bottom": int(days_to_bottom),
                "max_drawdown": float(bottom_dd),
                "start_equity": float(start_equity),
                "bottom_equity": float(bottom_equity),
                "recovery_equity": None,
                "is_recovered": 0,
            })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values(["series_type", "max_drawdown"])


def save_csv(df: pd.DataFrame, path: Path) -> None:
    if df.empty:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, float_format="%.10f")
    print(f"[OK] zapisano: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Liczy named periods, rolling windows i underwater periods na podstawie dziennej krzywej "
            "equity (daily_equity_drawdown.csv + benchmark_daily_equity_drawdown.csv). Używane tam, gdzie "
            "nie ma osobnego kroku backtestu liczącego to z miesięcznych zwrotów, np. US selected hedge "
            "(krok 07), które ma tylko dzienną rekonstrukcję equity."
        )
    )
    parser.add_argument("--daily-equity", required=True, help="daily_equity_drawdown.csv")
    parser.add_argument("--benchmark-daily-equity", required=True, help="benchmark_daily_equity_drawdown.csv")
    parser.add_argument("--config", required=True, help="Config JSON z kluczami named_periods, rolling_windows_months")
    parser.add_argument("--strategy-name", default=None)
    parser.add_argument("--benchmark-ticker", default=None)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    config = read_json(Path(args.config))
    named_periods = config.get("named_periods", [])
    rolling_windows = list(config.get("rolling_windows_months", [12, 24, 36, 48, 60, 84, 120, 180]))

    strategy_equity = load_equity_csv(Path(args.daily_equity), "equity_daily")
    benchmark_equity = load_equity_csv(Path(args.benchmark_daily_equity), "benchmark_equity")

    strategy_name = args.strategy_name
    if strategy_name is None:
        strategy_df = pd.read_csv(args.daily_equity, usecols=["strategy"])
        strategy_name = str(strategy_df["strategy"].dropna().iloc[0])

    benchmark_ticker = args.benchmark_ticker
    if benchmark_ticker is None:
        bench_df = pd.read_csv(args.benchmark_daily_equity, usecols=["benchmark_ticker"])
        benchmark_ticker = str(bench_df["benchmark_ticker"].dropna().iloc[0])

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    named_df = build_named_periods(strategy_name, benchmark_ticker, strategy_equity, benchmark_equity, named_periods)
    save_csv(named_df, out_dir / "summary_named_periods.csv")

    rolling_detail = build_rolling_windows_detail(strategy_name, benchmark_ticker, strategy_equity, benchmark_equity, rolling_windows)
    save_csv(rolling_detail, out_dir / "rolling_windows_detail.csv")

    if not rolling_detail.empty:
        worst = rolling_detail.sort_values("cagr_vs_benchmark").head(100)
        save_csv(worst, out_dir / "worst_rolling_windows.csv")

    rolling_summary = build_rolling_summary(rolling_detail)
    save_csv(rolling_summary, out_dir / "summary_rolling.csv")

    underwater = summarize_underwater_from_equity(strategy_name, benchmark_ticker, strategy_equity, benchmark_equity)
    save_csv(underwater, out_dir / "summary_underwater_periods.csv")

    if named_df.empty and rolling_detail.empty and underwater.empty:
        print("[WARN] Brak jakichkolwiek policzonych okresów - sprawdź zakres dat i config.")


if __name__ == "__main__":
    main()
