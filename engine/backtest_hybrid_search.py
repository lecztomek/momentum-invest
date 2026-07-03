from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd


EPS = 1e-12


def is_full_cash_weights(weights: Dict[str, float]) -> bool:
    return (
        isinstance(weights, dict)
        and len(weights) == 1
        and abs(float(weights.get("_CASH", 0.0)) - 1.0) <= EPS
    )


def get_wide_signal_value(
    signal_exec_map: Dict[str, pd.DataFrame],
    signal_name: str,
    dt: pd.Timestamp,
    asset: str,
) -> float:
    if signal_name not in signal_exec_map:
        return np.nan

    signal_df = signal_exec_map[signal_name]

    if dt not in signal_df.index:
        return np.nan

    if asset not in signal_df.columns:
        return np.nan

    value = signal_df.loc[dt, asset]

    if pd.isna(value):
        return np.nan

    return float(value)


def trigger_condition_passes(value: float, operator: str, threshold: float) -> bool:
    if pd.isna(value):
        return False

    if operator == ">":
        return value > threshold
    if operator == ">=":
        return value >= threshold
    if operator == "<":
        return value < threshold
    if operator == "<=":
        return value <= threshold

    raise ValueError(f"Nieznany trigger_operator: {operator}")


def apply_rebound_starter(
    strategy: Dict[str, Any],
    desired_target_weights: Dict[str, float],
    dt: pd.Timestamp,
    signal_exec_map: Dict[str, pd.DataFrame],
) -> tuple[Dict[str, float], Dict[str, Any]]:
    cfg = strategy.get("rebound_starter", {})

    diag = {
        "rebound_starter_active": 0,
        "rebound_signal_name": None,
        "rebound_trigger_asset": None,
        "rebound_trigger_value": np.nan,
        "rebound_trigger_threshold": np.nan,
    }

    if not bool(cfg.get("enabled", False)):
        return desired_target_weights, diag

    only_when_full_cash = bool(cfg.get("only_when_full_cash", True))

    if only_when_full_cash and not is_full_cash_weights(desired_target_weights):
        return desired_target_weights, diag

    signal_name = str(cfg["signal_name"])
    trigger_asset = str(cfg["trigger_asset"])
    operator = str(cfg.get("trigger_operator", ">"))
    threshold = float(cfg["trigger_threshold"])

    trigger_value = get_wide_signal_value(
        signal_exec_map=signal_exec_map,
        signal_name=signal_name,
        dt=dt,
        asset=trigger_asset,
    )

    diag.update({
        "rebound_signal_name": signal_name,
        "rebound_trigger_asset": trigger_asset,
        "rebound_trigger_value": trigger_value,
        "rebound_trigger_threshold": threshold,
    })

    if not trigger_condition_passes(trigger_value, operator, threshold):
        return desired_target_weights, diag

    target_weights = normalize_weights_or_cash(
        dict(cfg.get("target_weights", {}))
    )

    diag["rebound_starter_active"] = 1

    return target_weights, diag


def compute_rolling_windows_detail(
    strategy_name: str,
    benchmark_asset: str,
    monthly_df: pd.DataFrame,
    strategy_col: str = "net_return",
    benchmark_col: str = "benchmark_return",
    windows: tuple[int, ...] = (12, 24, 36, 48, 60, 84, 120, 180),
) -> pd.DataFrame:
    """
    Zwraca każde rolling window osobno, żeby zobaczyć najgorsze okresy strategii vs benchmark.

    Uwaga:
    - monthly_df u Ciebie ma datę w indeksie, nie w kolumnie date.
    - Funkcja zakłada miesięczne zwroty strategii i benchmarku.
    """

    df = monthly_df.copy()
    df = df.sort_index()

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    rows = []

    for window in windows:
        if len(df) < window:
            continue

        for start_idx in range(0, len(df) - window + 1):
            end_idx = start_idx + window - 1
            chunk = df.iloc[start_idx:end_idx + 1].copy()

            returns = chunk[strategy_col].dropna()
            bench = chunk[benchmark_col].dropna()
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

            strategy_growth = float((1.0 + returns).prod())
            benchmark_growth = float((1.0 + bench).prod())

            rows.append({
                "strategy": strategy_name,
                "benchmark": benchmark_asset,
                "window_months": int(window),
                "window_start": common_index.min().strftime("%Y-%m-%d"),
                "window_end": common_index.max().strftime("%Y-%m-%d"),
                "strategy_cagr": strategy_cagr,
                "benchmark_cagr": benchmark_cagr,
                "cagr_vs_benchmark": strategy_cagr - benchmark_cagr,
                "strategy_sharpe": strategy_sharpe,
                "benchmark_sharpe": benchmark_sharpe,
                "sharpe_vs_benchmark": strategy_sharpe - benchmark_sharpe,
                "strategy_max_drawdown": strategy_max_dd,
                "benchmark_max_drawdown": benchmark_max_dd,
                "maxdd_vs_benchmark": strategy_max_dd - benchmark_max_dd,
                "strategy_final_equity": strategy_growth,
                "benchmark_final_equity": benchmark_growth,
                "avg_monthly_excess": float((returns - bench).mean()),
                "hit_rate_excess": float((returns > bench).mean()),

                "avg_turnover": float(chunk["turnover"].mean()) if "turnover" in chunk.columns else np.nan,
                "total_turnover": float(chunk["turnover"].sum()) if "turnover" in chunk.columns else np.nan,
                "total_operations": int(chunk["operations"].sum()) if "operations" in chunk.columns else 0,
                "avg_operations_per_month": float(chunk["operations"].mean()) if "operations" in chunk.columns else np.nan,
                "months_in_cash": int(
                    chunk["weights_used_json"].astype(str).str.contains("_CASH").sum()
                ) if "weights_used_json" in chunk.columns else 0,
                "avg_bad_canaries": float(chunk["bad_canaries"].mean()) if "bad_canaries" in chunk.columns else np.nan,
                "max_bad_canaries": int(chunk["bad_canaries"].max()) if "bad_canaries" in chunk.columns else 0,
            })

    return pd.DataFrame(rows)


def build_rank_weight_target(
    selected_assets: List[str],
    rank_weights: List[float],
) -> Dict[str, float]:
    if not selected_assets:
        return {"_CASH": 1.0}

    usable_weights = rank_weights[:len(selected_assets)]
    if len(usable_weights) == 0:
        return {"_CASH": 1.0}

    total = float(sum(usable_weights))
    if total <= EPS:
        return {"_CASH": 1.0}

    usable_weights = [w / total for w in usable_weights]

    return {
        asset: float(weight)
        for asset, weight in zip(selected_assets, usable_weights)
    }


def load_wide_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0)
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def align_scores_to_execution_month(score_df: pd.DataFrame) -> pd.DataFrame:
    aligned = score_df.copy()
    aligned.index = (aligned.index.to_period("M") + 1).to_timestamp(how="start")
    return aligned


def annualized_return(monthly_returns: pd.Series) -> float:
    r = monthly_returns.dropna()
    if len(r) == 0:
        return np.nan
    total = float((1.0 + r).prod())
    years = len(r) / 12.0
    if years <= 0:
        return np.nan
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
    if vol <= 0:
        return np.nan
    return float(r.mean() / vol * np.sqrt(12.0))


