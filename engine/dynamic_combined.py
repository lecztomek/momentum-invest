# combine_two_strategy_monthly_dynamic_combined.py
# Python 3.10+
#
# Uruchom:
#   python combine_two_strategy_monthly_dynamic_combined.py
#
# Wymagania:
#   pip install pandas numpy
#
# Co robi:
#   1) testuje stare statyczne miksy A/B z WEIGHTS_TO_TEST,
#   2) dodaje wariant dynamic_combined:
#        - A risk, B risk -> 80/20
#        - A cash, B risk -> 0/100, czyli B dostaje 100%
#        - A cash, B cash -> 100% _CASH
#        - A risk, B cash -> 100/0, czyli A dostaje 100%
#   3) stan risk/cash bierze z weights_used_json w all_strategies_monthly.csv:
#        - tylko _CASH => cash
#        - dowolny realny ticker => risk
#   4) eksportuje pliki combined_for_replay_monthly_*.csv zgodne z replay_mapped_to_uk.py

from __future__ import annotations

import ast
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


BASE_DIR = Path(r"C:\Users\tleczycki\Desktop\d_us_txt")

STRATEGY_A_MONTHLY_DIR = BASE_DIR / "backtest_hybrid_aaa_daa_output_best17" / "monthly"
STRATEGY_B_MONTHLY_DIR = BASE_DIR / "backtest_hybrid_aaa_daa_output_def" / "monthly"

OUT_DIR = BASE_DIR / "combined_two_strategies_output"

# Pliki detaliczne z wagami miesiecznymi strategii A/B.
# To sa te pliki, ktore maja kolumne weights_used_json.
HOLDINGS_A_CSV: Path | None = BASE_DIR / "backtest_hybrid_aaa_daa_output_best17" / "all_strategies_monthly.csv"
HOLDINGS_B_CSV: Path | None = BASE_DIR / "backtest_hybrid_aaa_daa_output_def" / "all_strategies_monthly.csv"
HOLDINGS_WEIGHT_COLUMN = "weights_used_json"

# Tu trafiaja pliki wejsciowe dla replay_mapped_to_uk.py.
REPLAY_SOURCE_OUT_DIR = OUT_DIR / "replay_source_monthly"

# Waga A = pierwsza / glowna strategia, B = defensywna / druga strategia.
WEIGHTS_TO_TEST = [
    (1.00, 0.00),
    (0.95, 0.05),
    (0.90, 0.10),
    (0.85, 0.15),
    (0.80, 0.20),
    (0.75, 0.25),
    (0.70, 0.30),
    (0.60, 0.40),
    (0.50, 0.50),
    (0.40, 0.60),
    (0.30, 0.70),
    (0.20, 0.80),
    (0.10, 0.90),
    (0.00, 1.00),
]

# Dynamiczny wariant.
INCLUDE_DYNAMIC_COMBINED = True
DYNAMIC_WEIGHT_LABEL = "dynamic_combined"
DYNAMIC_RISK_RISK_WEIGHT_A = 0.80
DYNAMIC_RISK_RISK_WEIGHT_B = 0.20

# Jesli A i B sa jednoczesnie w cash, miesieczny zwrot ustawiamy na 0.
# Jesli cash w Twoim backtescie ma oprocentowanie, mozesz tu podpiac osobny cash return.
DYNAMIC_CASH_RETURN = 0.0

ROLLING_WINDOWS_MONTHS = [12, 24, 36, 48, 60, 84, 120, 180]
ROLLING_RETURN_WINDOWS_FOR_PAIN = [3, 6, 12]

# Histogram miesiecznych zwrotow: -9, -5, -3, 0, 3, 5, 9.
RETURN_BUCKET_EDGES = [-np.inf, -0.09, -0.05, -0.03, 0.0, 0.03, 0.05, 0.09, np.inf]
RETURN_BUCKET_LABELS = [
    "lt_-9pct",
    "-9_to_-5pct",
    "-5_to_-3pct",
    "-3_to_0pct",
    "0_to_3pct",
    "3_to_5pct",
    "5_to_9pct",
    "gt_9pct",
]

NAMED_PERIODS = [
    ("full_until_2023_no_gold_breakout", "2008-07-01", "2023-12-01"),
    ("full_until_2024_no_gold_odklejka", "2008-07-01", "2024-12-01"),
    ("post_gfc_recovery", "2008-07-01", "2012-12-01"),
    ("post_gfc_bull_full", "2009-04-01", "2019-12-01"),
    ("post_gfc_expansion_clean", "2013-01-01", "2019-12-01"),
    ("pre_covid_full", "2008-07-01", "2019-12-01"),
    ("covid_crash_rebound", "2020-01-01", "2021-12-01"),
    ("inflation_bear", "2022-01-01", "2023-03-01"),
    ("pre_gold_odklejka", "2008-07-01", "2022-12-01"),
    ("recent_full", "2023-01-01", "2026-03-01"),
    ("recent_2023_only", "2023-01-01", "2023-12-01"),
    ("gold_breakout_2024", "2024-01-01", "2024-12-01"),
    ("gold_odklejka_2025_2026", "2025-01-01", "2026-03-01"),
    ("gold_recent_2024_2026", "2024-01-01", "2026-03-01"),
]

EPS = 1e-12


def first_csv(folder: Path) -> Path:
    files = sorted(folder.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"Brak plikow CSV w folderze: {folder}")
    return files[0]


def normalize_ticker(ticker: Any) -> str:
    t = str(ticker).strip()
    if t.lower() == "_cash":
        return "_CASH"
    return t.lower()


def parse_weights_json(value: Any) -> dict[str, float]:
    """Tolerancyjny parser wag.

    Obsluguje:
    - prawdziwy dict,
    - JSON string: {"xlk.us": 0.5},
    - Python-literal string: {'xlk.us': 0.5},
    - puste/nan.
    """
    if isinstance(value, dict):
        obj = value
    else:
        if value is None:
            return {}

        try:
            if pd.isna(value):
                return {}
        except Exception:
            pass

        s = str(value).strip()
        if not s or s.lower() in {"nan", "none", "null"}:
            return {}

        obj = None
        parse_errors: list[str] = []

        try:
            obj = json.loads(s)
        except Exception as e:
            parse_errors.append(f"json.loads: {e}")

        if obj is None:
            try:
                obj = ast.literal_eval(s)
            except Exception as e:
                parse_errors.append(f"ast.literal_eval: {e}")

        if obj is None:
            s2 = s.replace('""', '"')
            try:
                obj = json.loads(s2)
            except Exception as e:
                parse_errors.append(f"json.loads cleaned: {e}")

        if obj is None:
            raise ValueError("; ".join(parse_errors))

    if not isinstance(obj, dict):
        return {}

    out: dict[str, float] = {}
    for k, v in obj.items():
        try:
            w = float(v)
        except Exception:
            continue
        if abs(w) > EPS:
            out[normalize_ticker(k)] = out.get(normalize_ticker(k), 0.0) + w

    return out


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    clean = {normalize_ticker(k): float(v) for k, v in weights.items() if abs(float(v)) > EPS}
    total = float(sum(clean.values()))
    if total <= EPS:
        return {"_CASH": 1.0}
    return {k: v / total for k, v in clean.items()}


def combine_weight_dicts(
    weights_a: dict[str, float],
    weights_b: dict[str, float],
    weight_a: float,
    weight_b: float,
) -> dict[str, float]:
    out: dict[str, float] = {}

    for asset, w in weights_a.items():
        out[normalize_ticker(asset)] = out.get(normalize_ticker(asset), 0.0) + float(weight_a) * float(w)

    for asset, w in weights_b.items():
        out[normalize_ticker(asset)] = out.get(normalize_ticker(asset), 0.0) + float(weight_b) * float(w)

    return normalize_weights(out)


def weights_signature(weights: dict[str, float]) -> tuple[tuple[str, float], ...]:
    return tuple((asset, round(float(weight), 10)) for asset, weight in sorted(weights.items()))


def is_cash_portfolio(weights: dict[str, float]) -> bool:
    """True, jesli portfel jest praktycznie w 100% w _CASH.

    Logika dynamic_combined:
    - tylko _CASH albo puste wagi => cash,
    - dowolny realny ticker z waga > EPS => risk.
    """
    if not weights:
        return True

    normalized = normalize_weights(weights)
    risk_weight = sum(
        float(weight)
        for ticker, weight in normalized.items()
        if normalize_ticker(ticker) != "_CASH"
    )
    return risk_weight <= 1e-8


def classify_risk_cash(weights: dict[str, float]) -> str:
    return "cash" if is_cash_portfolio(weights) else "risk"


def dynamic_allocation_for_states(state_a: str, state_b: str) -> tuple[float, float, str]:
    """Zwraca weight_a, weight_b, regime dla dynamic_combined."""
    if state_a == "risk" and state_b == "risk":
        return DYNAMIC_RISK_RISK_WEIGHT_A, DYNAMIC_RISK_RISK_WEIGHT_B, "a_risk_b_risk__80_20"

    if state_a == "cash" and state_b == "risk":
        return 0.0, 1.0, "a_cash_b_risk__b_100"

    if state_a == "risk" and state_b == "cash":
        return 1.0, 0.0, "a_risk_b_cash__a_100"

    if state_a == "cash" and state_b == "cash":
        return 0.0, 0.0, "a_cash_b_cash__cash"

    raise ValueError(f"Nieznany stan dynamiczny: state_a={state_a}, state_b={state_b}")


