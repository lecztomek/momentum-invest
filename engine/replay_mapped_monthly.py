from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd

EPS = 1e-12


def load_wide_csv(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0)
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def load_monthly_csv(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "date" not in df.columns:
        first = df.columns[0]
        df = df.rename(columns={first: "date"})
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").set_index("date")


def parse_json_obj(value: Any) -> Dict[str, float]:
    if isinstance(value, dict):
        return {str(k): float(v) for k, v in value.items()}
    if pd.isna(value):
        return {}
    obj = json.loads(str(value))
    return {str(k): float(v) for k, v in obj.items()}


def normalize_weights_or_cash(weights: Dict[str, float]) -> Dict[str, float]:
    clean = {str(a): float(w) for a, w in weights.items() if abs(float(w)) > EPS}
    total = float(sum(clean.values()))
    if total <= EPS:
        return {"_CASH": 1.0}
    return {a: float(w) / total for a, w in clean.items()}


def normalize_signature(weights: Dict[str, float]) -> Tuple[Tuple[str, float], ...]:
    return tuple((a, round(float(w), 10)) for a, w in sorted(weights.items()) if abs(float(w)) > EPS)


def load_mapping(path: str | Path) -> Dict[str, str]:
    with Path(path).open("r", encoding="utf-8-sig") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError("Mapping JSON must be an object: {old_ticker: new_ticker}")
    return {str(k): str(v) for k, v in obj.items()}


def map_weights(
    weights: Dict[str, float],
    mapping: Dict[str, str],
    unmapped: str = "error",
) -> Dict[str, float]:
    out: Dict[str, float] = {}

    for old_asset, weight in weights.items():
        if abs(float(weight)) <= EPS:
            continue

        if old_asset == "_CASH":
            new_asset = "_CASH"
        elif old_asset in mapping:
            new_asset = mapping[old_asset]
        elif unmapped == "keep":
            new_asset = old_asset
        elif unmapped == "cash":
            new_asset = "_CASH"
        else:
            raise KeyError(
                f"No mapping for asset {old_asset!r}. Add it to mapping JSON, "
                "or use --unmapped keep/cash."
            )

        out[new_asset] = out.get(new_asset, 0.0) + float(weight)

    return normalize_weights_or_cash(out)


def full_switch_turnover(current_weights: Dict[str, float], target_weights: Dict[str, float]) -> float:
    assets = set(current_weights.keys()) | set(target_weights.keys())
    return 0.5 * sum(abs(float(current_weights.get(a, 0.0)) - float(target_weights.get(a, 0.0))) for a in assets)


def full_switch_operations(current_weights: Dict[str, float], target_weights: Dict[str, float]) -> int:
    current_assets = [a for a, w in current_weights.items() if a != "_CASH" and abs(float(w)) > EPS]
    target_assets = [a for a, w in target_weights.items() if a != "_CASH" and abs(float(w)) > EPS]
    return len(current_assets) + len(target_assets)


def apply_month_return(weights_for_month: Dict[str, float], returns_row: pd.Series) -> Tuple[float, Dict[str, float]]:
    portfolio_return = 0.0

    for asset, weight in weights_for_month.items():
        if asset == "_CASH":
            continue
        if asset not in returns_row.index:
            raise KeyError(f"Asset {asset!r} missing in returns file columns")
        asset_ret = returns_row.get(asset, np.nan)
        if pd.isna(asset_ret):
            raise ValueError(f"Missing monthly return for asset {asset!r} on {returns_row.name}")
        portfolio_return += float(weight) * float(asset_ret)

    denom = 1.0 + portfolio_return
    if abs(denom) <= EPS:
        raise ValueError(f"Portfolio return produced zero denominator on {returns_row.name}")

    next_weights: Dict[str, float] = {}
    for asset, weight in weights_for_month.items():
        if asset == "_CASH":
            grown = float(weight)
        else:
            grown = float(weight) * (1.0 + float(returns_row[asset]))
        next_weights[asset] = grown / denom

    return float(portfolio_return), normalize_weights_or_cash(next_weights)


def apply_annual_tax_if_year_end(
    dt: pd.Timestamp,
    equity_before_tax: float,
    tax_base_equity: float,
    annual_tax_rate: float,
) -> tuple[float, float, float, int, float]:
    if annual_tax_rate <= 0.0:
        return equity_before_tax, 0.0, 0.0, 0, tax_base_equity
    if dt.month != 12:
        return equity_before_tax, 0.0, 0.0, 0, tax_base_equity

    taxable_profit = max(0.0, equity_before_tax - tax_base_equity)
    tax_amount = taxable_profit * annual_tax_rate
    equity_after_tax = equity_before_tax - tax_amount
    next_tax_base_equity = max(tax_base_equity, equity_after_tax)

    return equity_after_tax, tax_amount, taxable_profit, int(tax_amount > 0.0), next_tax_base_equity


def annualized_return(monthly_returns: pd.Series) -> float:
    r = monthly_returns.dropna()
    if len(r) == 0:
        return np.nan
    total = float((1.0 + r).prod())
    years = len(r) / 12.0
    if years <= 0:
        return np.nan
    if total <= 0:
        return -1.0
    return total ** (1.0 / years) - 1.0


def annualized_vol(monthly_returns: pd.Series) -> float:
    r = monthly_returns.dropna()
    if len(r) < 2:
        return np.nan
    return float(r.std(ddof=1) * np.sqrt(12.0))


def sharpe_ratio(monthly_returns: pd.Series) -> float:
    r = monthly_returns.dropna()
    if len(r) < 2:
        return np.nan
    vol = r.std(ddof=1)
    if vol <= EPS:
        return np.nan
    return float(r.mean() / vol * np.sqrt(12.0))


def max_drawdown_from_returns(monthly_returns: pd.Series) -> float:
    r = monthly_returns.dropna()
    if len(r) == 0:
        return np.nan
    equity = (1.0 + r).cumprod()
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min())