def equity_curve_from_returns(monthly_returns: pd.Series) -> pd.Series:
    r = monthly_returns.dropna()

    if len(r) == 0:
        return pd.Series(dtype=float)

    equity = (1.0 + r).cumprod()

    start_date = r.index[0] - pd.DateOffset(months=1)
    start = pd.Series([1.0], index=[start_date])

    return pd.concat([start, equity])


def max_drawdown_from_returns(monthly_returns: pd.Series) -> float:
    equity = equity_curve_from_returns(monthly_returns)

    if len(equity) == 0:
        return np.nan

    peak = equity.cummax()
    dd = equity / peak - 1.0

    return float(dd.min())


def drawdown_duration_stats(monthly_returns: pd.Series) -> Dict:
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

    equity = equity_curve_from_returns(r)
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

    durations = []
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


def summarize_underwater_periods(
    strategy_name: str,
    benchmark_asset: str,
    monthly: pd.DataFrame,
) -> List[Dict]:
    out: List[Dict] = []

    series_specs = [
        ("strategy", monthly["net_return"]),
        ("benchmark", monthly["benchmark_return"]),
    ]

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

            recovered = current_dd >= -EPS

            if recovered:
                duration_months = (
                    (dt.year - start_date.year) * 12
                    + (dt.month - start_date.month)
                )

                months_to_bottom = (
                    (bottom_date.year - start_date.year) * 12
                    + (bottom_date.month - start_date.month)
                )

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

            duration_months = (
                (last_dt.year - start_date.year) * 12
                + (last_dt.month - start_date.month)
            )

            months_to_bottom = (
                (bottom_date.year - start_date.year) * 12
                + (bottom_date.month - start_date.month)
            )

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


def count_bad_canaries(
    scores: pd.Series,
    canary_assets: List[str],
    threshold: float,
    missing_as_bad: bool,
) -> int:
    bad = 0
    for asset in canary_assets:
        s = scores.get(asset, np.nan)
        if pd.isna(s):
            if missing_as_bad:
                bad += 1
            continue
        if float(s) <= threshold:
            bad += 1
    return bad


def flatten_group_assets(group_set: Dict[str, List[str]], allowed_groups: List[str]) -> List[str]:
    out: List[str] = []
    for group_name in allowed_groups:
        for asset in group_set.get(group_name, []):
            if asset not in out:
                out.append(asset)
    return out


def rank_assets(scores: pd.Series, assets: List[str], returns_row: pd.Series) -> List[str]:
    valid: List[Tuple[str, float]] = []
    for asset in assets:
        s = scores.get(asset, np.nan)
        r = returns_row.get(asset, np.nan)
        if pd.notna(s) and pd.notna(r):
            valid.append((asset, float(s)))
    valid.sort(key=lambda x: (-x[1], x[0]))
    return [asset for asset, _ in valid]


def trailing_compound_return(
    returns_df: pd.DataFrame,
    dt: pd.Timestamp,
    asset: str,
    months: int,
) -> float:
    """
    Liczy trailing return z miesięcy PRZED dt, żeby nie było look-ahead.
    Np. dla dt=2024-05-01 i months=3 bierze 3 ostatnie miesięczne zwroty < dt.
    """
    if months <= 0:
        return np.nan

    if asset not in returns_df.columns:
        return np.nan

    hist = returns_df.loc[returns_df.index < dt, asset].dropna().tail(months)
    if len(hist) < months:
        return np.nan

    return float((1.0 + hist).prod() - 1.0)


def get_gate_score(
    gate: Dict[str, Any],
    asset: str,
    current_score_name: str,
    current_scores: pd.Series,
    score_exec_map: Dict[str, pd.DataFrame],
    dt: pd.Timestamp,
) -> float:
    """
    Gate może używać:
    - bieżącego score strategii,
    - albo osobnego score_name, np. score_ema3_over_ema10.
    """
    gate_score_name = gate.get("score_name")

    if not gate_score_name or str(gate_score_name) == current_score_name:
        return current_scores.get(asset, np.nan)

    gate_score_name = str(gate_score_name)

    if gate_score_name not in score_exec_map:
        return np.nan

    gate_scores_df = score_exec_map[gate_score_name]

    if dt not in gate_scores_df.index:
        return np.nan

    return gate_scores_df.loc[dt].get(asset, np.nan)


def asset_gate_passes(
    asset: str,
    gate: Dict[str, Any],
    dt: pd.Timestamp,
    current_score_name: str,
    current_scores: pd.Series,
    score_exec_map: Dict[str, pd.DataFrame],
    returns_df: pd.DataFrame,
    bad_canaries: int,
) -> bool:
    """
    Zwraca True, jeśli asset może wejść do rankingu.
    Domyślnie gate jest restrykcyjny przy brakach danych, ale można ustawić missing_as_block=false.
    """
    if not bool(gate.get("enabled", True)):
        return True

    missing_as_block = bool(gate.get("missing_as_block", True))

    if bool(gate.get("require_global_canary_ok", False)):
        allowed_bad = int(gate.get("allowed_bad_canaries_max", 0))
        if bad_canaries > allowed_bad:
            return False

    if "min_score" in gate:
        s = get_gate_score(
            gate=gate,
            asset=asset,
            current_score_name=current_score_name,
            current_scores=current_scores,
            score_exec_map=score_exec_map,
            dt=dt,
        )

        if pd.isna(s):
            return not missing_as_block

        if float(s) <= float(gate["min_score"]):
            return False

    if "min_return_1m" in gate:
        r1 = trailing_compound_return(returns_df, dt, asset, 1)
        if pd.isna(r1):
            return not missing_as_block
        if r1 <= float(gate["min_return_1m"]):
            return False

    if "min_return_2m" in gate:
        r2 = trailing_compound_return(returns_df, dt, asset, 2)
        if pd.isna(r2):
            return not missing_as_block
        if r2 <= float(gate["min_return_2m"]):
            return False

    if "min_return_3m" in gate:
        r3 = trailing_compound_return(returns_df, dt, asset, 3)
        if pd.isna(r3):
            return not missing_as_block
        if r3 <= float(gate["min_return_3m"]):
            return False

    if "min_return_6m" in gate:
        r6 = trailing_compound_return(returns_df, dt, asset, 6)
        if pd.isna(r6):
            return not missing_as_block
        if r6 <= float(gate["min_return_6m"]):
            return False

    if "max_drawdown_3m" in gate:
        max_dd_3m = trailing_max_drawdown(returns_df, dt, asset, 3)
        if pd.isna(max_dd_3m):
            return not missing_as_block
        if max_dd_3m <= float(gate["max_drawdown_3m"]):
            return False

    if "max_drawdown_6m" in gate:
        max_dd_6m = trailing_max_drawdown(returns_df, dt, asset, 6)
        if pd.isna(max_dd_6m):
            return not missing_as_block
        if max_dd_6m <= float(gate["max_drawdown_6m"]):
            return False

    return True


def trailing_max_drawdown(
    returns_df: pd.DataFrame,
    dt: pd.Timestamp,
    asset: str,
    months: int,
) -> float:
    """
    Max drawdown z ostatnich N miesięcy PRZED dt.
    Uwaga: wartości drawdown są ujemne, np. -0.20.
    """
    if months <= 0:
        return np.nan

    if asset not in returns_df.columns:
        return np.nan

    hist = returns_df.loc[returns_df.index < dt, asset].dropna().tail(months)
    if len(hist) < months:
        return np.nan

    return max_drawdown_from_returns(hist)