def load_monthly(path: Path, suffix: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"date", "net_return", "equity"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} nie ma kolumn: {missing}")

    keep_cols = ["date", "strategy", "net_return", "equity"]

    if "benchmark_return" in df.columns:
        keep_cols.append("benchmark_return")
    if "benchmark_equity" in df.columns:
        keep_cols.append("benchmark_equity")

    df = df[keep_cols].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    rename = {
        "strategy": f"strategy_{suffix}",
        "net_return": f"return_{suffix}",
        "equity": f"equity_{suffix}",
        "benchmark_return": f"benchmark_return_{suffix}",
        "benchmark_equity": f"benchmark_equity_{suffix}",
    }
    df = df.rename(columns=rename)
    return df


def equity_from_returns(returns: pd.Series) -> pd.Series:
    return (1.0 + returns.fillna(0.0)).cumprod()


def max_drawdown(
    equity: pd.Series,
) -> tuple[float, pd.Timestamp | None, pd.Timestamp | None, pd.Timestamp | None, int | None]:
    if equity.empty:
        return np.nan, None, None, None, None

    running_max = equity.cummax()
    dd = equity / running_max - 1.0

    bottom_idx = dd.idxmin()
    max_dd = float(dd.loc[bottom_idx])

    peak_equity = running_max.loc[bottom_idx]
    start_candidates = equity.loc[:bottom_idx]
    start_idx = start_candidates[start_candidates == peak_equity].index[-1]

    recovery_idx = None
    after_bottom = equity.loc[bottom_idx:]
    recovered = after_bottom[after_bottom >= peak_equity]
    if not recovered.empty:
        recovery_idx = recovered.index[0]

    duration_months = None
    if recovery_idx is not None:
        duration_months = int((recovery_idx.to_period("M") - start_idx.to_period("M")).n)

    return max_dd, start_idx, bottom_idx, recovery_idx, duration_months


def drawdown_series(equity: pd.Series) -> pd.Series:
    if equity.empty:
        return pd.Series(dtype=float)
    return equity / equity.cummax() - 1.0


def ulcer_index(equity: pd.Series) -> float:
    dd_pct = drawdown_series(equity) * 100.0
    if dd_pct.empty:
        return np.nan
    return float(np.sqrt(np.mean(np.square(np.minimum(dd_pct, 0.0)))))


def consecutive_true_lengths(mask: pd.Series | np.ndarray) -> list[int]:
    lengths: list[int] = []
    run = 0

    for value in list(mask):
        if bool(value):
            run += 1
        else:
            if run > 0:
                lengths.append(run)
            run = 0

    if run > 0:
        lengths.append(run)

    return lengths


def streak_distribution(mask: pd.Series | np.ndarray, prefix: str) -> dict:
    lengths = consecutive_true_lengths(mask)
    total_months_in_streaks = int(sum(lengths))

    out = {
        f"{prefix}_streak_count": int(len(lengths)),
        f"{prefix}_streak_max": int(max(lengths)) if lengths else 0,
        f"{prefix}_streak_avg": float(np.mean(lengths)) if lengths else 0.0,
        f"{prefix}_streak_months_total": total_months_in_streaks,
        f"{prefix}_streak_len_1_count": int(sum(1 for x in lengths if x == 1)),
        f"{prefix}_streak_len_2_count": int(sum(1 for x in lengths if x == 2)),
        f"{prefix}_streak_len_3_count": int(sum(1 for x in lengths if x == 3)),
        f"{prefix}_streak_len_4_count": int(sum(1 for x in lengths if x == 4)),
        f"{prefix}_streak_len_5plus_count": int(sum(1 for x in lengths if x >= 5)),
        f"{prefix}_months_in_streak_2plus": int(sum(x for x in lengths if x >= 2)),
        f"{prefix}_months_in_streak_3plus": int(sum(x for x in lengths if x >= 3)),
        f"{prefix}_months_in_streak_4plus": int(sum(x for x in lengths if x >= 4)),
        f"{prefix}_months_in_streak_5plus": int(sum(x for x in lengths if x >= 5)),
    }
    return out


def return_bucket_stats(rets: pd.Series, prefix: str = "ret") -> dict:
    buckets = pd.cut(
        rets.astype(float),
        bins=RETURN_BUCKET_EDGES,
        labels=RETURN_BUCKET_LABELS,
        right=False,
        include_lowest=True,
    )

    counts = buckets.value_counts(sort=False)
    n = len(rets)

    out = {}
    for label in RETURN_BUCKET_LABELS:
        count = int(counts.get(label, 0))
        out[f"{prefix}_bucket_{label}_count"] = count
        out[f"{prefix}_bucket_{label}_rate"] = float(count / n) if n else np.nan

    return out


def rolling_return_pain_stats(d: pd.DataFrame, return_col: str, prefix: str = "rolling") -> dict:
    out = {}
    rets = d[return_col].astype(float)

    for window in ROLLING_RETURN_WINDOWS_FOR_PAIN:
        if len(rets) < window:
            out[f"{prefix}_{window}m_worst_return"] = np.nan
            out[f"{prefix}_{window}m_best_return"] = np.nan
            out[f"{prefix}_{window}m_negative_rate"] = np.nan
            continue

        rolling_total = (1.0 + rets).rolling(window).apply(np.prod, raw=True) - 1.0
        rolling_total = rolling_total.dropna()

        out[f"{prefix}_{window}m_worst_return"] = float(rolling_total.min())
        out[f"{prefix}_{window}m_best_return"] = float(rolling_total.max())
        out[f"{prefix}_{window}m_negative_rate"] = float((rolling_total < 0).mean())

    return out


def advanced_return_stats(d: pd.DataFrame, return_col: str, equity_col: str) -> dict:
    rets = d[return_col].astype(float)
    equity = pd.Series(d[equity_col].astype(float).values, index=d["date"])

    downside = rets[rets < 0]
    downside_dev = float(np.sqrt(np.mean(np.square(np.minimum(rets, 0.0)))) * math.sqrt(12))
    ann_return_arithmetic = float(rets.mean() * 12)

    sortino = float(ann_return_arithmetic / downside_dev) if downside_dev > 0 else np.nan
    mdd, _, _, _, _ = max_drawdown(equity)
    cagr = float(equity.iloc[-1] ** (12.0 / len(equity)) - 1.0) if len(equity) else np.nan
    calmar = float(cagr / abs(mdd)) if mdd < 0 else np.nan

    var_95 = float(rets.quantile(0.05))
    cvar_95 = float(rets[rets <= var_95].mean()) if (rets <= var_95).any() else np.nan

    out = {
        "median_month": float(rets.median()),
        "avg_month": float(rets.mean()),
        "std_month": float(rets.std(ddof=0)),
        "downside_dev_ann": downside_dev,
        "sortino": sortino,
        "calmar": calmar,
        "skew_monthly": float(rets.skew()),
        "kurtosis_monthly": float(rets.kurtosis()),
        "var_95_monthly": var_95,
        "cvar_95_monthly": cvar_95,
        "ulcer_index": ulcer_index(equity),
        "negative_months": int((rets < 0).sum()),
        "negative_month_rate": float((rets < 0).mean()),
        "nonpositive_months": int((rets <= 0).sum()),
        "nonpositive_month_rate": float((rets <= 0).mean()),
        "zero_months": int((rets == 0).sum()),
        "zero_month_rate": float((rets == 0).mean()),
        "big_loss_3pct_months": int((rets <= -0.03).sum()),
        "big_loss_3pct_rate": float((rets <= -0.03).mean()),
        "big_loss_5pct_months": int((rets <= -0.05).sum()),
        "big_loss_5pct_rate": float((rets <= -0.05).mean()),
        "big_gain_3pct_months": int((rets >= 0.03).sum()),
        "big_gain_3pct_rate": float((rets >= 0.03).mean()),
        "big_gain_5pct_months": int((rets >= 0.05).sum()),
        "big_gain_5pct_rate": float((rets >= 0.05).mean()),
        "avg_loss_month": float(downside.mean()) if len(downside) else 0.0,
        "median_loss_month": float(downside.median()) if len(downside) else 0.0,
        "avg_gain_month": float(rets[rets > 0].mean()) if (rets > 0).any() else 0.0,
    }

    out.update(streak_distribution(rets < 0, prefix="loss"))
    out.update(streak_distribution(rets > 0, prefix="gain"))
    out.update(return_bucket_stats(rets, prefix="return"))
    out.update(rolling_return_pain_stats(d, return_col=return_col, prefix="rolling_total"))

    return out