def total_return(monthly_returns: pd.Series) -> float:
    r = monthly_returns.dropna()
    if len(r) == 0:
        return np.nan
    return float((1.0 + r).prod() - 1.0)


def drawdown_duration_stats(monthly_returns: pd.Series) -> Dict[str, Any]:
    r = monthly_returns.dropna()
    if len(r) == 0:
        return {
            "max_drawdown": np.nan,
            "max_drawdown_start": None,
            "max_drawdown_bottom": None,
            "max_drawdown_recovery": None,
            "max_drawdown_duration_months": np.nan,
            "max_time_underwater_months": np.nan,
            "avg_time_underwater_months": np.nan,
            "num_underwater_periods": 0,
            "current_underwater_months": 0,
        }

    equity = (1.0 + r).cumprod()
    peak = equity.cummax()
    dd = equity / peak - 1.0

    max_dd = float(dd.min())
    bottom_date = dd.idxmin()

    peak_before_bottom = equity.loc[:bottom_date].cummax()
    peak_value_at_bottom = peak_before_bottom.loc[bottom_date]
    peak_dates = peak_before_bottom[peak_before_bottom == peak_value_at_bottom].index
    start_date = peak_dates[0]

    recovery_date = None
    after_bottom = equity.loc[bottom_date:]
    recovered = after_bottom[after_bottom >= peak_value_at_bottom]
    if len(recovered) > 0:
        recovery_date = recovered.index[0]

    if recovery_date is not None:
        max_dd_duration = len(equity.loc[start_date:recovery_date]) - 1
    else:
        max_dd_duration = len(equity.loc[start_date:]) - 1

    underwater = dd < -EPS
    durations: List[int] = []
    current = 0
    for is_underwater in underwater:
        if is_underwater:
            current += 1
        else:
            if current > 0:
                durations.append(current)
                current = 0
    current_underwater_months = current
    if current > 0:
        durations.append(current)

    return {
        "max_drawdown": max_dd,
        "max_drawdown_start": start_date.strftime("%Y-%m-%d"),
        "max_drawdown_bottom": bottom_date.strftime("%Y-%m-%d"),
        "max_drawdown_recovery": recovery_date.strftime("%Y-%m-%d") if recovery_date is not None else None,
        "max_drawdown_duration_months": int(max_dd_duration),
        "max_time_underwater_months": int(max(durations)) if durations else 0,
        "avg_time_underwater_months": float(np.mean(durations)) if durations else 0.0,
        "num_underwater_periods": int(len(durations)),
        "current_underwater_months": int(current_underwater_months),
    }