def apply_asset_gates(
    candidate_assets: List[str],
    asset_gates: Dict[str, Dict[str, Any]],
    dt: pd.Timestamp,
    current_score_name: str,
    current_scores: pd.Series,
    score_exec_map: Dict[str, pd.DataFrame],
    returns_df: pd.DataFrame,
    bad_canaries: int,
) -> Tuple[List[str], List[str]]:
    """
    Usuwa z kandydatów assety, które nie przeszły własnego gate.
    Zwraca: filtered_assets, blocked_assets.
    """
    if not asset_gates:
        return candidate_assets, []

    filtered: List[str] = []
    blocked: List[str] = []

    for asset in candidate_assets:
        gate = asset_gates.get(asset)

        if gate is None:
            filtered.append(asset)
            continue

        ok = asset_gate_passes(
            asset=asset,
            gate=gate,
            dt=dt,
            current_score_name=current_score_name,
            current_scores=current_scores,
            score_exec_map=score_exec_map,
            returns_df=returns_df,
            bad_canaries=bad_canaries,
        )

        if ok:
            filtered.append(asset)
        else:
            blocked.append(asset)

    return filtered, blocked


def normalize_weights_or_cash(weights: Dict[str, float]) -> Dict[str, float]:
    clean = {
        asset: float(weight)
        for asset, weight in weights.items()
        if abs(float(weight)) > EPS
    }

    total = float(sum(clean.values()))

    if total <= EPS:
        return {"_CASH": 1.0}

    return {
        asset: float(weight) / total
        for asset, weight in clean.items()
    }


def apply_max_weight_caps(
    target_weights: Dict[str, float],
    max_weight_per_asset: Dict[str, float],
) -> Dict[str, float]:
    """
    Nakłada capy typu:
      btcusd.custom max 0.10

    Nadwyżka jest redystrybuowana do aktywów bez capu / z wolnym miejscem.
    Jeśli nie ma gdzie redystrybuować, idzie do _CASH.

    Kompatybilność wsteczna: jeśli max_weight_per_asset jest pusty, nic nie zmienia.
    """
    if not max_weight_per_asset:
        return target_weights

    weights = normalize_weights_or_cash(target_weights)

    if "_CASH" in weights and len(weights) == 1:
        return weights

    caps = {
        asset: float(cap)
        for asset, cap in max_weight_per_asset.items()
        if cap is not None and float(cap) >= 0.0
    }

    if not caps:
        return weights

    out = weights.copy()

    for _ in range(50):
        excess = 0.0

        for asset, weight in list(out.items()):
            if asset == "_CASH":
                continue

            cap = caps.get(asset)

            if cap is not None and weight > cap + EPS:
                excess += weight - cap
                out[asset] = cap

        if excess <= EPS:
            break

        receivers: List[str] = []
        for asset, weight in out.items():
            if asset == "_CASH":
                continue

            cap = caps.get(asset)

            if cap is None:
                receivers.append(asset)
            elif weight < cap - EPS:
                receivers.append(asset)

        if not receivers:
            out["_CASH"] = out.get("_CASH", 0.0) + excess
            break

        receiver_total = sum(out[a] for a in receivers)
        distributed = 0.0

        if receiver_total <= EPS:
            add = excess / len(receivers)
            for asset in receivers:
                cap = caps.get(asset)
                room = np.inf if cap is None else max(0.0, cap - out[asset])
                delta = min(add, room)
                out[asset] += delta
                distributed += delta
        else:
            for asset in receivers:
                share = out[asset] / receiver_total
                cap = caps.get(asset)
                room = np.inf if cap is None else max(0.0, cap - out[asset])
                delta = min(excess * share, room)
                out[asset] += delta
                distributed += delta

        if distributed <= EPS:
            out["_CASH"] = out.get("_CASH", 0.0) + excess
            break

    return normalize_weights_or_cash(out)


def has_weight_cap_breach(
    weights: Dict[str, float],
    max_weight_per_asset: Dict[str, float],
) -> bool:
    if not max_weight_per_asset:
        return False

    for asset, cap in max_weight_per_asset.items():
        if cap is None:
            continue
        if float(weights.get(asset, 0.0)) > float(cap) + EPS:
            return True

    return False


def target_assets_from_weights(weights: Dict[str, float]) -> List[str]:
    return [
        asset
        for asset, weight in weights.items()
        if asset != "_CASH" and abs(float(weight)) > EPS
    ]


def should_keep_current_assets_by_hysteresis(
    current_weights: Dict[str, float],
    desired_selected_assets: List[str],
    scores: pd.Series,
    top_n: int,
    min_score_gap_to_switch: float,
) -> bool:
    """
    Histereza anty-churn:
    - jeśli obecny skład nie jest pusty,
    - i wszystkie obecne aktywa nadal mają score,
    - i najgorszy obecny asset nie odstaje od najlepszego nowego assetu spoza obecnego
      bardziej niż min_score_gap_to_switch,
    to zostawiamy obecny skład.

    Działa najlepiej dla equal_weight / top_n 1-3.
    """
    if min_score_gap_to_switch <= 0.0:
        return False

    current_assets = target_assets_from_weights(current_weights)
    current_assets = [a for a in current_assets if a != "_CASH"]

    if not current_assets:
        return False

    if len(current_assets) != top_n:
        return False

    if not desired_selected_assets:
        return False

    current_scores = []
    for asset in current_assets:
        s = scores.get(asset, np.nan)
        if pd.isna(s):
            return False
        current_scores.append(float(s))

    desired_set = set(desired_selected_assets)
    current_set = set(current_assets)

    if desired_set == current_set:
        return False

    challenger_assets = [a for a in desired_selected_assets if a not in current_set]
    if not challenger_assets:
        return False

    challenger_scores = []
    for asset in challenger_assets:
        s = scores.get(asset, np.nan)
        if pd.isna(s):
            continue
        challenger_scores.append(float(s))

    if not challenger_scores:
        return False

    weakest_current_score = min(current_scores)
    best_challenger_score = max(challenger_scores)

    return (best_challenger_score - weakest_current_score) < min_score_gap_to_switch


def normalize_signature(weights: Dict[str, float]) -> Tuple[Tuple[str, float], ...]:
    items = []
    for asset, weight in sorted(weights.items()):
        if abs(weight) > EPS:
            items.append((asset, round(float(weight), 10)))
    return tuple(items)


def full_switch_turnover(current_weights: Dict[str, float], target_weights: Dict[str, float]) -> float:
    assets = set(current_weights.keys()) | set(target_weights.keys())
    total = 0.0
    for asset in assets:
        total += abs(current_weights.get(asset, 0.0) - target_weights.get(asset, 0.0))
    return 0.5 * total


def full_switch_operations(current_weights: Dict[str, float], target_weights: Dict[str, float]) -> int:
    current_assets = [a for a, w in current_weights.items() if a != "_CASH" and abs(w) > EPS]
    target_assets = [a for a, w in target_weights.items() if a != "_CASH" and abs(w) > EPS]
    return len(current_assets) + len(target_assets)