def blend_vs_a_stats(d: pd.DataFrame) -> dict:
    """Statystyki pokazujace, co B robi z wynikiem A."""
    required = {"return_a", "return_b", "combined_return"}
    if not required.issubset(d.columns):
        return {}

    a = d["return_a"].astype(float)
    b = d["return_b"].astype(float)
    c = d["combined_return"].astype(float)
    delta = c - a
    n = len(d)

    improves = delta > 0
    worsens = delta < 0

    a_neg = a < 0
    a_nonneg = a >= 0
    c_neg = c < 0
    c_nonneg = c >= 0

    b_reduces_a_loss = a_neg & (c > a)
    b_deepens_a_loss = a_neg & (c < a)
    b_turns_a_loss_to_nonloss = a_neg & c_nonneg
    b_turns_a_nonloss_to_loss = a_nonneg & c_neg

    corr_ab = float(a.corr(b)) if a.std(ddof=0) > 0 and b.std(ddof=0) > 0 else np.nan

    out = {
        "vs_a_avg_monthly_delta": float(delta.mean()),
        "vs_a_median_monthly_delta": float(delta.median()),
        "vs_a_total_delta_sum": float(delta.sum()),
        "vs_a_improved_months": int(improves.sum()),
        "vs_a_improved_month_rate": float(improves.mean()) if n else np.nan,
        "vs_a_worsened_months": int(worsens.sum()),
        "vs_a_worsened_month_rate": float(worsens.mean()) if n else np.nan,
        "vs_a_unchanged_months": int((delta == 0).sum()),
        "vs_a_b_reduces_a_loss_months": int(b_reduces_a_loss.sum()),
        "vs_a_b_reduces_a_loss_rate_all": float(b_reduces_a_loss.mean()) if n else np.nan,
        "vs_a_b_reduces_a_loss_rate_when_a_loses": float(b_reduces_a_loss.sum() / a_neg.sum()) if a_neg.sum() else np.nan,
        "vs_a_b_deepens_a_loss_months": int(b_deepens_a_loss.sum()),
        "vs_a_b_deepens_a_loss_rate_all": float(b_deepens_a_loss.mean()) if n else np.nan,
        "vs_a_b_deepens_a_loss_rate_when_a_loses": float(b_deepens_a_loss.sum() / a_neg.sum()) if a_neg.sum() else np.nan,
        "vs_a_b_turns_a_loss_to_nonloss_months": int(b_turns_a_loss_to_nonloss.sum()),
        "vs_a_b_turns_a_loss_to_nonloss_rate_when_a_loses": float(b_turns_a_loss_to_nonloss.sum() / a_neg.sum()) if a_neg.sum() else np.nan,
        "vs_a_b_turns_a_nonloss_to_loss_months": int(b_turns_a_nonloss_to_loss.sum()),
        "vs_a_b_turns_a_nonloss_to_loss_rate_when_a_nonloss": float(b_turns_a_nonloss_to_loss.sum() / a_nonneg.sum()) if a_nonneg.sum() else np.nan,
        "return_corr_a_b": corr_ab,
        "months_a_down_b_up": int(((a < 0) & (b > 0)).sum()),
        "months_a_up_b_down": int(((a > 0) & (b < 0)).sum()),
        "months_b_better_than_a": int((b > a).sum()),
        "months_b_worse_than_a": int((b < a).sum()),
        "avg_b_minus_a": float((b - a).mean()),
        "median_b_minus_a": float((b - a).median()),
    }

    out["vs_a_avg_help_when_improves"] = float(delta[improves].mean()) if improves.any() else 0.0
    out["vs_a_avg_damage_when_worsens"] = float(delta[worsens].mean()) if worsens.any() else 0.0

    return out


def dynamic_regime_stats(d: pd.DataFrame) -> dict:
    if "dynamic_regime" not in d.columns:
        return {}

    n = len(d)
    counts = d["dynamic_regime"].value_counts(dropna=False).to_dict()

    out = {
        "dynamic_avg_weight_a": float(d["weight_a"].mean()) if "weight_a" in d.columns else np.nan,
        "dynamic_avg_weight_b": float(d["weight_b"].mean()) if "weight_b" in d.columns else np.nan,
    }

    for regime in [
        "a_risk_b_risk__80_20",
        "a_cash_b_risk__b_100",
        "a_risk_b_cash__a_100",
        "a_cash_b_cash__cash",
    ]:
        count = int(counts.get(regime, 0))
        out[f"dynamic_{regime}_months"] = count
        out[f"dynamic_{regime}_rate"] = float(count / n) if n else np.nan

    return out


def calc_metrics(
    df: pd.DataFrame,
    return_col: str,
    equity_col: str,
    benchmark_return_col: str | None = None,
    benchmark_equity_col: str | None = None,
    period_name: str = "FULL",
    period_type: str = "full",
    include_blend_vs_a: bool = True,
) -> dict:
    d = df.copy()
    months = len(d)

    if months == 0:
        raise ValueError(f"Pusty okres: {period_name}")

    start = d["date"].iloc[0]
    end = d["date"].iloc[-1]

    rets = d[return_col].astype(float)
    equity = d[equity_col].astype(float)

    final_equity = float(equity.iloc[-1])
    years = months / 12.0

    cagr = final_equity ** (1.0 / years) - 1.0 if final_equity > 0 and years > 0 else np.nan
    ann_vol = float(rets.std(ddof=0) * math.sqrt(12))
    sharpe = float((rets.mean() * 12) / ann_vol) if ann_vol > 0 else np.nan

    mdd, mdd_start, mdd_bottom, mdd_recovery, mdd_duration = max_drawdown(
        pd.Series(equity.values, index=d["date"])
    )

    out = {
        "period_type": period_type,
        "period_name": period_name,
        "start": start.date().isoformat(),
        "end": end.date().isoformat(),
        "months": months,
        "cagr": cagr,
        "ann_vol": ann_vol,
        "sharpe": sharpe,
        "max_drawdown": mdd,
        "final_equity": final_equity,
        "max_drawdown_start": mdd_start.date().isoformat() if mdd_start is not None else None,
        "max_drawdown_bottom": mdd_bottom.date().isoformat() if mdd_bottom is not None else None,
        "max_drawdown_recovery": mdd_recovery.date().isoformat() if mdd_recovery is not None else None,
        "max_drawdown_duration_months": mdd_duration,
        "best_month": float(rets.max()),
        "worst_month": float(rets.min()),
        "positive_month_rate": float((rets > 0).mean()),
    }

    out.update(advanced_return_stats(d, return_col=return_col, equity_col=equity_col))

    if include_blend_vs_a:
        out.update(blend_vs_a_stats(d))

    out.update(dynamic_regime_stats(d))

    if benchmark_return_col and benchmark_return_col in d.columns:
        b_rets = d[benchmark_return_col].astype(float)
        b_equity = equity_from_returns(b_rets)

        b_final = float(b_equity.iloc[-1])
        b_cagr = b_final ** (1.0 / years) - 1.0 if b_final > 0 and years > 0 else np.nan
        b_vol = float(b_rets.std(ddof=0) * math.sqrt(12))
        b_sharpe = float((b_rets.mean() * 12) / b_vol) if b_vol > 0 else np.nan

        b_mdd, _, _, _, _ = max_drawdown(pd.Series(b_equity.values, index=d["date"]))

        out.update(
            {
                "benchmark_cagr": b_cagr,
                "benchmark_ann_vol": b_vol,
                "benchmark_sharpe": b_sharpe,
                "benchmark_max_drawdown": b_mdd,
                "benchmark_final_equity": b_final,
                "cagr_vs_benchmark": cagr - b_cagr,
                "sharpe_vs_benchmark": sharpe - b_sharpe,
                "maxdd_vs_benchmark": abs(mdd) - abs(b_mdd),
                "avg_monthly_excess": float((rets - b_rets).mean()),
                "hit_rate_excess": float((rets > b_rets).mean()),
                "cum_excess_sum": float((rets - b_rets).sum()),
            }
        )

    return out


def make_combined(df: pd.DataFrame, weight_a: float, weight_b: float) -> pd.DataFrame:
    d = df.copy()

    total = weight_a + weight_b
    if not np.isclose(total, 1.0):
        weight_a = weight_a / total
        weight_b = weight_b / total

    d["combined_return"] = weight_a * d["return_a"] + weight_b * d["return_b"]
    d["combined_equity"] = equity_from_returns(d["combined_return"])

    d["weight_a"] = weight_a
    d["weight_b"] = weight_b

    if "benchmark_return_a" in d.columns:
        d["benchmark_return"] = d["benchmark_return_a"]
    elif "benchmark_return_b" in d.columns:
        d["benchmark_return"] = d["benchmark_return_b"]

    if "benchmark_return" in d.columns:
        d["benchmark_equity"] = equity_from_returns(d["benchmark_return"])

    d["excess_return"] = d["combined_return"] - d.get("benchmark_return", 0.0)
    d["delta_vs_a"] = d["combined_return"] - d["return_a"]
    d["delta_vs_b"] = d["combined_return"] - d["return_b"]
    d["b_better_than_a"] = d["return_b"] > d["return_a"]
    d["b_reduces_a_loss"] = (d["return_a"] < 0) & (d["combined_return"] > d["return_a"])
    d["b_deepens_a_loss"] = (d["return_a"] < 0) & (d["combined_return"] < d["return_a"])
    d["b_turns_a_loss_to_nonloss"] = (d["return_a"] < 0) & (d["combined_return"] >= 0)
    d["b_turns_a_nonloss_to_loss"] = (d["return_a"] >= 0) & (d["combined_return"] < 0)

    return d