def summarize_underwater_periods(strategy_name: str, benchmark_asset: str, monthly: pd.DataFrame) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    series_specs = [("strategy", monthly["net_return"]), ("benchmark", monthly["benchmark_return"])]

    for series_type, returns in series_specs:
        r = returns.dropna()
        if r.empty:
            continue

        equity = (1.0 + r).cumprod()
        peak = equity.cummax()
        dd = equity / peak - 1.0
        in_underwater = False
        start_date = None
        bottom_date = None
        bottom_dd = 0.0
        start_equity = None
        bottom_equity = None
        dates = list(equity.index)

        for dt in dates:
            current_dd = float(dd.loc[dt])
            current_equity = float(equity.loc[dt])
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
                duration_months = (dt.year - start_date.year) * 12 + (dt.month - start_date.month)
                months_to_bottom = (bottom_date.year - start_date.year) * 12 + (bottom_date.month - start_date.month)
                out.append({
                    "strategy": strategy_name,
                    "benchmark": benchmark_asset,
                    "series_type": series_type,
                    "underwater_start": start_date.strftime("%Y-%m-%d"),
                    "underwater_bottom": bottom_date.strftime("%Y-%m-%d"),
                    "underwater_recovery": dt.strftime("%Y-%m-%d"),
                    "duration_months": int(duration_months),
                    "months_to_bottom": int(months_to_bottom),
                    "months_to_recovery": int(duration_months),
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
            duration_months = (last_dt.year - start_date.year) * 12 + (last_dt.month - start_date.month)
            months_to_bottom = (bottom_date.year - start_date.year) * 12 + (bottom_date.month - start_date.month)
            out.append({
                "strategy": strategy_name,
                "benchmark": benchmark_asset,
                "series_type": series_type,
                "underwater_start": start_date.strftime("%Y-%m-%d"),
                "underwater_bottom": bottom_date.strftime("%Y-%m-%d"),
                "underwater_recovery": None,
                "duration_months": int(duration_months),
                "months_to_bottom": int(months_to_bottom),
                "months_to_recovery": None,
                "max_drawdown": float(bottom_dd),
                "start_equity": float(start_equity),
                "bottom_equity": float(bottom_equity),
                "recovery_equity": None,
                "is_recovered": 0,
            })

    return out


def summarize_period(
    strategy_name: str,
    benchmark_asset: str,
    monthly: pd.DataFrame,
    period_type: str,
    period_name: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> Dict[str, Any] | None:
    sub = monthly.loc[(monthly.index >= start) & (monthly.index <= end)].copy()
    if sub.empty:
        return None

    returns = sub["net_return"].dropna()
    bench = sub["benchmark_return"].dropna()
    common_index = returns.index.intersection(bench.index)
    if len(common_index) == 0:
        return None

    returns = returns.loc[common_index]
    bench = bench.loc[common_index]
    data = sub.loc[common_index]
    strategy_dd_stats = drawdown_duration_stats(returns)
    benchmark_dd_stats = drawdown_duration_stats(bench)

    row: Dict[str, Any] = {
        "strategy": strategy_name,
        "benchmark": benchmark_asset,
        "period_type": period_type,
        "period_name": period_name,
        "start": common_index.min().strftime("%Y-%m-%d"),
        "end": common_index.max().strftime("%Y-%m-%d"),
        "months": int(len(common_index)),
        "total_return": total_return(returns),
        "cagr": annualized_return(returns),
        "ann_vol": annualized_vol(returns),
        "sharpe": sharpe_ratio(returns),
        "max_drawdown": max_drawdown_from_returns(returns),
        "final_equity": float((1.0 + returns).cumprod().iloc[-1]),
        "avg_monthly_turnover": float(data["turnover"].mean()),
        "total_turnover": float(data["turnover"].sum()),
        "total_operations": int(data["operations"].sum()),
        "avg_operations_per_month": float(data["operations"].mean()),
        "benchmark_total_return": total_return(bench),
        "benchmark_cagr": annualized_return(bench),
        "benchmark_ann_vol": annualized_vol(bench),
        "benchmark_sharpe": sharpe_ratio(bench),
        "benchmark_max_drawdown": max_drawdown_from_returns(bench),
        "benchmark_final_equity": float((1.0 + bench).cumprod().iloc[-1]),
        "total_return_vs_benchmark": total_return(returns) - total_return(bench),
        "cagr_vs_benchmark": annualized_return(returns) - annualized_return(bench),
        "sharpe_vs_benchmark": sharpe_ratio(returns) - sharpe_ratio(bench),
        "maxdd_vs_benchmark": max_drawdown_from_returns(returns) - max_drawdown_from_returns(bench),
        "avg_monthly_excess": float((returns - bench).mean()),
        "hit_rate_excess": float((returns > bench).mean()),
        "cum_excess_sum": float((returns - bench).sum()),
    }

    for prefix, stats in [("", strategy_dd_stats), ("benchmark_", benchmark_dd_stats)]:
        row[f"{prefix}max_drawdown_start"] = stats["max_drawdown_start"]
        row[f"{prefix}max_drawdown_bottom"] = stats["max_drawdown_bottom"]
        row[f"{prefix}max_drawdown_recovery"] = stats["max_drawdown_recovery"]
        row[f"{prefix}max_drawdown_duration_months"] = stats["max_drawdown_duration_months"]
        row[f"{prefix}max_time_underwater_months"] = stats["max_time_underwater_months"]
        row[f"{prefix}avg_time_underwater_months"] = stats["avg_time_underwater_months"]
        row[f"{prefix}num_underwater_periods"] = stats["num_underwater_periods"]
        row[f"{prefix}current_underwater_months"] = stats["current_underwater_months"]

    return row


def summarize_rolling_windows(
    strategy_name: str,
    benchmark_asset: str,
    monthly: pd.DataFrame,
    window_months_list: Iterable[int],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for window_months in window_months_list:
        window_months = int(window_months)
        if len(monthly) < window_months:
            continue

        rows = []
        for i in range(len(monthly) - window_months + 1):
            sub = monthly.iloc[i:i + window_months].copy()
            returns = sub["net_return"]
            bench = sub["benchmark_return"]
            row = {
                "start": sub.index.min(),
                "end": sub.index.max(),
                "strategy_total_return": total_return(returns),
                "benchmark_total_return": total_return(bench),
                "strategy_cagr": annualized_return(returns),
                "benchmark_cagr": annualized_return(bench),
                "strategy_sharpe": sharpe_ratio(returns),
                "benchmark_sharpe": sharpe_ratio(bench),
                "strategy_max_drawdown": max_drawdown_from_returns(returns),
                "benchmark_max_drawdown": max_drawdown_from_returns(bench),
                "avg_monthly_excess": float((returns - bench).mean()),
                "hit_rate_excess": float((returns > bench).mean()),
            }
            row["total_return_vs_benchmark"] = row["strategy_total_return"] - row["benchmark_total_return"]
            row["cagr_vs_benchmark"] = row["strategy_cagr"] - row["benchmark_cagr"]
            row["sharpe_vs_benchmark"] = row["strategy_sharpe"] - row["benchmark_sharpe"]
            row["maxdd_vs_benchmark"] = row["strategy_max_drawdown"] - row["benchmark_max_drawdown"]
            rows.append(row)

        df = pd.DataFrame(rows)
        out.append({
            "strategy": strategy_name,
            "benchmark": benchmark_asset,
            "window_months": window_months,
            "n_windows": int(len(df)),
            "pct_windows_total_return_beats_benchmark": float((df["total_return_vs_benchmark"] > 0).mean()),
            "pct_windows_cagr_beats_benchmark": float((df["cagr_vs_benchmark"] > 0).mean()),
            "pct_windows_sharpe_beats_benchmark": float((df["sharpe_vs_benchmark"] > 0).mean()),
            "pct_windows_lower_dd_than_benchmark": float((df["maxdd_vs_benchmark"] > 0).mean()),
            "median_strategy_total_return": float(df["strategy_total_return"].median()),
            "median_benchmark_total_return": float(df["benchmark_total_return"].median()),
            "median_total_return_vs_benchmark": float(df["total_return_vs_benchmark"].median()),
            "median_strategy_cagr": float(df["strategy_cagr"].median()),
            "median_benchmark_cagr": float(df["benchmark_cagr"].median()),
            "median_cagr_vs_benchmark": float(df["cagr_vs_benchmark"].median()),
            "worst_total_return_vs_benchmark": float(df["total_return_vs_benchmark"].min()),
            "best_total_return_vs_benchmark": float(df["total_return_vs_benchmark"].max()),
            "worst_cagr_vs_benchmark": float(df["cagr_vs_benchmark"].min()),
            "best_cagr_vs_benchmark": float(df["cagr_vs_benchmark"].max()),
            "worst_strategy_max_drawdown": float(df["strategy_max_drawdown"].min()),
            "worst_benchmark_max_drawdown": float(df["benchmark_max_drawdown"].min()),
            "median_hit_rate_excess": float(df["hit_rate_excess"].median()),
            "median_avg_monthly_excess": float(df["avg_monthly_excess"].median()),
        })

    return out


def compute_rolling_windows_detail(
    strategy_name: str,
    benchmark_asset: str,
    monthly_df: pd.DataFrame,
    windows: Iterable[int],
) -> pd.DataFrame:
    df = monthly_df.copy().sort_index()
    rows: List[Dict[str, Any]] = []

    for window in windows:
        window = int(window)
        if len(df) < window:
            continue
        for start_idx in range(0, len(df) - window + 1):
            end_idx = start_idx + window - 1
            chunk = df.iloc[start_idx:end_idx + 1].copy()
            returns = chunk["net_return"].dropna()
            bench = chunk["benchmark_return"].dropna()
            common_index = returns.index.intersection(bench.index)
            if len(common_index) < window:
                continue
            returns = returns.loc[common_index]
            bench = bench.loc[common_index]
            chunk = chunk.loc[common_index]

            strategy_cagr = annualized_return(returns)
            benchmark_cagr = annualized_return(bench)
            strategy_sharpe = sharpe_ratio(returns)
            benchmark_sharpe = sharpe_ratio(bench)
            strategy_max_dd = max_drawdown_from_returns(returns)
            benchmark_max_dd = max_drawdown_from_returns(bench)
            strategy_total_ret = total_return(returns)
            benchmark_total_ret = total_return(bench)

            rows.append({
                "strategy": strategy_name,
                "benchmark": benchmark_asset,
                "window_months": int(window),
                "window_start": common_index.min().strftime("%Y-%m-%d"),
                "window_end": common_index.max().strftime("%Y-%m-%d"),
                "strategy_total_return": strategy_total_ret,
                "benchmark_total_return": benchmark_total_ret,
                "total_return_vs_benchmark": strategy_total_ret - benchmark_total_ret,
                "strategy_cagr": strategy_cagr,
                "benchmark_cagr": benchmark_cagr,
                "cagr_vs_benchmark": strategy_cagr - benchmark_cagr,
                "strategy_sharpe": strategy_sharpe,
                "benchmark_sharpe": benchmark_sharpe,
                "sharpe_vs_benchmark": strategy_sharpe - benchmark_sharpe,
                "strategy_max_drawdown": strategy_max_dd,
                "benchmark_max_drawdown": benchmark_max_dd,
                "maxdd_vs_benchmark": strategy_max_dd - benchmark_max_dd,
                "strategy_final_equity": float((1.0 + returns).prod()),
                "benchmark_final_equity": float((1.0 + bench).prod()),
                "avg_monthly_excess": float((returns - bench).mean()),
                "hit_rate_excess": float((returns > bench).mean()),
                "avg_turnover": float(chunk["turnover"].mean()),
                "total_turnover": float(chunk["turnover"].sum()),
                "total_operations": int(chunk["operations"].sum()),
                "avg_operations_per_month": float(chunk["operations"].mean()),
                "months_in_cash": int(chunk["weights_used_json"].astype(str).str.contains("_CASH").sum()),
            })

    return pd.DataFrame(rows)


def summarize_equity_checkpoints(
    strategy_name: str,
    benchmark_asset: str,
    monthly: pd.DataFrame,
    checkpoints: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for cp in checkpoints:
        start = pd.Timestamp(cp["start"])
        end = pd.Timestamp(cp["end"])
        name = str(cp["name"] if "name" in cp else cp["checkpoint_name"])
        sub = monthly.loc[(monthly.index >= start) & (monthly.index <= end)].copy()
        if sub.empty:
            continue
        strategy_equity = float((1.0 + sub["net_return"]).cumprod().iloc[-1])
        benchmark_equity = float((1.0 + sub["benchmark_return"]).cumprod().iloc[-1])
        out.append({
            "strategy": strategy_name,
            "benchmark": benchmark_asset,
            "checkpoint_name": name,
            "start": sub.index.min().strftime("%Y-%m-%d"),
            "end": sub.index.max().strftime("%Y-%m-%d"),
            "months": int(len(sub)),
            "strategy_equity_multiple": strategy_equity,
            "benchmark_equity_multiple": benchmark_equity,
            "equity_ratio_strategy_vs_benchmark": strategy_equity / benchmark_equity if benchmark_equity > EPS else np.nan,
            "strategy_total_return": strategy_equity - 1.0,
            "benchmark_total_return": benchmark_equity - 1.0,
            "strategy_cagr": annualized_return(sub["net_return"]),
            "benchmark_cagr": annualized_return(sub["benchmark_return"]),
            "strategy_max_drawdown": max_drawdown_from_returns(sub["net_return"]),
            "benchmark_max_drawdown": max_drawdown_from_returns(sub["benchmark_return"]),
        })
    return out


def build_holdings_export(monthly: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for dt, row in monthly.iterrows():
        weights = parse_json_obj(row["weights_used_json"])
        for asset, weight in weights.items():
            if abs(float(weight)) <= EPS:
                continue
            rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "strategy": row["strategy"],
                "asset": asset,
                "weight": float(weight),
                "signal_changed_source": int(row.get("signal_changed_source", 0)),
                "rebalanced": int(row.get("rebalanced", 0)),
                "turnover": float(row.get("turnover", 0.0)),
                "operations": int(row.get("operations", 0)),
            })
    return pd.DataFrame(rows)


def build_trades_export(monthly: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for dt, row in monthly.iterrows():
        before = parse_json_obj(row["weights_before_trade_json"])
        after = parse_json_obj(row["weights_used_json"])
        assets = sorted(set(before.keys()) | set(after.keys()))
        for asset in assets:
            b = float(before.get(asset, 0.0))
            a = float(after.get(asset, 0.0))
            delta = a - b
            if abs(delta) <= EPS:
                continue
            rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "strategy": row["strategy"],
                "asset": asset,
                "weight_before_trade": b,
                "weight_after_trade": a,
                "trade_weight_delta": delta,
                "side": "BUY" if delta > 0 else "SELL",
                "signal_changed_source": int(row.get("signal_changed_source", 0)),
                "rebalanced": int(row.get("rebalanced", 0)),
                "turnover": float(row.get("turnover", 0.0)),
                "trade_cost": float(row.get("trade_cost", 0.0)),
            })
    return pd.DataFrame(rows)


def replay_mapped_monthly(
    source_monthly: pd.DataFrame,
    returns_df: pd.DataFrame,
    mapping: Dict[str, str],
    benchmark_asset: str,
    strategy_name: str,
    transaction_cost_bps_one_way: float,
    annual_tax_rate: float,
    execution_mode: str,
    unmapped: str,
) -> pd.DataFrame:
    cost_rate = float(transaction_cost_bps_one_way) / 10000.0
    current_weights: Dict[str, float] = {"_CASH": 1.0}
    equity_value = 1.0
    tax_base_equity = 1.0
    last_target_signature = None
    records: List[Dict[str, Any]] = []

    common_dates = [dt for dt in source_monthly.index if dt in returns_df.index]
    if not common_dates:
        raise ValueError("No overlapping dates between source monthly and new returns file")

    for idx, dt in enumerate(common_dates):
        src_row = source_monthly.loc[dt]
        returns_row = returns_df.loc[dt]
        if pd.isna(returns_row.get(benchmark_asset, np.nan)):
            continue

        source_weights = parse_json_obj(src_row["weights_used_json"])
        target_weights = map_weights(source_weights, mapping=mapping, unmapped=unmapped)
        target_signature = normalize_signature(target_weights)
        signal_changed_source = int(src_row.get("signal_changed", 1 if idx == 0 else 0))

        if execution_mode == "signal_changed":
            rebalanced = idx == 0 or signal_changed_source == 1
        elif execution_mode == "target_each_month":
            rebalanced = True
        elif execution_mode == "target_when_changed":
            rebalanced = idx == 0 or target_signature != last_target_signature
        else:
            raise ValueError(f"Unknown execution_mode: {execution_mode}")

        weights_before_trade = current_weights.copy()

        if rebalanced:
            turnover = full_switch_turnover(current_weights, target_weights)
            operations = full_switch_operations(current_weights, target_weights)
            trade_cost = turnover * cost_rate
            weights_for_month = target_weights.copy()
            last_target_signature = target_signature
        else:
            turnover = 0.0
            operations = 0
            trade_cost = 0.0
            weights_for_month = current_weights.copy()

        gross_return, next_weights = apply_month_return(weights_for_month, returns_row)
        net_return_before_tax = (1.0 + gross_return) * (1.0 - trade_cost) - 1.0

        equity_before_tax = equity_value * (1.0 + net_return_before_tax)
        tax_base_before = tax_base_equity
        equity_after_tax, tax_amount, taxable_profit, tax_event, tax_base_equity = apply_annual_tax_if_year_end(
            dt=dt,
            equity_before_tax=equity_before_tax,
            tax_base_equity=tax_base_equity,
            annual_tax_rate=annual_tax_rate,
        )
        net_return = equity_after_tax / equity_value - 1.0
        equity_value = equity_after_tax
        current_weights = next_weights

        records.append({
            "date": dt,
            "strategy": strategy_name,
            "execution_mode": execution_mode,
            "source_weights_json": json.dumps(source_weights, ensure_ascii=False),
            "mapped_target_weights_json": json.dumps(target_weights, ensure_ascii=False),
            "weights_before_trade_json": json.dumps(weights_before_trade, ensure_ascii=False),
            "weights_used_json": json.dumps(weights_for_month, ensure_ascii=False),
            "next_weights_json": json.dumps(current_weights, ensure_ascii=False),
            "signal_changed_source": int(signal_changed_source),
            "rebalanced": int(rebalanced),
            "turnover": float(turnover),
            "operations": int(operations),
            "trade_cost": float(trade_cost),
            "gross_return": float(gross_return),
            "net_return_before_tax": float(net_return_before_tax),
            "taxable_profit_year": float(taxable_profit),
            "tax_amount": float(tax_amount),
            "tax_event": int(tax_event),
            "tax_base_before": float(tax_base_before),
            "tax_base_after": float(tax_base_equity),
            "net_return": float(net_return),
            "equity_before_tax": float(equity_before_tax),
            "equity": float(equity_value),
            "benchmark_return": float(returns_row[benchmark_asset]),
        })

    monthly = pd.DataFrame(records)
    if monthly.empty:
        raise ValueError("Replay produced no monthly rows")
    monthly = monthly.set_index("date").sort_index()
    monthly["benchmark_equity"] = (1.0 + monthly["benchmark_return"]).cumprod()
    monthly["excess_return"] = monthly["net_return"] - monthly["benchmark_return"]
    return monthly


def read_config_if_any(path: str | None) -> Dict[str, Any]:
    if not path:
        return {}
    with Path(path).open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def save_csv(df: pd.DataFrame, path: Path, include_index: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=include_index, float_format="%.10f")
    print(f"[OK] saved: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay an existing strategy monthly file on mapped tickers and new returns."
    )
    parser.add_argument("--monthly", required=True, help="Source *_monthly.csv from the original backtest")
    parser.add_argument("--returns", required=True, help="Wide CSV with new monthly returns, date index in first column")
    parser.add_argument("--mapping", required=True, help="JSON mapping: old_ticker -> new_ticker")
    parser.add_argument("--benchmark", required=True, help="Benchmark ticker/column in the new returns file")
    parser.add_argument("--out-dir", default="mapped_replay_output")
    parser.add_argument("--strategy-name", default=None)
    parser.add_argument("--config", default=None, help="Optional original config JSON for windows/periods/checkpoints/cost/tax")
    parser.add_argument("--transaction-cost-bps-one-way", type=float, default=None)
    parser.add_argument("--annual-tax-rate", type=float, default=None)
    parser.add_argument(
        "--windows",
        default=None,
        help="Comma-separated rolling windows, e.g. 12,24,36,48,60,84,120,180",
    )
    parser.add_argument(
        "--execution-mode",
        choices=["signal_changed", "target_each_month", "target_when_changed"],
        default="signal_changed",
        help=(
            "signal_changed: rebalance only when source monthly says signal_changed=1; "
            "target_each_month: rebalance to mapped source weights every month; "
            "target_when_changed: rebalance when mapped target signature changes."
        ),
    )
    parser.add_argument(
        "--unmapped",
        choices=["error", "keep", "cash"],
        default="error",
        help="What to do if source asset is absent from mapping JSON",
    )
    args = parser.parse_args()

    config = read_config_if_any(args.config)

    monthly_source = load_monthly_csv(args.monthly)
    returns_df = load_wide_csv(args.returns)
    mapping = load_mapping(args.mapping)
    
    # START TESTU UK
    # speq.uk masz dopiero od 2021-05-10, więc bezpieczniej zacząć od pełnego miesiąca:
    START_DATE = pd.Timestamp("2021-06-01")
    # ewentualnie bardziej konserwatywnie:
    # START_DATE = pd.Timestamp("2021-07-01")
    
    monthly_source = monthly_source.loc[monthly_source.index >= START_DATE].copy()
    returns_df = returns_df.loc[returns_df.index >= START_DATE].copy()

    strategy_name = args.strategy_name
    if strategy_name is None:
        if "strategy" in monthly_source.columns and monthly_source["strategy"].notna().any():
            strategy_name = str(monthly_source["strategy"].dropna().iloc[0]) + "__mapped_replay"
        else:
            strategy_name = Path(args.monthly).stem + "__mapped_replay"

    transaction_cost = (
        float(args.transaction_cost_bps_one_way)
        if args.transaction_cost_bps_one_way is not None
        else float(config.get("transaction_cost_bps_one_way", 0.0))
    )
    annual_tax_rate = (
        float(args.annual_tax_rate)
        if args.annual_tax_rate is not None
        else float(config.get("annual_tax_rate", 0.0))
    )

    if args.windows:
        rolling_windows = [int(x.strip()) for x in args.windows.split(",") if x.strip()]
    else:
        rolling_windows = list(config.get("rolling_windows_months", [12, 24, 36, 48, 60, 84, 120, 180]))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    monthly = replay_mapped_monthly(
        source_monthly=monthly_source,
        returns_df=returns_df,
        mapping=mapping,
        benchmark_asset=args.benchmark,
        strategy_name=strategy_name,
        transaction_cost_bps_one_way=transaction_cost,
        annual_tax_rate=annual_tax_rate,
        execution_mode=args.execution_mode,
        unmapped=args.unmapped,
    )

    monthly_reset = monthly.reset_index()
    save_csv(monthly_reset, out_dir / "replayed_monthly.csv")
    save_csv(build_holdings_export(monthly), out_dir / "replayed_holdings.csv")
    save_csv(build_trades_export(monthly), out_dir / "replayed_trades.csv")

    full_row = summarize_period(
        strategy_name=strategy_name,
        benchmark_asset=args.benchmark,
        monthly=monthly,
        period_type="full",
        period_name="FULL",
        start=monthly.index.min(),
        end=monthly.index.max(),
    )
    summary_full = pd.DataFrame([full_row]) if full_row else pd.DataFrame()
    if not summary_full.empty:
        save_csv(summary_full, out_dir / "summary_full_period.csv")

    named_rows: List[Dict[str, Any]] = []
    for item in config.get("named_periods", []):
        row = summarize_period(
            strategy_name=strategy_name,
            benchmark_asset=args.benchmark,
            monthly=monthly,
            period_type="named_period",
            period_name=str(item["name"]),
            start=pd.Timestamp(item["start"]),
            end=pd.Timestamp(item["end"]),
        )
        if row is not None:
            named_rows.append(row)
    summary_named = pd.DataFrame(named_rows)
    if not summary_named.empty:
        summary_named = summary_named.sort_values(["period_name", "sharpe", "cagr"], ascending=[True, False, False])
        save_csv(summary_named, out_dir / "summary_named_periods.csv")

    summary_rolling = pd.DataFrame(
        summarize_rolling_windows(
            strategy_name=strategy_name,
            benchmark_asset=args.benchmark,
            monthly=monthly,
            window_months_list=rolling_windows,
        )
    )
    if not summary_rolling.empty:
        summary_rolling = summary_rolling.sort_values(
            ["window_months", "median_cagr_vs_benchmark", "pct_windows_cagr_beats_benchmark"],
            ascending=[True, False, False],
        )
        save_csv(summary_rolling, out_dir / "summary_rolling.csv")

    rolling_detail = compute_rolling_windows_detail(
        strategy_name=strategy_name,
        benchmark_asset=args.benchmark,
        monthly_df=monthly,
        windows=rolling_windows,
    )
    if not rolling_detail.empty:
        rolling_detail = rolling_detail.sort_values(["window_months", "cagr_vs_benchmark"], ascending=[True, True])
        save_csv(rolling_detail, out_dir / "rolling_windows_detail.csv")
        save_csv(rolling_detail.sort_values("cagr_vs_benchmark").head(100), out_dir / "worst_rolling_windows.csv")
        worst_by_window = (
            rolling_detail
            .sort_values(["window_months", "cagr_vs_benchmark"], ascending=[True, True])
            .groupby("window_months", as_index=False)
            .head(20)
        )
        save_csv(worst_by_window, out_dir / "worst_rolling_windows_by_window.csv")

    checkpoint_rows = summarize_equity_checkpoints(
        strategy_name=strategy_name,
        benchmark_asset=args.benchmark,
        monthly=monthly,
        checkpoints=list(config.get("equity_checkpoints", [])),
    )
    summary_checkpoints = pd.DataFrame(checkpoint_rows)
    if not summary_checkpoints.empty:
        summary_checkpoints = summary_checkpoints.sort_values(
            ["checkpoint_name", "equity_ratio_strategy_vs_benchmark"], ascending=[True, False]
        )
        save_csv(summary_checkpoints, out_dir / "summary_equity_checkpoints.csv")

    underwater_rows = summarize_underwater_periods(
        strategy_name=strategy_name,
        benchmark_asset=args.benchmark,
        monthly=monthly,
    )
    summary_underwater = pd.DataFrame(underwater_rows)
    if not summary_underwater.empty:
        summary_underwater = summary_underwater.sort_values(
            ["strategy", "series_type", "duration_months", "max_drawdown"],
            ascending=[True, True, False, True],
        )
        save_csv(summary_underwater, out_dir / "summary_underwater_periods.csv")

    print("\n=== SUMMARY FULL PERIOD ===")
    with pd.option_context("display.max_columns", None, "display.width", 220):
        print(summary_full)

    if not summary_rolling.empty:
        print("\n=== SUMMARY ROLLING ===")
        with pd.option_context("display.max_columns", None, "display.width", 220):
            print(summary_rolling)


if __name__ == "__main__":
    main()