def apply_month_return(weights_for_month: Dict[str, float], returns_row: pd.Series) -> Tuple[float, Dict[str, float]]:
    portfolio_return = 0.0

    for asset, weight in weights_for_month.items():
        if asset == "_CASH":
            continue
        asset_ret = returns_row.get(asset, np.nan)
        if pd.isna(asset_ret):
            raise ValueError(f"Brak monthly return dla aktywa {asset}")
        portfolio_return += weight * float(asset_ret)

    next_weights: Dict[str, float] = {}
    denom = 1.0 + portfolio_return

    for asset, weight in weights_for_month.items():
        if asset == "_CASH":
            grown = weight
        else:
            grown = weight * (1.0 + float(returns_row[asset]))
        next_weights[asset] = grown / denom

    return portfolio_return, next_weights


def build_equal_weight_target(selected_assets: List[str]) -> Dict[str, float]:
    if not selected_assets:
        return {"_CASH": 1.0}
    w = 1.0 / len(selected_assets)
    return {asset: w for asset in selected_assets}


def build_inverse_vol_target(
    selected_assets: List[str],
    hist_returns: pd.DataFrame,
) -> Tuple[Dict[str, float], float | None]:
    if not selected_assets:
        return {"_CASH": 1.0}, None

    sub = hist_returns[selected_assets].dropna(axis=1, how="any")
    if sub.shape[1] == 0:
        return {"_CASH": 1.0}, None

    vols = sub.std(ddof=1)
    inv = 1.0 / vols.replace(0.0, np.nan)
    inv = inv.replace([np.inf, -np.inf], np.nan).dropna()

    if len(inv) == 0:
        return {"_CASH": 1.0}, None

    weights = inv / inv.sum()
    target = {asset: float(weights[asset]) for asset in weights.index}

    cov = sub[weights.index].cov()
    est_vol_annual = float(np.sqrt(np.dot(weights.values, np.dot(cov.values, weights.values))) * np.sqrt(12.0))
    return target, est_vol_annual


def build_min_variance_target(
    selected_assets: List[str],
    hist_returns: pd.DataFrame,
) -> Tuple[Dict[str, float], float | None]:
    if not selected_assets:
        return {"_CASH": 1.0}, None

    sub = hist_returns[selected_assets].dropna(axis=1, how="any")
    if sub.shape[1] == 0:
        return {"_CASH": 1.0}, None

    cov = sub.cov().values
    n = cov.shape[0]

    try:
        inv_cov = np.linalg.pinv(cov)
    except np.linalg.LinAlgError:
        return {"_CASH": 1.0}, None

    ones = np.ones(n)
    raw = inv_cov @ ones
    denom = float(ones @ raw)
    if abs(denom) <= EPS:
        return {"_CASH": 1.0}, None

    weights = raw / denom
    weights = np.clip(weights, 0.0, None)

    if weights.sum() <= EPS:
        return {"_CASH": 1.0}, None

    weights = weights / weights.sum()
    cols = list(sub.columns)
    target = {cols[i]: float(weights[i]) for i in range(len(cols))}
    est_vol_annual = float(np.sqrt(np.dot(weights, np.dot(cov, weights))) * np.sqrt(12.0))
    return target, est_vol_annual


def apply_target_vol_overlay(
    target_weights: Dict[str, float],
    estimated_portfolio_vol_annual: float | None,
    target_vol_annual: float | None,
) -> Dict[str, float]:
    if target_vol_annual is None or estimated_portfolio_vol_annual is None:
        return target_weights

    if estimated_portfolio_vol_annual <= EPS:
        return target_weights

    scale = min(1.0, float(target_vol_annual) / estimated_portfolio_vol_annual)
    if scale >= 1.0:
        return target_weights

    out: Dict[str, float] = {}
    risky_sum = 0.0
    for asset, weight in target_weights.items():
        if asset == "_CASH":
            continue
        new_w = float(weight) * scale
        if new_w > EPS:
            out[asset] = new_w
            risky_sum += new_w

    cash_weight = 1.0 - risky_sum
    if cash_weight > EPS:
        out["_CASH"] = cash_weight

    if not out:
        out["_CASH"] = 1.0

    return out


def get_strategy_date_range(strategy: Dict) -> Tuple[pd.Timestamp | None, pd.Timestamp | None]:
    start_date = pd.Timestamp(strategy["start_date"]) if strategy.get("start_date") else None
    end_date = pd.Timestamp(strategy["end_date"]) if strategy.get("end_date") else None
    return start_date, end_date


def filter_dates(
    common_dates: List[pd.Timestamp],
    start_date: pd.Timestamp | None,
    end_date: pd.Timestamp | None,
) -> List[pd.Timestamp]:
    out: List[pd.Timestamp] = []
    for dt in common_dates:
        if start_date is not None and dt < start_date:
            continue
        if end_date is not None and dt > end_date:
            continue
        out.append(dt)
    return out


def infer_strategy_name(strategy: Dict) -> str:
    if strategy.get("name"):
        return str(strategy["name"])
    return f"hybrid_{abs(hash(json.dumps(strategy, sort_keys=True))) % 10_000_000}"


def apply_annual_tax_if_year_end(
    dt: pd.Timestamp,
    equity_before_tax: float,
    tax_base_equity: float,
    annual_tax_rate: float,
) -> tuple[float, float, float, int, float]:
    """
    Roczny podatek typu high-water mark:
    - podatek tylko od wzrostu ponad tax_base_equity,
    - tax_base_equity nie spada po roku stratnym,
    - po zapłacie podatku baza rośnie do equity_after_tax, jeśli to nowy szczyt.
    """
    if annual_tax_rate <= 0.0:
        return equity_before_tax, 0.0, 0.0, 0, tax_base_equity

    if dt.month != 12:
        return equity_before_tax, 0.0, 0.0, 0, tax_base_equity

    taxable_profit = max(0.0, equity_before_tax - tax_base_equity)
    tax_amount = taxable_profit * annual_tax_rate
    equity_after_tax = equity_before_tax - tax_amount

    next_tax_base_equity = max(tax_base_equity, equity_after_tax)

    return equity_after_tax, tax_amount, taxable_profit, int(tax_amount > 0.0), next_tax_base_equity


def build_periods_from_config(config: Dict, monthly_index: pd.Index) -> List[Dict]:
    periods: List[Dict] = []

    if len(monthly_index) == 0:
        return periods

    periods.append({
        "period_type": "full",
        "period_name": "FULL",
        "start": monthly_index.min(),
        "end": monthly_index.max(),
    })

    for item in config.get("named_periods", []):
        periods.append({
            "period_type": "named_period",
            "period_name": str(item["name"]),
            "start": pd.Timestamp(item["start"]),
            "end": pd.Timestamp(item["end"]),
        })

    return periods


def build_checkpoints_from_config(config: Dict, monthly_index: pd.Index) -> List[Dict]:
    checkpoints: List[Dict] = []

    if len(monthly_index) == 0:
        return checkpoints

    for item in config.get("equity_checkpoints", []):
        checkpoints.append({
            "checkpoint_name": str(item["name"]),
            "start": pd.Timestamp(item["start"]),
            "end": pd.Timestamp(item["end"]),
        })

    return checkpoints