def make_dynamic_combined(
    df: pd.DataFrame,
    holdings_a: pd.DataFrame | None,
    holdings_b: pd.DataFrame | None,
    weight_label: str = DYNAMIC_WEIGHT_LABEL,
) -> pd.DataFrame:
    """Buduje dynamic_combined na podstawie stanu risk/cash z miesiecznych holdings.

    Reguly:
       A risk, B risk -> 80/20
       A cash, B risk -> B 100
       A cash, B cash -> cash
       A risk, B cash -> A 100
    """
    if holdings_a is None:
        raise ValueError("dynamic_combined wymaga holdings_a z weights_used_json")
    if holdings_b is None:
        raise ValueError("dynamic_combined wymaga holdings_b z weights_used_json")

    map_a = holdings_to_monthly_weight_map(holdings_a)
    map_b = holdings_to_monthly_weight_map(holdings_b)

    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values("date").reset_index(drop=True)

    records: list[dict[str, Any]] = []
    previous_signature: tuple[tuple[str, float], ...] | None = None

    missing_a = 0
    missing_b = 0

    for _, row in d.iterrows():
        dt = pd.Timestamp(row["date"])

        if dt not in map_a:
            missing_a += 1
        if dt not in map_b:
            missing_b += 1

        weights_a = map_a.get(dt, {"_CASH": 1.0})
        weights_b = map_b.get(dt, {"_CASH": 1.0})

        state_a = classify_risk_cash(weights_a)
        state_b = classify_risk_cash(weights_b)
        dynamic_weight_a, dynamic_weight_b, dynamic_regime = dynamic_allocation_for_states(state_a, state_b)

        if state_a == "cash" and state_b == "cash":
            combined_return = float(DYNAMIC_CASH_RETURN)
            combined_weights = {"_CASH": 1.0}
        else:
            combined_return = float(dynamic_weight_a * row["return_a"] + dynamic_weight_b * row["return_b"])
            combined_weights = combine_weight_dicts(
                weights_a=weights_a if dynamic_weight_a > EPS else {},
                weights_b=weights_b if dynamic_weight_b > EPS else {},
                weight_a=dynamic_weight_a,
                weight_b=dynamic_weight_b,
            )

        sig = weights_signature(combined_weights)
        signal_changed = int(previous_signature is None or sig != previous_signature)
        previous_signature = sig

        records.append(
            {
                "combined_return": combined_return,
                "weight_a": float(dynamic_weight_a),
                "weight_b": float(dynamic_weight_b),
                "dynamic_state_a": state_a,
                "dynamic_state_b": state_b,
                "dynamic_regime": dynamic_regime,
                "combined_weights_json": json.dumps(combined_weights, ensure_ascii=False, sort_keys=True),
                "combined_signal_changed": signal_changed,
            }
        )

    if missing_a:
        print(f"[WARN] dynamic_combined: brak holdings A dla {missing_a} miesiecy; traktuje jako _CASH.")
    if missing_b:
        print(f"[WARN] dynamic_combined: brak holdings B dla {missing_b} miesiecy; traktuje jako _CASH.")

    dyn = pd.concat([d, pd.DataFrame(records)], axis=1)
    dyn["combined_equity"] = equity_from_returns(dyn["combined_return"])
    dyn["weight_label"] = weight_label

    if "benchmark_return_a" in dyn.columns:
        dyn["benchmark_return"] = dyn["benchmark_return_a"]
    elif "benchmark_return_b" in dyn.columns:
        dyn["benchmark_return"] = dyn["benchmark_return_b"]

    if "benchmark_return" in dyn.columns:
        dyn["benchmark_equity"] = equity_from_returns(dyn["benchmark_return"])

    dyn["excess_return"] = dyn["combined_return"] - dyn.get("benchmark_return", 0.0)
    dyn["delta_vs_a"] = dyn["combined_return"] - dyn["return_a"]
    dyn["delta_vs_b"] = dyn["combined_return"] - dyn["return_b"]
    dyn["b_better_than_a"] = dyn["return_b"] > dyn["return_a"]
    dyn["b_reduces_a_loss"] = (dyn["return_a"] < 0) & (dyn["combined_return"] > dyn["return_a"])
    dyn["b_deepens_a_loss"] = (dyn["return_a"] < 0) & (dyn["combined_return"] < dyn["return_a"])
    dyn["b_turns_a_loss_to_nonloss"] = (dyn["return_a"] < 0) & (dyn["combined_return"] >= 0)
    dyn["b_turns_a_nonloss_to_loss"] = (dyn["return_a"] >= 0) & (dyn["combined_return"] < 0)

    return dyn


def rolling_summary(d: pd.DataFrame, weight_label: str) -> pd.DataFrame:
    rows = []

    for window in ROLLING_WINDOWS_MONTHS:
        if len(d) < window:
            continue

        for start_idx in range(0, len(d) - window + 1):
            sub = d.iloc[start_idx : start_idx + window].copy()
            # Rolling ma equity liczona od poczatku calego backtestu, wiec resetujemy ja dla okna.
            sub["combined_equity_window"] = equity_from_returns(sub["combined_return"])
            metrics = calc_metrics(
                sub,
                return_col="combined_return",
                equity_col="combined_equity_window",
                benchmark_return_col="benchmark_return" if "benchmark_return" in sub.columns else None,
                period_name=f"rolling_{window}",
                period_type="rolling",
            )
            metrics["window_months"] = window
            metrics["window_start"] = sub["date"].iloc[0].date().isoformat()
            metrics["window_end"] = sub["date"].iloc[-1].date().isoformat()
            metrics["weight_label"] = weight_label
            rows.append(metrics)

    return pd.DataFrame(rows)