def summarize_period(
    strategy_name: str,
    benchmark_asset: str,
    monthly: pd.DataFrame,
    period_type: str,
    period_name: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> Dict | None:
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

    row = {
        "strategy": strategy_name,
        "benchmark": benchmark_asset,
        "period_type": period_type,
        "period_name": period_name,
        "start": common_index.min().strftime("%Y-%m-%d"),
        "end": common_index.max().strftime("%Y-%m-%d"),
        "months": int(len(common_index)),
        "cagr": annualized_return(returns),
        "ann_vol": annualized_vol(returns),
        "sharpe": sharpe_ratio(returns),
        "max_drawdown": max_drawdown_from_returns(returns),
        "final_equity": float((1.0 + returns).cumprod().iloc[-1]),
        "avg_monthly_turnover": float(data["turnover"].mean()),
        "total_turnover": float(data["turnover"].sum()),
        "total_operations": int(data["operations"].sum()),
        "avg_operations_per_month": float(data["operations"].mean()),
        "benchmark_cagr": annualized_return(bench),
        "benchmark_ann_vol": annualized_vol(bench),
        "benchmark_sharpe": sharpe_ratio(bench),
        "benchmark_max_drawdown": max_drawdown_from_returns(bench),
        "benchmark_final_equity": float((1.0 + bench).cumprod().iloc[-1]),
        "cagr_vs_benchmark": annualized_return(returns) - annualized_return(bench),
        "sharpe_vs_benchmark": sharpe_ratio(returns) - sharpe_ratio(bench),
        "maxdd_vs_benchmark": max_drawdown_from_returns(returns) - max_drawdown_from_returns(bench),
        "avg_monthly_excess": float((returns - bench).mean()),
        "hit_rate_excess": float((returns > bench).mean()),
        "cum_excess_sum": float((returns - bench).sum()),

        "max_drawdown_start": strategy_dd_stats["max_drawdown_start"],
        "max_drawdown_bottom": strategy_dd_stats["max_drawdown_bottom"],
        "max_drawdown_recovery": strategy_dd_stats["max_drawdown_recovery"],
        "max_drawdown_duration_months": strategy_dd_stats["max_drawdown_duration_months"],
        "max_time_underwater_months": strategy_dd_stats["max_time_underwater_months"],
        "avg_time_underwater_months": strategy_dd_stats["avg_time_underwater_months"],
        "num_underwater_periods": strategy_dd_stats["num_underwater_periods"],
        "current_underwater_months": strategy_dd_stats["current_underwater_months"],

        "benchmark_max_drawdown_start": benchmark_dd_stats["max_drawdown_start"],
        "benchmark_max_drawdown_bottom": benchmark_dd_stats["max_drawdown_bottom"],
        "benchmark_max_drawdown_recovery": benchmark_dd_stats["max_drawdown_recovery"],
        "benchmark_max_drawdown_duration_months": benchmark_dd_stats["max_drawdown_duration_months"],
        "benchmark_max_time_underwater_months": benchmark_dd_stats["max_time_underwater_months"],
        "benchmark_avg_time_underwater_months": benchmark_dd_stats["avg_time_underwater_months"],
        "benchmark_num_underwater_periods": benchmark_dd_stats["num_underwater_periods"],
        "benchmark_current_underwater_months": benchmark_dd_stats["current_underwater_months"],
    }

    for field in [
        "score_name",
        "canary_score_name",
        "canary_bad_threshold",
        "missing_canary_as_bad",
        "group_set_name",
        "canary_pair_name",
        "behavior_map_name",
        "top_n",
        "weighting_method",
        "rank_weights",
        "covariance_lookback_months",
        "require_positive_score",
        "target_vol_annual",
        "min_score_gap_to_switch",
        "asset_gates_json",
        "max_weight_per_asset_json",
    ]:
        if field in monthly.columns:
            non_null = monthly[field].dropna()
            if len(non_null) > 0:
                row[field] = non_null.iloc[0]

    return row


def summarize_rolling_windows(
    strategy_name: str,
    benchmark_asset: str,
    monthly: pd.DataFrame,
    window_months_list: List[int],
) -> List[Dict]:
    out: List[Dict] = []

    for window_months in window_months_list:
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
                "strategy_cagr": annualized_return(returns),
                "benchmark_cagr": annualized_return(bench),
                "strategy_sharpe": sharpe_ratio(returns),
                "benchmark_sharpe": sharpe_ratio(bench),
                "strategy_max_drawdown": max_drawdown_from_returns(returns),
                "benchmark_max_drawdown": max_drawdown_from_returns(bench),
                "avg_monthly_excess": float((returns - bench).mean()),
                "hit_rate_excess": float((returns > bench).mean()),
            }
            row["cagr_vs_benchmark"] = row["strategy_cagr"] - row["benchmark_cagr"]
            row["sharpe_vs_benchmark"] = row["strategy_sharpe"] - row["benchmark_sharpe"]
            row["maxdd_vs_benchmark"] = row["strategy_max_drawdown"] - row["benchmark_max_drawdown"]
            rows.append(row)

        if not rows:
            continue

        df = pd.DataFrame(rows)

        out.append({
            "strategy": strategy_name,
            "benchmark": benchmark_asset,
            "window_months": window_months,
            "n_windows": int(len(df)),
            "pct_windows_cagr_beats_benchmark": float((df["cagr_vs_benchmark"] > 0).mean()),
            "pct_windows_sharpe_beats_benchmark": float((df["sharpe_vs_benchmark"] > 0).mean()),
            "pct_windows_lower_dd_than_benchmark": float((df["maxdd_vs_benchmark"] > 0).mean()),
            "median_strategy_cagr": float(df["strategy_cagr"].median()),
            "median_benchmark_cagr": float(df["benchmark_cagr"].median()),
            "median_cagr_vs_benchmark": float(df["cagr_vs_benchmark"].median()),
            "worst_cagr_vs_benchmark": float(df["cagr_vs_benchmark"].min()),
            "best_cagr_vs_benchmark": float(df["cagr_vs_benchmark"].max()),
            "worst_strategy_max_drawdown": float(df["strategy_max_drawdown"].min()),
            "worst_benchmark_max_drawdown": float(df["benchmark_max_drawdown"].min()),
            "median_hit_rate_excess": float(df["hit_rate_excess"].median()),
            "median_avg_monthly_excess": float(df["avg_monthly_excess"].median()),
        })

    return out


def summarize_equity_checkpoints(
    strategy_name: str,
    benchmark_asset: str,
    monthly: pd.DataFrame,
    checkpoints: List[Dict],
) -> List[Dict]:
    out: List[Dict] = []

    for cp in checkpoints:
        start = cp["start"]
        end = cp["end"]
        name = cp["checkpoint_name"]

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
            "strategy_cagr": annualized_return(sub["net_return"]),
            "benchmark_cagr": annualized_return(sub["benchmark_return"]),
            "strategy_max_drawdown": max_drawdown_from_returns(sub["net_return"]),
            "benchmark_max_drawdown": max_drawdown_from_returns(sub["benchmark_return"]),
        })

    return out


def build_combined_rank(
    full_summary: pd.DataFrame,
    rolling_summary: pd.DataFrame,
    preferred_windows: List[int],
) -> pd.DataFrame:
    if full_summary.empty:
        return full_summary.copy()

    base = full_summary.copy()

    rolling_pivot = rolling_summary.pivot_table(
        index="strategy",
        columns="window_months",
        values=[
            "median_cagr_vs_benchmark",
            "worst_cagr_vs_benchmark",
            "pct_windows_cagr_beats_benchmark",
        ],
        aggfunc="first",
    )

    rolling_pivot.columns = [
        f"rolling_{int(window)}_{metric.replace('pct_windows_cagr_beats_benchmark', 'pct_beats')}"
        for metric, window in rolling_pivot.columns
    ]
    rolling_pivot = rolling_pivot.reset_index()

    out = base.merge(rolling_pivot, on="strategy", how="left")

    score = np.zeros(len(out), dtype=float)

    score += out["cagr_vs_benchmark"].fillna(0.0) * 40.0
    score += out["sharpe_vs_benchmark"].fillna(0.0) * 20.0
    score += out["maxdd_vs_benchmark"].fillna(0.0) * 10.0

    for w in preferred_windows:
        col1 = f"rolling_{w}_median_cagr_vs_benchmark"
        col2 = f"rolling_{w}_worst_cagr_vs_benchmark"
        col3 = f"rolling_{w}_pct_beats"

        if col1 in out.columns:
            score += out[col1].fillna(0.0) * 25.0
        if col2 in out.columns:
            score += out[col2].fillna(0.0) * 15.0
        if col3 in out.columns:
            score += out[col3].fillna(0.0) * 10.0

    out["combined_score"] = score
    out = out.sort_values(
        ["combined_score", "sharpe", "cagr"],
        ascending=[False, False, False],
    )
    return out