def rolling_aggregate(rolling_df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for (weight_label, window), g in rolling_df.groupby(["weight_label", "window_months"]):
        row = {
            "weight_label": weight_label,
            "window_months": window,
            "n_windows": len(g),
            "median_cagr": g["cagr"].median(),
            "median_sharpe": g["sharpe"].median(),
            "worst_cagr": g["cagr"].min(),
            "best_cagr": g["cagr"].max(),
            "worst_max_drawdown": g["max_drawdown"].min(),
            "median_max_drawdown": g["max_drawdown"].median(),
            "median_negative_month_rate": g["negative_month_rate"].median(),
            "worst_negative_month_rate": g["negative_month_rate"].max(),
            "median_loss_streak_max": g["loss_streak_max"].median(),
            "worst_loss_streak_max": g["loss_streak_max"].max(),
            "median_big_loss_3pct_rate": g["big_loss_3pct_rate"].median(),
            "worst_big_loss_3pct_rate": g["big_loss_3pct_rate"].max(),
            "median_rolling_12m_worst_return": g["rolling_total_12m_worst_return"].median(),
            "worst_rolling_12m_worst_return": g["rolling_total_12m_worst_return"].min(),
        }

        if "cagr_vs_benchmark" in g.columns:
            row.update(
                {
                    "pct_windows_cagr_beats_benchmark": float((g["cagr_vs_benchmark"] > 0).mean()),
                    "pct_windows_sharpe_beats_benchmark": float((g["sharpe_vs_benchmark"] > 0).mean()),
                    "pct_windows_lower_dd_than_benchmark": float((g["maxdd_vs_benchmark"] < 0).mean()),
                    "median_cagr_vs_benchmark": g["cagr_vs_benchmark"].median(),
                    "worst_cagr_vs_benchmark": g["cagr_vs_benchmark"].min(),
                    "best_cagr_vs_benchmark": g["cagr_vs_benchmark"].max(),
                }
            )

        if "vs_a_worsened_month_rate" in g.columns:
            row.update(
                {
                    "median_vs_a_worsened_month_rate": g["vs_a_worsened_month_rate"].median(),
                    "median_vs_a_b_deepens_a_loss_rate_when_a_loses": g["vs_a_b_deepens_a_loss_rate_when_a_loses"].median(),
                    "median_vs_a_b_reduces_a_loss_rate_when_a_loses": g["vs_a_b_reduces_a_loss_rate_when_a_loses"].median(),
                }
            )

        if "dynamic_avg_weight_a" in g.columns:
            row.update(
                {
                    "median_dynamic_avg_weight_a": g["dynamic_avg_weight_a"].median(),
                    "median_dynamic_avg_weight_b": g["dynamic_avg_weight_b"].median(),
                }
            )

        rows.append(row)

    return pd.DataFrame(rows)


def add_period_equity(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["combined_equity_period"] = equity_from_returns(d["combined_return"])
    return d


def load_holdings(
    path: Path | None,
    suffix: str,
    strategy_name: str | None = None,
) -> pd.DataFrame | None:
    """Wczytuje holdings z dwoch mozliwych formatow.

    1) Format dlugi:
       date,ticker,weight

    2) Format miesieczny z JSON:
       date,strategy,weights_used_json
       gdzie weights_used_json = {"xlv.us": 0.5, "xlp.us": 0.5}

    Zwraca zawsze format:
       date, strategy, ticker, weight, source
    """

    if path is None:
        print(f"[INFO] Holdings {suffix.upper()} CSV nie podane, pomijam.")
        return None

    if not path.exists():
        print(f"[WARN] Holdings {suffix.upper()} CSV nie istnieje: {path}")
        return None

    raw = pd.read_csv(path)
    raw.columns = [c.strip() for c in raw.columns]

    if "date" not in raw.columns:
        raise ValueError(f"{path} nie ma kolumny date")

    raw["date"] = pd.to_datetime(raw["date"])

    # Jezeli plik zawiera wiele strategii, filtrujemy tylko te konkretna.
    if strategy_name is not None and "strategy" in raw.columns:
        before = len(raw)
        raw = raw[raw["strategy"].astype(str) == str(strategy_name)].copy()
        after = len(raw)

        if after == 0:
            print(f"[WARN] Holdings {suffix.upper()}: nie znaleziono strategy == {strategy_name}")
            print(f"[WARN] Plik: {path}")
            return None

        print(f"[INFO] Holdings {suffix.upper()}: filtr strategy {after}/{before} rows")

    # Format 1: juz jest date,ticker,weight.
    if {"date", "ticker", "weight"}.issubset(raw.columns):
        cols = ["date", "strategy", "ticker", "weight"] if "strategy" in raw.columns else ["date", "ticker", "weight"]
        out = raw[cols].copy()

        if "strategy" not in out.columns:
            out["strategy"] = strategy_name or ""

        out["ticker"] = out["ticker"].map(normalize_ticker)
        out["weight"] = out["weight"].astype(float)
        out["source"] = suffix
        return out[["date", "strategy", "ticker", "weight", "source"]]

    # Format 2: weights_used_json.
    if HOLDINGS_WEIGHT_COLUMN in raw.columns:
        rows = []

        for _, r in raw.iterrows():
            value = r.get(HOLDINGS_WEIGHT_COLUMN)

            try:
                weights = parse_weights_json(value)
            except Exception as e:
                print(f"[WARN] Nie moge sparsowac JSON dla {suffix.upper()} date={r['date']}: {value} | {e}")
                continue

            if not weights:
                continue

            for ticker, weight in weights.items():
                rows.append(
                    {
                        "date": r["date"],
                        "strategy": r.get("strategy", strategy_name or ""),
                        "ticker": normalize_ticker(ticker),
                        "weight": float(weight),
                        "source": suffix,
                    }
                )

        out = pd.DataFrame(rows)

        if out.empty:
            print(f"[WARN] Holdings {suffix.upper()} po parsowaniu JSON sa puste.")
            return None

        return out[["date", "strategy", "ticker", "weight", "source"]]

    raise ValueError(
        f"{path} nie ma ani kolumn date/ticker/weight, ani kolumny {HOLDINGS_WEIGHT_COLUMN}. "
        f"Dostepne kolumny: {list(raw.columns)}"
    )


def holdings_to_monthly_weight_map(holdings: pd.DataFrame | None) -> dict[pd.Timestamp, dict[str, float]]:
    if holdings is None or holdings.empty:
        return {}

    h = holdings.copy()
    h["date"] = pd.to_datetime(h["date"])
    h["ticker"] = h["ticker"].map(normalize_ticker)
    h["weight"] = h["weight"].astype(float)

    out: dict[pd.Timestamp, dict[str, float]] = {}
    for dt, g in h.groupby("date"):
        weights: dict[str, float] = {}
        for _, row in g.iterrows():
            ticker = normalize_ticker(row["ticker"])
            weights[ticker] = weights.get(ticker, 0.0) + float(row["weight"])
        out[pd.Timestamp(dt)] = normalize_weights(weights)

    return out


def make_replay_source_monthly(
    combined: pd.DataFrame,
    holdings_a: pd.DataFrame | None,
    holdings_b: pd.DataFrame | None,
    weight_a: float,
    weight_b: float,
    weight_label: str,
) -> pd.DataFrame | None:
    """Buduje plik monthly zgodny z replay_mapped_to_uk.py dla statycznych wag.

    Replay potrzebuje glownie:
       date,strategy,signal_changed,weights_used_json

    Wagi sa laczone jako:
       combined_weights = weight_a * weights_A + weight_b * weights_B

    Dla najwierniejszego odtworzenia combined w UK replay polecam potem uzyc:
       --execution-mode target_each_month
    """
    if weight_a > EPS and holdings_a is None:
        print(f"[WARN] {weight_label}: brak holdings A, nie zapisuje replay-source.")
        return None
    if weight_b > EPS and holdings_b is None:
        print(f"[WARN] {weight_label}: brak holdings B, nie zapisuje replay-source.")
        return None

    map_a = holdings_to_monthly_weight_map(holdings_a)
    map_b = holdings_to_monthly_weight_map(holdings_b)

    c = combined.copy()
    c["date"] = pd.to_datetime(c["date"])
    c = c.sort_values("date")

    rows: list[dict[str, Any]] = []
    previous_signature: tuple[tuple[str, float], ...] | None = None

    for _, row in c.iterrows():
        dt = pd.Timestamp(row["date"])

        weights_a = map_a.get(dt, {"_CASH": 1.0}) if weight_a > EPS else {}
        weights_b = map_b.get(dt, {"_CASH": 1.0}) if weight_b > EPS else {}

        combined_weights = combine_weight_dicts(
            weights_a=weights_a,
            weights_b=weights_b,
            weight_a=weight_a,
            weight_b=weight_b,
        )

        sig = weights_signature(combined_weights)
        signal_changed = int(previous_signature is None or sig != previous_signature)
        previous_signature = sig

        rows.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "strategy": f"{weight_label}__combined_replay_source",
                "signal_changed": signal_changed,
                "weights_used_json": json.dumps(combined_weights, ensure_ascii=False, sort_keys=True),
                "weight_label": weight_label,
                "weight_a": float(weight_a),
                "weight_b": float(weight_b),
                "source_return_a": float(row.get("return_a", np.nan)),
                "source_return_b": float(row.get("return_b", np.nan)),
                "source_combined_return": float(row.get("combined_return", np.nan)),
                "source_combined_equity": float(row.get("combined_equity", np.nan)),
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return None

    # Kontrola sumy wag.
    sums = out["weights_used_json"].map(lambda x: sum(parse_weights_json(x).values()))
    max_diff = float((sums - 1.0).abs().max())
    if max_diff > 1e-8:
        print(f"[WARN] {weight_label}: max roznica sumy wag od 1.0 = {max_diff:.12f}")

    return out


def make_dynamic_replay_source_monthly(
    combined: pd.DataFrame,
    weight_label: str = DYNAMIC_WEIGHT_LABEL,
) -> pd.DataFrame | None:
    """Buduje replay-source dla dynamic_combined.

    Tu nie przeliczamy juz wag z fixed weight_a/weight_b, tylko bierzemy gotowe
    combined_weights_json z make_dynamic_combined.
    """
    required = {"date", "combined_weights_json", "combined_return", "combined_equity"}
    missing = required - set(combined.columns)
    if missing:
        raise ValueError(f"dynamic replay source: brakuje kolumn {missing}")

    c = combined.copy()
    c["date"] = pd.to_datetime(c["date"])
    c = c.sort_values("date")

    rows: list[dict[str, Any]] = []
    for _, row in c.iterrows():
        dt = pd.Timestamp(row["date"])
        weights_json = row["combined_weights_json"]

        rows.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "strategy": f"{weight_label}__combined_replay_source",
                "signal_changed": int(row.get("combined_signal_changed", 1)),
                "weights_used_json": weights_json,
                "weight_label": weight_label,
                "weight_a": float(row.get("weight_a", np.nan)),
                "weight_b": float(row.get("weight_b", np.nan)),
                "dynamic_state_a": row.get("dynamic_state_a", ""),
                "dynamic_state_b": row.get("dynamic_state_b", ""),
                "dynamic_regime": row.get("dynamic_regime", ""),
                "source_return_a": float(row.get("return_a", np.nan)),
                "source_return_b": float(row.get("return_b", np.nan)),
                "source_combined_return": float(row.get("combined_return", np.nan)),
                "source_combined_equity": float(row.get("combined_equity", np.nan)),
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return None

    sums = out["weights_used_json"].map(lambda x: sum(parse_weights_json(x).values()))
    max_diff = float((sums - 1.0).abs().max())
    if max_diff > 1e-8:
        print(f"[WARN] {weight_label}: max roznica sumy wag od 1.0 = {max_diff:.12f}")

    return out


def diversification_summary_from_ticker_frame(by_ticker: pd.DataFrame, weight_label: str) -> dict:
    if by_ticker.empty:
        return {}

    by_ticker = by_ticker.copy()
    by_ticker["date"] = pd.to_datetime(by_ticker["date"])
    by_ticker["ticker"] = by_ticker["ticker"].map(normalize_ticker)
    by_ticker["combined_weight"] = by_ticker["combined_weight"].astype(float)

    if "sector" not in by_ticker.columns:
        by_ticker["sector"] = "UNKNOWN"
    by_ticker["sector"] = by_ticker["sector"].fillna("UNKNOWN")

    rows = []
    for date, g in by_ticker.groupby("date"):
        weights = g["combined_weight"].astype(float)
        sector_weights = g.groupby("sector")["combined_weight"].sum().sort_values(ascending=False)

        hhi_ticker = float(np.square(weights).sum())
        effective_n_tickers = float(1.0 / hhi_ticker) if hhi_ticker > 0 else np.nan
        hhi_sector = float(np.square(sector_weights).sum())
        effective_n_sectors = float(1.0 / hhi_sector) if hhi_sector > 0 else np.nan

        rows.append(
            {
                "date": date,
                "unique_tickers": int(g["ticker"].nunique()),
                "top1_ticker_weight": float(weights.max()) if len(weights) else np.nan,
                "top3_ticker_weight": float(weights.nlargest(3).sum()) if len(weights) else np.nan,
                "top5_ticker_weight": float(weights.nlargest(5).sum()) if len(weights) else np.nan,
                "hhi_ticker": hhi_ticker,
                "effective_n_tickers": effective_n_tickers,
                "unique_sectors": int((sector_weights > 0).sum()),
                "top1_sector_weight": float(sector_weights.iloc[0]) if len(sector_weights) else np.nan,
                "hhi_sector": hhi_sector,
                "effective_n_sectors": effective_n_sectors,
            }
        )

    monthly_div = pd.DataFrame(rows)
    monthly_div["weight_label"] = weight_label
    monthly_div.to_csv(OUT_DIR / f"combined_diversification_monthly_{weight_label}.csv", index=False)

    return {
        "div_avg_unique_tickers": float(monthly_div["unique_tickers"].mean()),
        "div_min_unique_tickers": int(monthly_div["unique_tickers"].min()),
        "div_avg_top1_ticker_weight": float(monthly_div["top1_ticker_weight"].mean()),
        "div_avg_top3_ticker_weight": float(monthly_div["top3_ticker_weight"].mean()),
        "div_avg_top5_ticker_weight": float(monthly_div["top5_ticker_weight"].mean()),
        "div_avg_effective_n_tickers": float(monthly_div["effective_n_tickers"].mean()),
        "div_min_effective_n_tickers": float(monthly_div["effective_n_tickers"].min()),
        "div_avg_unique_sectors": float(monthly_div["unique_sectors"].mean()),
        "div_min_unique_sectors": int(monthly_div["unique_sectors"].min()),
        "div_avg_top1_sector_weight": float(monthly_div["top1_sector_weight"].mean()),
        "div_avg_effective_n_sectors": float(monthly_div["effective_n_sectors"].mean()),
        "div_min_effective_n_sectors": float(monthly_div["effective_n_sectors"].min()),
    }


def portfolio_diversification_summary(
    holdings_a: pd.DataFrame | None,
    holdings_b: pd.DataFrame | None,
    weight_a: float,
    weight_b: float,
    weight_label: str,
) -> dict:
    """Opcjonalne statystyki dywersyfikacji tickerow/sektorow dla statycznych wag."""
    if holdings_a is None and holdings_b is None:
        return {}

    frames = []
    if holdings_a is not None and weight_a > 0:
        ha = holdings_a.copy()
        ha["combined_weight"] = ha["weight"] * weight_a
        frames.append(ha)
    if holdings_b is not None and weight_b > 0:
        hb = holdings_b.copy()
        hb["combined_weight"] = hb["weight"] * weight_b
        frames.append(hb)

    if not frames:
        return {}

    h = pd.concat(frames, ignore_index=True)
    h["ticker"] = h["ticker"].map(normalize_ticker)

    by_ticker = (
        h.groupby(["date", "ticker"], as_index=False)["combined_weight"]
        .sum()
        .sort_values(["date", "combined_weight"], ascending=[True, False])
    )

    if "sector" in h.columns:
        sector_map = (
            h.dropna(subset=["sector"])
            .drop_duplicates("ticker")
            .set_index("ticker")["sector"]
            .to_dict()
        )
        by_ticker["sector"] = by_ticker["ticker"].map(sector_map).fillna("UNKNOWN")
    else:
        by_ticker["sector"] = "UNKNOWN"

    return diversification_summary_from_ticker_frame(by_ticker, weight_label=weight_label)


def portfolio_diversification_summary_from_monthly_weights(
    combined: pd.DataFrame,
    weight_label: str,
    weights_json_col: str = "combined_weights_json",
) -> dict:
    """Dywersyfikacja dla dynamic_combined z gotowych miesiecznych combined_weights_json."""
    if weights_json_col not in combined.columns:
        return {}

    rows: list[dict[str, Any]] = []

    for _, row in combined.iterrows():
        dt = pd.Timestamp(row["date"])
        weights = parse_weights_json(row[weights_json_col])
        weights = normalize_weights(weights)

        for ticker, weight in weights.items():
            if abs(weight) <= EPS:
                continue
            rows.append(
                {
                    "date": dt,
                    "ticker": normalize_ticker(ticker),
                    "combined_weight": float(weight),
                    "sector": "UNKNOWN",
                }
            )

    if not rows:
        return {}

    by_ticker = pd.DataFrame(rows)
    return diversification_summary_from_ticker_frame(by_ticker, weight_label=weight_label)


def save_friendly_tables(full_df: pd.DataFrame, named_df: pd.DataFrame, rolling_agg_df: pd.DataFrame) -> None:
    """Male, czytelne CSV pod szybka decyzje, bez setek kolumn."""
    decision_cols = [
        "weight_label",
        "weight_a",
        "weight_b",
        "dynamic_avg_weight_a",
        "dynamic_avg_weight_b",
        "dynamic_a_risk_b_risk__80_20_months",
        "dynamic_a_cash_b_risk__b_100_months",
        "dynamic_a_risk_b_cash__a_100_months",
        "dynamic_a_cash_b_cash__cash_months",
        "cagr",
        "ann_vol",
        "sharpe",
        "sortino",
        "calmar",
        "max_drawdown",
        "max_drawdown_duration_months",
        "final_equity",
        "negative_months",
        "negative_month_rate",
        "big_loss_3pct_months",
        "big_loss_5pct_months",
        "loss_streak_max",
        "loss_streak_len_2_count",
        "loss_streak_len_3_count",
        "loss_streak_len_4_count",
        "loss_streak_len_5plus_count",
        "rolling_total_12m_worst_return",
        "return_corr_a_b",
        "vs_a_improved_months",
        "vs_a_worsened_months",
        "vs_a_b_reduces_a_loss_months",
        "vs_a_b_deepens_a_loss_months",
        "vs_a_b_turns_a_loss_to_nonloss_months",
        "vs_a_b_turns_a_nonloss_to_loss_months",
        "div_avg_effective_n_tickers",
        "div_avg_top1_ticker_weight",
        "score_simple",
        "score_psychology",
        "score_balanced",
    ]
    decision_cols = [c for c in decision_cols if c in full_df.columns]
    full_df[decision_cols].to_csv(OUT_DIR / "combined_decision_table.csv", index=False)

    bucket_cols = ["weight_label", "weight_a", "weight_b"] + [
        c for c in full_df.columns if c.startswith("return_bucket_") and c.endswith("_count")
    ]
    bucket_cols = [c for c in bucket_cols if c in full_df.columns]
    full_df[bucket_cols].to_csv(OUT_DIR / "combined_return_histogram_buckets.csv", index=False)

    streak_cols = [
        "weight_label",
        "weight_a",
        "weight_b",
        "loss_streak_max",
        "loss_streak_count",
        "loss_streak_len_1_count",
        "loss_streak_len_2_count",
        "loss_streak_len_3_count",
        "loss_streak_len_4_count",
        "loss_streak_len_5plus_count",
        "loss_months_in_streak_2plus",
        "loss_months_in_streak_3plus",
        "loss_months_in_streak_4plus",
        "loss_months_in_streak_5plus",
    ]
    streak_cols = [c for c in streak_cols if c in full_df.columns]
    full_df[streak_cols].to_csv(OUT_DIR / "combined_loss_streaks.csv", index=False)

    b_effect_cols = [
        "weight_label",
        "weight_a",
        "weight_b",
        "return_corr_a_b",
        "vs_a_avg_monthly_delta",
        "vs_a_total_delta_sum",
        "vs_a_improved_months",
        "vs_a_improved_month_rate",
        "vs_a_worsened_months",
        "vs_a_worsened_month_rate",
        "vs_a_b_reduces_a_loss_months",
        "vs_a_b_reduces_a_loss_rate_when_a_loses",
        "vs_a_b_deepens_a_loss_months",
        "vs_a_b_deepens_a_loss_rate_when_a_loses",
        "vs_a_b_turns_a_loss_to_nonloss_months",
        "vs_a_b_turns_a_nonloss_to_loss_months",
        "avg_b_minus_a",
    ]
    b_effect_cols = [c for c in b_effect_cols if c in full_df.columns]
    full_df[b_effect_cols].to_csv(OUT_DIR / "combined_b_effect_vs_a.csv", index=False)

    dynamic_cols = [
        "weight_label",
        "months",
        "dynamic_avg_weight_a",
        "dynamic_avg_weight_b",
        "dynamic_a_risk_b_risk__80_20_months",
        "dynamic_a_risk_b_risk__80_20_rate",
        "dynamic_a_cash_b_risk__b_100_months",
        "dynamic_a_cash_b_risk__b_100_rate",
        "dynamic_a_risk_b_cash__a_100_months",
        "dynamic_a_risk_b_cash__a_100_rate",
        "dynamic_a_cash_b_cash__cash_months",
        "dynamic_a_cash_b_cash__cash_rate",
    ]
    dynamic_cols = [c for c in dynamic_cols if c in full_df.columns]
    if dynamic_cols:
        full_df[dynamic_cols].to_csv(OUT_DIR / "combined_dynamic_regimes.csv", index=False)

    if not rolling_agg_df.empty:
        rolling_cols = [
            "weight_label",
            "window_months",
            "n_windows",
            "median_cagr",
            "worst_cagr",
            "median_sharpe",
            "worst_max_drawdown",
            "median_max_drawdown",
            "median_negative_month_rate",
            "worst_negative_month_rate",
            "median_loss_streak_max",
            "worst_loss_streak_max",
            "median_rolling_12m_worst_return",
            "worst_rolling_12m_worst_return",
        ]
        rolling_cols = [c for c in rolling_cols if c in rolling_agg_df.columns]
        rolling_agg_df[rolling_cols].to_csv(OUT_DIR / "combined_rolling_psychology.csv", index=False)

    if not named_df.empty:
        named_cols = [
            "weight_label",
            "period_name",
            "start",
            "end",
            "months",
            "cagr",
            "sharpe",
            "sortino",
            "max_drawdown",
            "final_equity",
            "negative_month_rate",
            "loss_streak_max",
            "rolling_total_12m_worst_return",
            "vs_a_b_reduces_a_loss_months",
            "vs_a_b_deepens_a_loss_months",
        ]
        named_cols = [c for c in named_cols if c in named_df.columns]
        named_df[named_cols].to_csv(OUT_DIR / "combined_named_periods_readable.csv", index=False)


def add_full_and_period_outputs(
    combined: pd.DataFrame,
    label: str,
    weight_a_for_summary: float,
    weight_b_for_summary: float,
    csv_a: Path,
    csv_b: Path,
    full_rows: list[dict[str, Any]],
    named_rows: list[dict[str, Any]],
    rolling_rows: list[pd.DataFrame],
    diversification_stats: dict | None = None,
) -> None:
    """Wspolna obsluga metryk dla wariantu statycznego albo dynamicznego."""
    full = calc_metrics(
        combined,
        return_col="combined_return",
        equity_col="combined_equity",
        benchmark_return_col="benchmark_return" if "benchmark_return" in combined.columns else None,
        period_name="FULL",
        period_type="full",
    )
    full["weight_label"] = label
    full["weight_a"] = weight_a_for_summary
    full["weight_b"] = weight_b_for_summary
    full["strategy_a_file"] = csv_a.name
    full["strategy_b_file"] = csv_b.name
    full["strategy_a_name"] = combined["strategy_a"].iloc[0] if "strategy_a" in combined.columns else ""
    full["strategy_b_name"] = combined["strategy_b"].iloc[0] if "strategy_b" in combined.columns else ""
    if diversification_stats:
        full.update(diversification_stats)
    full_rows.append(full)

    # Named periods need equity reset per period.
    for name, start, end in NAMED_PERIODS:
        sub = combined[
            (combined["date"] >= pd.to_datetime(start))
            & (combined["date"] <= pd.to_datetime(end))
        ].copy()

        if sub.empty:
            continue

        sub["combined_equity_period"] = equity_from_returns(sub["combined_return"])

        named = calc_metrics(
            sub,
            return_col="combined_return",
            equity_col="combined_equity_period",
            benchmark_return_col="benchmark_return" if "benchmark_return" in sub.columns else None,
            period_name=name,
            period_type="named_period",
        )
        named["weight_label"] = label
        named["weight_a"] = weight_a_for_summary
        named["weight_b"] = weight_b_for_summary
        named_rows.append(named)

    # Rolling metrics.
    roll = rolling_summary(combined, label)
    if not roll.empty:
        roll["weight_a"] = weight_a_for_summary
        roll["weight_b"] = weight_b_for_summary
        rolling_rows.append(roll)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPLAY_SOURCE_OUT_DIR.mkdir(parents=True, exist_ok=True)

    csv_a = first_csv(STRATEGY_A_MONTHLY_DIR)
    csv_b = first_csv(STRATEGY_B_MONTHLY_DIR)

    print(f"[INFO] Strategy A CSV: {csv_a}")
    print(f"[INFO] Strategy B CSV: {csv_b}")

    a = load_monthly(csv_a, "a")
    b = load_monthly(csv_b, "b")

    strategy_a_name = a["strategy_a"].iloc[0] if "strategy_a" in a.columns else None
    strategy_b_name = b["strategy_b"].iloc[0] if "strategy_b" in b.columns else None

    holdings_a = load_holdings(HOLDINGS_A_CSV, "a", strategy_name=strategy_a_name)
    holdings_b = load_holdings(HOLDINGS_B_CSV, "b", strategy_name=strategy_b_name)

    df = pd.merge(a, b, on="date", how="inner").sort_values("date").reset_index(drop=True)

    if df.empty:
        raise ValueError("Brak wspolnych dat miedzy strategiami.")

    print(f"[INFO] Common date range: {df['date'].min().date()} -> {df['date'].max().date()}")
    print(f"[INFO] Common months: {len(df)}")

    if holdings_a is None and holdings_b is None:
        print("[INFO] Holdings CSV nie podane, pomijam dywersyfikacje tickerow/sektorow i replay-source.")
    else:
        print("[INFO] Holdings CSV znalezione, licze dywersyfikacje tickerow/sektorow i replay-source.")

    all_monthly = []
    full_rows: list[dict[str, Any]] = []
    named_rows: list[dict[str, Any]] = []
    rolling_rows: list[pd.DataFrame] = []
    replay_source_paths: list[Path] = []

    # 1) Stare statyczne warianty.
    for weight_a, weight_b in WEIGHTS_TO_TEST:
        label = f"a{int(round(weight_a * 100)):03d}_b{int(round(weight_b * 100)):03d}"

        combined = make_combined(df, weight_a, weight_b)
        combined["weight_label"] = label

        # Plik monthly z normalnymi combined_return/equity.
        monthly_out = OUT_DIR / f"combined_monthly_{label}.csv"
        combined.to_csv(monthly_out, index=False)

        # Plik udajacy normalny *_monthly.csv, ale z wagami combined, pod replay UK.
        replay_source = make_replay_source_monthly(
            combined=combined,
            holdings_a=holdings_a,
            holdings_b=holdings_b,
            weight_a=weight_a,
            weight_b=weight_b,
            weight_label=label,
        )
        if replay_source is not None:
            replay_out = REPLAY_SOURCE_OUT_DIR / f"combined_for_replay_monthly_{label}.csv"
            replay_source.to_csv(replay_out, index=False)
            replay_source_paths.append(replay_out)

        diversification_stats = portfolio_diversification_summary(
            holdings_a=holdings_a,
            holdings_b=holdings_b,
            weight_a=weight_a,
            weight_b=weight_b,
            weight_label=label,
        )

        add_full_and_period_outputs(
            combined=combined,
            label=label,
            weight_a_for_summary=weight_a,
            weight_b_for_summary=weight_b,
            csv_a=csv_a,
            csv_b=csv_b,
            full_rows=full_rows,
            named_rows=named_rows,
            rolling_rows=rolling_rows,
            diversification_stats=diversification_stats,
        )

        all_monthly.append(combined)

    # 2) Nowy dynamic_combined.
    if INCLUDE_DYNAMIC_COMBINED:
        if holdings_a is None or holdings_b is None:
            print("[WARN] dynamic_combined pominiety, bo brakuje holdings A albo B z weights_used_json.")
        else:
            label = DYNAMIC_WEIGHT_LABEL
            print(f"[INFO] Licze {label}...")

            dynamic_combined = make_dynamic_combined(
                df=df,
                holdings_a=holdings_a,
                holdings_b=holdings_b,
                weight_label=label,
            )

            monthly_out = OUT_DIR / f"combined_monthly_{label}.csv"
            dynamic_combined.to_csv(monthly_out, index=False)
			
            # Attribution dynamic_combined vs statyczne 80/20.
            static_8020_for_attr = make_combined(df, 0.80, 0.20)[
                ["date", "combined_return"]
            ].rename(columns={"combined_return": "static_8020_return"})
            
            attr = dynamic_combined.merge(static_8020_for_attr, on="date", how="left")
            attr["dynamic_minus_8020"] = attr["combined_return"] - attr["static_8020_return"]
            
            attr["dynamic_equity"] = equity_from_returns(attr["combined_return"])
            attr["static_8020_equity"] = equity_from_returns(attr["static_8020_return"])
            attr["relative_equity_dynamic_vs_8020"] = attr["dynamic_equity"] / attr["static_8020_equity"]
            
            attr.to_csv(OUT_DIR / "combined_dynamic_vs_static_8020_monthly_attribution.csv", index=False)
            
            regime_attr = (
                attr.groupby("dynamic_regime", dropna=False)
                .agg(
                    months=("date", "count"),
                    avg_dynamic_return=("combined_return", "mean"),
                    avg_static_8020_return=("static_8020_return", "mean"),
                    avg_dynamic_minus_8020=("dynamic_minus_8020", "mean"),
                    sum_dynamic_minus_8020=("dynamic_minus_8020", "sum"),
                    hit_rate_dynamic_beats_8020=("dynamic_minus_8020", lambda x: float((x > 0).mean())),
                    worst_dynamic_minus_8020=("dynamic_minus_8020", "min"),
                    best_dynamic_minus_8020=("dynamic_minus_8020", "max"),
                )
                .reset_index()
            )
            
            regime_attr.to_csv(OUT_DIR / "combined_dynamic_vs_static_8020_regime_attribution.csv", index=False)
            
            print("\n=== DYNAMIC VS STATIC 80/20 ATTRIBUTION ===")
            print(regime_attr.to_string(index=False))

            replay_source = make_dynamic_replay_source_monthly(
                combined=dynamic_combined,
                weight_label=label,
            )
            if replay_source is not None:
                replay_out = REPLAY_SOURCE_OUT_DIR / f"combined_for_replay_monthly_{label}.csv"
                replay_source.to_csv(replay_out, index=False)
                replay_source_paths.append(replay_out)

            diversification_stats = portfolio_diversification_summary_from_monthly_weights(
                combined=dynamic_combined,
                weight_label=label,
                weights_json_col="combined_weights_json",
            )

            add_full_and_period_outputs(
                combined=dynamic_combined,
                label=label,
                weight_a_for_summary=float(dynamic_combined["weight_a"].mean()),
                weight_b_for_summary=float(dynamic_combined["weight_b"].mean()),
                csv_a=csv_a,
                csv_b=csv_b,
                full_rows=full_rows,
                named_rows=named_rows,
                rolling_rows=rolling_rows,
                diversification_stats=diversification_stats,
            )

            all_monthly.append(dynamic_combined)

            print("[INFO] dynamic_combined regime counts:")
            print(dynamic_combined["dynamic_regime"].value_counts().to_string())

    full_df = pd.DataFrame(full_rows)
    named_df = pd.DataFrame(named_rows)
    rolling_df = pd.concat(rolling_rows, ignore_index=True) if rolling_rows else pd.DataFrame()
    rolling_agg_df = rolling_aggregate(rolling_df) if not rolling_df.empty else pd.DataFrame()
    monthly_df = pd.concat(all_monthly, ignore_index=True)

    # Ranking pomocniczy 1: klasyczny, lekko risk-adjusted.
    full_df["score_simple"] = (
        full_df["cagr"] * 1000.0
        + full_df["sharpe"].fillna(0.0) * 25.0
        - full_df["max_drawdown"].abs() * 100.0
    )

    # Ranking pomocniczy 2: psychologiczny.
    full_df["score_psychology"] = (
        full_df["cagr"] * 800.0
        + full_df["sortino"].fillna(0.0) * 20.0
        - full_df["negative_month_rate"] * 80.0
        - full_df["big_loss_3pct_rate"] * 120.0
        - full_df["loss_streak_max"] * 3.0
        - full_df["rolling_total_12m_worst_return"].abs() * 80.0
    )

    # Ranking pomocniczy 3: zbalansowany.
    full_df["score_balanced"] = (
        full_df["cagr"] * 900.0
        + full_df["sharpe"].fillna(0.0) * 20.0
        + full_df["sortino"].fillna(0.0) * 10.0
        - full_df["max_drawdown"].abs() * 120.0
        - full_df["negative_month_rate"] * 50.0
        - full_df["loss_streak_max"] * 2.0
        - full_df.get("vs_a_b_deepens_a_loss_rate_when_a_loses", pd.Series(0.0, index=full_df.index)).fillna(0.0) * 25.0
    )

    # Jezeli masz holdings, dodajemy bonus/kare za realna dywersyfikacje tickerow/sektorow.
    if "div_avg_effective_n_tickers" in full_df.columns:
        full_df["score_balanced"] += full_df["div_avg_effective_n_tickers"].fillna(0.0) * 2.0
        full_df["score_balanced"] -= full_df["div_avg_top1_ticker_weight"].fillna(0.0) * 20.0
        full_df["score_balanced"] -= full_df["div_avg_top1_sector_weight"].fillna(0.0) * 20.0

    full_df = full_df.sort_values("score_balanced", ascending=False).reset_index(drop=True)

    full_df.to_csv(OUT_DIR / "combined_full_summary.csv", index=False)
    named_df.to_csv(OUT_DIR / "combined_named_periods.csv", index=False)
    rolling_df.to_csv(OUT_DIR / "combined_rolling_windows.csv", index=False)
    rolling_agg_df.to_csv(OUT_DIR / "combined_rolling_aggregate.csv", index=False)
    monthly_df.to_csv(OUT_DIR / "combined_all_monthly.csv", index=False)

    save_friendly_tables(full_df, named_df, rolling_agg_df)

    print("\n=== DECISION TABLE ===")
    cols = [
        "weight_label",
        "weight_a",
        "weight_b",
        "dynamic_avg_weight_a",
        "dynamic_avg_weight_b",
        "cagr",
        "ann_vol",
        "sharpe",
        "sortino",
        "max_drawdown",
        "final_equity",
        "negative_months",
        "negative_month_rate",
        "loss_streak_max",
        "big_loss_3pct_months",
        "rolling_total_12m_worst_return",
        "return_corr_a_b",
        "vs_a_b_reduces_a_loss_months",
        "vs_a_b_deepens_a_loss_months",
        "vs_a_b_turns_a_loss_to_nonloss_months",
        "vs_a_b_turns_a_nonloss_to_loss_months",
        "div_avg_effective_n_tickers",
        "div_avg_top1_ticker_weight",
        "score_balanced",
    ]
    cols = [c for c in cols if c in full_df.columns]
    print(full_df[cols].to_string(index=False))

    print("\n=== DYNAMIC REGIMES ===")
    dynamic_cols = [
        "weight_label",
        "months",
        "dynamic_avg_weight_a",
        "dynamic_avg_weight_b",
        "dynamic_a_risk_b_risk__80_20_months",
        "dynamic_a_cash_b_risk__b_100_months",
        "dynamic_a_risk_b_cash__a_100_months",
        "dynamic_a_cash_b_cash__cash_months",
    ]
    dynamic_cols = [c for c in dynamic_cols if c in full_df.columns]
    if dynamic_cols:
        print(full_df[dynamic_cols].to_string(index=False))
    else:
        print("Brak dynamic_combined albo brak kolumn dynamicznych.")

    print("\n=== LOSS STREAKS ===")
    streak_cols = [
        "weight_label",
        "negative_months",
        "loss_streak_max",
        "loss_streak_len_1_count",
        "loss_streak_len_2_count",
        "loss_streak_len_3_count",
        "loss_streak_len_4_count",
        "loss_streak_len_5plus_count",
    ]
    streak_cols = [c for c in streak_cols if c in full_df.columns]
    print(full_df[streak_cols].to_string(index=False))

    print("\n=== RETURN HISTOGRAM COUNTS ===")
    hist_cols = ["weight_label"] + [
        f"return_bucket_{label}_count" for label in RETURN_BUCKET_LABELS
    ]
    hist_cols = [c for c in hist_cols if c in full_df.columns]
    print(full_df[hist_cols].to_string(index=False))

    print(f"\n[OK] Wyniki zapisane do: {OUT_DIR}")
    print("\nNajwazniejsze pliki:")
    print(f"  - {OUT_DIR / 'combined_decision_table.csv'}")
    print(f"  - {OUT_DIR / 'combined_full_summary.csv'}")
    print(f"  - {OUT_DIR / 'combined_monthly_dynamic_combined.csv'}")
    print(f"  - {OUT_DIR / 'combined_dynamic_regimes.csv'}")
    print(f"  - {OUT_DIR / 'combined_loss_streaks.csv'}")
    print(f"  - {OUT_DIR / 'combined_return_histogram_buckets.csv'}")
    print(f"  - {OUT_DIR / 'combined_b_effect_vs_a.csv'}")
    print(f"  - {OUT_DIR / 'combined_rolling_psychology.csv'}")
    print(f"  - {OUT_DIR / 'combined_named_periods_readable.csv'}")

    if replay_source_paths:
        print(f"\n[OK] Pliki do UK replay zapisane w: {REPLAY_SOURCE_OUT_DIR}")
        print("Przyklady:")
        print(f"  - {REPLAY_SOURCE_OUT_DIR / 'combined_for_replay_monthly_a080_b020.csv'}")
        print(f"  - {REPLAY_SOURCE_OUT_DIR / 'combined_for_replay_monthly_dynamic_combined.csv'}")
        print("\nDo replay_mapped_to_uk.py uzyj najlepiej:")
        print("  --execution-mode target_each_month")
    else:
        print("\n[WARN] Nie zapisano plikow replay-source, bo brakuje holdings A/B.")


if __name__ == "__main__":
    main()