def backtest_one_strategy(
    strategy: Dict,
    config: Dict,
    score_exec: pd.DataFrame,
    score_exec_map: Dict[str, pd.DataFrame],
    signal_exec_map: Dict[str, pd.DataFrame],
    returns_df: pd.DataFrame,
    benchmark_asset: str,
    transaction_cost_bps_one_way: float,
    annual_tax_rate: float,
) -> pd.DataFrame:
    name = infer_strategy_name(strategy)
    start_date, end_date = get_strategy_date_range(strategy)
    threshold = float(strategy.get("canary_bad_threshold", 0.0))
    missing_as_bad = bool(strategy.get("missing_canary_as_bad", True))
    cost_rate = float(transaction_cost_bps_one_way) / 10000.0

    top_n = int(strategy["top_n"])
    weighting_method = str(strategy.get("weighting_method", "equal_weight"))
    covariance_lookback_months = int(strategy.get("covariance_lookback_months", 6))
    min_history_months = int(strategy.get("min_history_months", covariance_lookback_months))
    require_positive_score = bool(strategy.get("require_positive_score", False))
    min_score_gap_to_switch = float(strategy.get("min_score_gap_to_switch", 0.0))
    target_vol_annual = strategy.get("target_vol_annual", None)

    score_name = str(strategy["score_name"])
    canary_score_name = str(strategy.get("canary_score_name", score_name))

    if canary_score_name not in score_exec_map:
        raise KeyError(
            f"Brak canary_score_name w score_files: {canary_score_name}. "
            f"Strategia: {name}"
        )

    canary_score_exec = score_exec_map[canary_score_name]

    asset_gates: Dict[str, Dict[str, Any]] = dict(strategy.get("asset_gates", {}))
    max_weight_per_asset: Dict[str, float] = dict(strategy.get("max_weight_per_asset", {}))

    for gated_asset, gate in asset_gates.items():
        if "max_weight" in gate and gated_asset not in max_weight_per_asset:
            max_weight_per_asset[gated_asset] = float(gate["max_weight"])

    group_set = config["group_sets"][str(strategy["group_set_name"])]
    canary_assets = list(config["canary_pairs"][str(strategy["canary_pair_name"])])
    behavior_map = config["behavior_maps"][str(strategy["behavior_map_name"])]

    max_behavior_key = max(int(k) for k in behavior_map.keys())

    common_dates = sorted(set(score_exec.index) & set(returns_df.index))
    common_dates = filter_dates(common_dates, start_date, end_date)

    records = []
    current_weights: Dict[str, float] = {"_CASH": 1.0}
    last_target_signature = None
    equity_value = 1.0
    tax_base_equity = 1.0
    started = False

    for dt in common_dates:
        scores = score_exec.loc[dt]

        if dt in canary_score_exec.index:
            canary_scores = canary_score_exec.loc[dt]
        else:
            canary_scores = pd.Series(dtype=float)

        returns_row = returns_df.loc[dt]

        if pd.isna(returns_row.get(benchmark_asset, np.nan)):
            continue

        bad_canaries = count_bad_canaries(
            scores=canary_scores,
            canary_assets=canary_assets,
            threshold=threshold,
            missing_as_bad=missing_as_bad,
        )

        behavior_entry = behavior_map[str(min(bad_canaries, max_behavior_key))]
        allowed_groups = list(behavior_entry.get("allowed_groups", []))
        excluded_assets = list(behavior_entry.get("exclude_assets", []))

        candidate_assets = flatten_group_assets(group_set, allowed_groups)
        candidate_assets = [a for a in candidate_assets if a not in excluded_assets]

        candidate_assets, blocked_by_asset_gate = apply_asset_gates(
            candidate_assets=candidate_assets,
            asset_gates=asset_gates,
            dt=dt,
            current_score_name=score_name,
            current_scores=scores,
            score_exec_map=score_exec_map,
            returns_df=returns_df,
            bad_canaries=bad_canaries,
        )

        ranked_candidates = rank_assets(scores, candidate_assets, returns_row)

        if require_positive_score:
            ranked_candidates = [a for a in ranked_candidates if float(scores[a]) > 0.0]

        selected_assets = ranked_candidates[:top_n]

        hist = returns_df.loc[returns_df.index < dt, selected_assets]
        estimated_portfolio_vol_annual = None

        if len(selected_assets) == 0 or len(hist) < min_history_months:
            desired_target_weights = {"_CASH": 1.0}
        else:
            hist = hist.tail(covariance_lookback_months)

            if weighting_method == "equal_weight":
                desired_target_weights = build_equal_weight_target(selected_assets)

            elif weighting_method == "rank_weights":
                rank_weights = list(strategy["rank_weights"])
                desired_target_weights = build_rank_weight_target(
                    selected_assets=selected_assets,
                    rank_weights=rank_weights,
                )

            elif weighting_method == "inverse_vol":
                desired_target_weights, estimated_portfolio_vol_annual = build_inverse_vol_target(selected_assets, hist)

            elif weighting_method == "min_variance":
                desired_target_weights, estimated_portfolio_vol_annual = build_min_variance_target(selected_assets, hist)

            else:
                raise ValueError(f"Nieznany weighting_method: {weighting_method}")

            desired_target_weights = apply_target_vol_overlay(
                target_weights=desired_target_weights,
                estimated_portfolio_vol_annual=estimated_portfolio_vol_annual,
                target_vol_annual=target_vol_annual,
            )

            desired_target_weights = apply_max_weight_caps(
                target_weights=desired_target_weights,
                max_weight_per_asset=max_weight_per_asset,
            )

        kept_by_hysteresis = False
        force_no_trade = False
        forced_rebalance_due_to_cap = False
        forced_exit_due_to_asset_gate = False

        if started:
            current_assets_for_gate_check = target_assets_from_weights(current_weights)
            current_has_blocked_asset = any(
                asset in blocked_by_asset_gate
                for asset in current_assets_for_gate_check
            )

            if current_has_blocked_asset:
                keep_current = False
                forced_exit_due_to_asset_gate = True
            elif has_weight_cap_breach(current_weights, max_weight_per_asset):
                keep_current = False
                forced_rebalance_due_to_cap = True
            else:
                keep_current = should_keep_current_assets_by_hysteresis(
                    current_weights=current_weights,
                    desired_selected_assets=selected_assets,
                    scores=scores,
                    top_n=top_n,
                    min_score_gap_to_switch=min_score_gap_to_switch,
                )

            if keep_current:
                selected_assets = target_assets_from_weights(current_weights)
                desired_target_weights = current_weights.copy()
                kept_by_hysteresis = True
                force_no_trade = True

        target_before_rebound_weights = desired_target_weights.copy()

        desired_target_weights, rebound_diag = apply_rebound_starter(
            strategy=strategy,
            desired_target_weights=desired_target_weights,
            dt=dt,
            signal_exec_map=signal_exec_map,
        )

        if rebound_diag["rebound_starter_active"]:
            selected_assets = target_assets_from_weights(desired_target_weights)

        target_signature = normalize_signature(desired_target_weights)

        if not started:
            started = True
            signal_changed = True
        elif force_no_trade:
            signal_changed = False
        elif forced_rebalance_due_to_cap or forced_exit_due_to_asset_gate:
            signal_changed = True
        else:
            signal_changed = target_signature != last_target_signature

        if signal_changed:
            turnover = full_switch_turnover(current_weights, desired_target_weights)
            operations = full_switch_operations(current_weights, desired_target_weights)
            trade_cost = turnover * cost_rate
            weights_for_month = desired_target_weights.copy()
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

        (
            equity_after_tax,
            tax_amount,
            taxable_profit,
            tax_event,
            tax_base_equity,
        ) = apply_annual_tax_if_year_end(
            dt=dt,
            equity_before_tax=equity_before_tax,
            tax_base_equity=tax_base_equity,
            annual_tax_rate=annual_tax_rate,
        )

        net_return = equity_after_tax / equity_value - 1.0

        equity_value = equity_after_tax
        current_weights = next_weights

        canary_scores_json = json.dumps(
            {
                asset: (
                    None
                    if pd.isna(canary_scores.get(asset, np.nan))
                    else float(canary_scores.get(asset, np.nan))
                )
                for asset in canary_assets
            },
            ensure_ascii=False,
        )

        records.append({
            "date": dt,
            "strategy": name,
            "signal_changed": int(signal_changed),
            "kept_by_hysteresis": int(kept_by_hysteresis),
            "forced_rebalance_due_to_cap": int(forced_rebalance_due_to_cap),
            "forced_exit_due_to_asset_gate": int(forced_exit_due_to_asset_gate),
            "min_score_gap_to_switch": min_score_gap_to_switch,
            "turnover": turnover,
            "operations": operations,
            "trade_cost": trade_cost,
            "gross_return": gross_return,
            "net_return_before_tax": net_return_before_tax,
            "taxable_profit_year": taxable_profit,
            "tax_amount": tax_amount,
            "tax_event": tax_event,
            "tax_base_before": tax_base_before,
            "tax_base_after": tax_base_equity,
            "net_return": net_return,
            "equity_before_tax": equity_before_tax,
            "equity": equity_value,
            "weights_used_json": json.dumps(weights_for_month, ensure_ascii=False),
            "target_before_rebound_json": json.dumps(target_before_rebound_weights, ensure_ascii=False),
            "rebound_starter_active": int(rebound_diag["rebound_starter_active"]),
            "rebound_signal_name": rebound_diag["rebound_signal_name"],
            "rebound_trigger_asset": rebound_diag["rebound_trigger_asset"],
            "rebound_trigger_value": rebound_diag["rebound_trigger_value"],
            "rebound_trigger_threshold": rebound_diag["rebound_trigger_threshold"],
            "next_weights_json": json.dumps(current_weights, ensure_ascii=False),
            "bad_canaries": bad_canaries,
            "canary_scores_json": canary_scores_json,
            "canary_bad_threshold": threshold,
            "missing_canary_as_bad": int(missing_as_bad),
            "allowed_groups": "|".join(allowed_groups),
            "excluded_assets": "|".join(excluded_assets),
            "candidate_assets": "|".join(ranked_candidates),
            "selected_assets": "|".join(selected_assets),
            "blocked_by_asset_gate": "|".join(blocked_by_asset_gate),
            "asset_gates_json": json.dumps(asset_gates, ensure_ascii=False),
            "max_weight_per_asset_json": json.dumps(max_weight_per_asset, ensure_ascii=False),
            "top_n": top_n,
            "weighting_method": weighting_method,
            "covariance_lookback_months": covariance_lookback_months,
            "require_positive_score": int(require_positive_score),
            "target_vol_annual": target_vol_annual,
            "estimated_portfolio_vol_annual": estimated_portfolio_vol_annual,
            "group_set_name": str(strategy["group_set_name"]),
            "canary_pair_name": str(strategy["canary_pair_name"]),
            "behavior_map_name": str(strategy["behavior_map_name"]),
            "score_name": score_name,
            "canary_score_name": canary_score_name,
            "rank_weights": "|".join(str(x) for x in strategy.get("rank_weights", [])),
        })

    monthly = pd.DataFrame(records)
    if monthly.empty:
        raise ValueError(f"Strategia {name}: brak danych.")

    monthly = monthly.set_index("date").sort_index()
    bench_returns = returns_df.loc[monthly.index, benchmark_asset].astype(float)
    monthly["benchmark_return"] = bench_returns
    monthly["benchmark_equity"] = (1.0 + monthly["benchmark_return"]).cumprod()
    monthly["excess_return"] = monthly["net_return"] - monthly["benchmark_return"]
    return monthly


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, float_format="%.10f")
    print(f"[OK] zapisano: {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="hybrid_aaa_daa_strategies.json")
    parser.add_argument("--out-dir", default="backtest_hybrid_aaa_daa_output")
    args = parser.parse_args()

    config_path = Path(args.config)
    out_dir = Path(args.out_dir)
    monthly_dir = out_dir / "monthly"

    out_dir.mkdir(parents=True, exist_ok=True)
    monthly_dir.mkdir(parents=True, exist_ok=True)

    with config_path.open("r", encoding="utf-8-sig") as f:
        config = json.load(f)

    score_files = config.get("score_files", {})
    if not score_files:
        raise ValueError("Brak score_files w configu.")

    returns_df = load_wide_csv(config["returns_file"])
    benchmark_asset = str(config["benchmark_asset"])
    transaction_cost_bps_one_way = float(config.get("transaction_cost_bps_one_way", 0.0))
    annual_tax_rate = float(config.get("annual_tax_rate", 0.0))
    rolling_windows = list(config.get("rolling_windows_months", [12, 24, 36, 48, 60]))
    combined_rank_windows = list(config.get("combined_rank_windows", [12, 24, 36, 48, 60]))

    score_map: Dict[str, pd.DataFrame] = {}
    for score_name, score_path in score_files.items():
        score_df = load_wide_csv(score_path)
        score_map[str(score_name)] = align_scores_to_execution_month(score_df)

    signal_files = config.get("signal_files", {})

    signal_map: Dict[str, pd.DataFrame] = {}
    for signal_name, signal_path in signal_files.items():
        signal_df = load_wide_csv(signal_path)
        signal_map[str(signal_name)] = align_scores_to_execution_month(signal_df)

    all_monthly: Dict[str, pd.DataFrame] = {}
    all_monthly_for_export = []
    full_rows = []
    named_rows = []
    rolling_rows = []
    checkpoint_rows = []
    underwater_rows = []
    rolling_detail_rows = []

    for strategy in config["strategies"]:
        strategy_name = infer_strategy_name(strategy)
        score_name = str(strategy["score_name"])
        canary_score_name = str(strategy.get("canary_score_name", score_name))

        if score_name not in score_map:
            raise KeyError(f"Brak score_name w score_files: {score_name}")

        if canary_score_name not in score_map:
            raise KeyError(f"Brak canary_score_name w score_files: {canary_score_name}")

        monthly = backtest_one_strategy(
            strategy=strategy,
            config=config,
            score_exec=score_map[score_name],
            score_exec_map=score_map,
            signal_exec_map=signal_map,
            returns_df=returns_df,
            benchmark_asset=benchmark_asset,
            transaction_cost_bps_one_way=transaction_cost_bps_one_way,
            annual_tax_rate=annual_tax_rate,
        )

        all_monthly[strategy_name] = monthly
        all_monthly_for_export.append(monthly.reset_index())

        monthly_path = monthly_dir / f"{strategy_name}_monthly.csv"
        monthly.to_csv(monthly_path, float_format="%.10f")
        print(f"[OK] zapisano: {monthly_path}")

        periods = build_periods_from_config(config, monthly.index)
        for period in periods:
            row = summarize_period(
                strategy_name=strategy_name,
                benchmark_asset=benchmark_asset,
                monthly=monthly,
                period_type=period["period_type"],
                period_name=period["period_name"],
                start=period["start"],
                end=period["end"],
            )
            if row is None:
                continue

            if period["period_type"] == "full":
                full_rows.append(row)
            else:
                named_rows.append(row)

        rolling_rows.extend(
            summarize_rolling_windows(
                strategy_name=strategy_name,
                benchmark_asset=benchmark_asset,
                monthly=monthly,
                window_months_list=rolling_windows,
            )
        )

        rolling_detail = compute_rolling_windows_detail(
            strategy_name=strategy_name,
            benchmark_asset=benchmark_asset,
            monthly_df=monthly,
            windows=tuple(rolling_windows),
        )

        if not rolling_detail.empty:
            rolling_detail_rows.append(rolling_detail)

        checkpoints = build_checkpoints_from_config(config, monthly.index)
        checkpoint_rows.extend(
            summarize_equity_checkpoints(
                strategy_name=strategy_name,
                benchmark_asset=benchmark_asset,
                monthly=monthly,
                checkpoints=checkpoints,
            )
        )

        underwater_rows.extend(
            summarize_underwater_periods(
                strategy_name=strategy_name,
                benchmark_asset=benchmark_asset,
                monthly=monthly,
            )
        )

    summary_full_period = pd.DataFrame(full_rows).sort_values(
        ["sharpe", "cagr", "max_drawdown"],
        ascending=[False, False, False],
    )
    save_csv(summary_full_period, out_dir / "summary_full_period.csv")

    summary_named_periods = pd.DataFrame(named_rows)
    if not summary_named_periods.empty:
        summary_named_periods = summary_named_periods.sort_values(
            ["period_name", "sharpe", "cagr"],
            ascending=[True, False, False],
        )
        save_csv(summary_named_periods, out_dir / "summary_named_periods.csv")

    summary_rolling = pd.DataFrame(rolling_rows)
    if not summary_rolling.empty:
        summary_rolling = summary_rolling.sort_values(
            ["window_months", "median_cagr_vs_benchmark", "pct_windows_cagr_beats_benchmark"],
            ascending=[True, False, False],
        )
        save_csv(summary_rolling, out_dir / "summary_rolling.csv")

    if rolling_detail_rows:
        rolling_windows_detail = pd.concat(rolling_detail_rows, ignore_index=True)

        rolling_windows_detail = rolling_windows_detail.sort_values(
            ["window_months", "cagr_vs_benchmark"],
            ascending=[True, True],
        )

        save_csv(rolling_windows_detail, out_dir / "rolling_windows_detail.csv")

        worst_rolling_windows = rolling_windows_detail.sort_values(
            "cagr_vs_benchmark",
            ascending=True,
        ).head(100)

        save_csv(worst_rolling_windows, out_dir / "worst_rolling_windows.csv")

        worst_rolling_windows_by_window = (
            rolling_windows_detail
            .sort_values(["window_months", "cagr_vs_benchmark"], ascending=[True, True])
            .groupby("window_months", as_index=False)
            .head(20)
        )

        save_csv(
            worst_rolling_windows_by_window,
            out_dir / "worst_rolling_windows_by_window.csv",
        )
    else:
        rolling_windows_detail = pd.DataFrame()
        worst_rolling_windows = pd.DataFrame()
        worst_rolling_windows_by_window = pd.DataFrame()

    summary_checkpoints = pd.DataFrame(checkpoint_rows)
    if not summary_checkpoints.empty:
        summary_checkpoints = summary_checkpoints.sort_values(
            ["checkpoint_name", "equity_ratio_strategy_vs_benchmark"],
            ascending=[True, False],
        )
        save_csv(summary_checkpoints, out_dir / "summary_equity_checkpoints.csv")

    summary_underwater_periods = pd.DataFrame(underwater_rows)
    if not summary_underwater_periods.empty:
        summary_underwater_periods = summary_underwater_periods.sort_values(
            ["strategy", "series_type", "duration_months", "max_drawdown"],
            ascending=[True, True, False, True],
        )
        save_csv(summary_underwater_periods, out_dir / "summary_underwater_periods.csv")

    summary_combined_rank = build_combined_rank(
        full_summary=summary_full_period,
        rolling_summary=summary_rolling,
        preferred_windows=combined_rank_windows,
    )
    if not summary_combined_rank.empty:
        save_csv(summary_combined_rank, out_dir / "summary_combined_rank.csv")

    all_monthly_df = pd.concat(all_monthly_for_export, ignore_index=True)
    all_monthly_path = out_dir / "all_strategies_monthly.csv"
    all_monthly_df.to_csv(all_monthly_path, index=False, float_format="%.10f")
    print(f"[OK] zapisano: {all_monthly_path}")

    print("\n=== PODSUMOWANIE FULL PERIOD ===")
    with pd.option_context("display.max_columns", None, "display.width", 260):
        print(summary_full_period)

    if not summary_named_periods.empty:
        print("\n=== PODSUMOWANIE NAMED PERIODS ===")
        with pd.option_context("display.max_columns", None, "display.width", 260):
            print(summary_named_periods)

    if not summary_rolling.empty:
        print("\n=== PODSUMOWANIE ROLLING ===")
        with pd.option_context("display.max_columns", None, "display.width", 260):
            print(summary_rolling)

    if not summary_underwater_periods.empty:
        print("\n=== PODSUMOWANIE UNDERWATER PERIODS ===")
        with pd.option_context("display.max_columns", None, "display.width", 260):
            print(summary_underwater_periods.head(60))

    if not summary_combined_rank.empty:
        print("\n=== PODSUMOWANIE COMBINED RANK ===")
        with pd.option_context("display.max_columns", None, "display.width", 260):
            print(summary_combined_rank)


if __name__ == "__main__":
    main()