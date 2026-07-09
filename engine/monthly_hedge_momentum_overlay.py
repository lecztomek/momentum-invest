from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

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


def compound_returns(r: pd.Series) -> pd.Series:
    return (1.0 + r.fillna(0.0)).cumprod()


def period_return(r: pd.Series) -> float:
    if len(r) == 0:
        return np.nan

    return float((1.0 + r.fillna(0.0)).prod() - 1.0)


def calc_drawdown(equity: pd.Series) -> pd.Series:
    return equity / equity.cummax() - 1.0


def rolling_total_return(r: pd.Series, window: int) -> pd.Series:
    return (1.0 + r.fillna(0.0)).rolling(window).apply(np.prod, raw=True) - 1.0


def rolling_maxdd_from_returns(r: pd.Series, window: int) -> pd.Series:
    def _maxdd(x: np.ndarray) -> float:
        eq = np.cumprod(1.0 + x)
        peak = np.maximum.accumulate(eq)
        dd = eq / peak - 1.0
        return float(np.min(dd))

    return r.fillna(0.0).rolling(window).apply(_maxdd, raw=True)


def calc_cagr(
    start_equity: float,
    end_equity: float,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> float:
    days = (end_date - start_date).days

    if days <= 0 or start_equity <= 0 or end_equity <= 0:
        return np.nan

    years = days / 365.25
    return (end_equity / start_equity) ** (1.0 / years) - 1.0


def safe_calmar(cagr: float, maxdd: float) -> float:
    if pd.isna(cagr) or pd.isna(maxdd):
        return np.nan

    if maxdd >= 0:
        return np.nan

    return cagr / abs(maxdd)


def max_consecutive_true(mask: pd.Series) -> int:
    max_run = 0
    current = 0

    for value in mask.fillna(False).astype(bool):
        if value:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0

    return int(max_run)


def month_end_index(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return index.to_period("M").to_timestamp("M")


# =========================
# LOADERS
# =========================

def load_daily_equity_all(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = clean_columns(df)

    date_col = find_date_column(df)
    df = df.rename(columns={date_col: "date"})

    if "strategy" not in df.columns:
        raise ValueError("Plik musi mieć kolumnę strategy.")

    if "portfolio_daily_return" not in df.columns and "equity_daily" not in df.columns:
        raise ValueError(
            "Plik musi mieć portfolio_daily_return albo equity_daily."
        )

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["strategy", "date"])

    if "portfolio_daily_return" not in df.columns:
        df["portfolio_daily_return"] = (
            df.groupby("strategy")["equity_daily"]
            .pct_change()
            .fillna(0.0)
        )

    df["portfolio_daily_return"] = pd.to_numeric(
        df["portfolio_daily_return"],
        errors="coerce",
    )

    return df.dropna(subset=["date", "strategy", "portfolio_daily_return"])


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


def get_strategy_daily_returns(
    daily_all: pd.DataFrame,
    strategy: str,
) -> pd.Series:
    df = daily_all[daily_all["strategy"].astype(str) == strategy].copy()

    if df.empty:
        raise ValueError(
            f"Nie znaleziono strategii '{strategy}'. "
            f"Dostępne: {sorted(daily_all['strategy'].astype(str).unique())}"
        )

    df = df.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    df = df.set_index("date")

    return df["portfolio_daily_return"].astype(float).rename(strategy)


def get_ticker_daily_returns(
    daily_close: pd.DataFrame,
    ticker: str,
) -> pd.Series:
    ticker_map = {normalize_ticker(c): str(c) for c in daily_close.columns}
    key = normalize_ticker(ticker)

    if key not in ticker_map:
        raise ValueError(
            f"Nie znaleziono tickera '{ticker}' w daily_close.csv. "
            f"Pierwsze kolumny: {list(daily_close.columns)[:20]}"
        )

    col = ticker_map[key]

    price = daily_close[col].ffill()
    ret = price.pct_change()
    ret = ret.replace([np.inf, -np.inf], np.nan)

    return ret.rename(col)


# =========================
# MONTHLY SIGNALS
# =========================

def daily_to_monthly_returns(daily_return: pd.Series) -> pd.Series:
    r = daily_return.dropna().copy()
    r.index = pd.to_datetime(r.index)

    out = r.resample("M").apply(period_return)
    out.index.name = "month_end"

    return out.dropna()


def align_monthly_returns(
    a_monthly: pd.Series,
    baseline_monthly: pd.Series,
    hedge_monthly: pd.Series,
) -> pd.DataFrame:
    df = pd.concat(
        [
            a_monthly.rename("A"),
            baseline_monthly.rename("BASELINE"),
            hedge_monthly.rename("HEDGE"),
        ],
        axis=1,
    ).dropna()

    return df


def build_monthly_hedge_signal(
    monthly: pd.DataFrame,
    rule: str,
    lookback: int,
    ema_span: int,
    min_hedge_return: float,
    min_spread_vs_a: float,
) -> pd.Series:
    """
    Sygnał liczony na końcu miesiąca M.
    Sygnał jest przesunięty o 1 miesiąc, więc działa od miesiąca M+1.
    """
    a = monthly["A"]
    h = monthly["HEDGE"]

    h_lb = rolling_total_return(h, lookback)
    a_lb = rolling_total_return(a, lookback)

    if rule == "hedge_1m_positive":
        raw = h > min_hedge_return

    elif rule == "hedge_lb_positive":
        raw = h_lb > min_hedge_return

    elif rule == "hedge_beats_a":
        raw = (h_lb - a_lb) > min_spread_vs_a

    elif rule == "hedge_positive_and_beats_a":
        raw = (h_lb > min_hedge_return) & ((h_lb - a_lb) > min_spread_vs_a)

    elif rule == "hedge_positive_and_beats_a_not_6m_extended":
        h_6m = rolling_total_return(h, 6)
        a_6m = rolling_total_return(a, 6)

        raw = (
            (h_lb > min_hedge_return)
            & ((h_lb - a_lb) > min_spread_vs_a)
            & ((h_6m - a_6m) <= 0.0)
        )

    elif rule == "hedge_positive_and_beats_a_not_6m_12m_extended":
        h_6m = rolling_total_return(h, 6)
        a_6m = rolling_total_return(a, 6)
        h_12m = rolling_total_return(h, 12)
        a_12m = rolling_total_return(a, 12)

        raw = (
            (h_lb > min_hedge_return)
            & ((h_lb - a_lb) > min_spread_vs_a)
            & ((h_6m - a_6m) <= 0.0)
            & ((h_12m - a_12m) <= 0.0)
        )

    elif rule == "hedge_positive_and_a_negative":
        raw = (h_lb > min_hedge_return) & (a < 0.0)

    elif rule == "hedge_positive_and_a_lb_negative":
        raw = (h_lb > min_hedge_return) & (a_lb < 0.0)

    elif rule == "hedge_ema_positive":
        h_eq = compound_returns(h)
        h_ema = h_eq.ewm(span=ema_span, adjust=False).mean()
        raw = h_eq > h_ema

    elif rule == "hedge_ema_positive_and_beats_a":
        h_eq = compound_returns(h)
        h_ema = h_eq.ewm(span=ema_span, adjust=False).mean()
        raw = (h_eq > h_ema) & ((h_lb - a_lb) > min_spread_vs_a)

    elif rule == "hedge_positive_and_beats_a_a_3m_positive":
        a_3m = rolling_total_return(a, 3)
        raw = (
            (h_lb > min_hedge_return)
            & ((h_lb - a_lb) > min_spread_vs_a)
            & (a_3m > 0.0)
        )
		
    else:
        raise ValueError(f"Nieznana reguła: {rule}")

    raw = raw.fillna(False).astype(bool)

    signal = raw.shift(1).fillna(False).astype(bool)
    signal.name = "hedge_on"

    return signal


def iter_rule_configs(
    rules: List[str],
    lookbacks: List[int],
    ema_spans: List[int],
    min_hedge_returns: List[float],
    min_spreads_vs_a: List[float],
) -> Iterable[Tuple[str, int, int, float, float]]:
    """
    Redukuje duplikaty.
    Np. hedge_1m_positive nie zależy od lookback ani ema_span,
    więc nie produkujemy wielu identycznych wariantów.
    """
    for rule in rules:
        if rule == "hedge_1m_positive":
            for min_h in min_hedge_returns:
                yield rule, 1, 0, min_h, 0.0

        elif rule == "hedge_lb_positive":
            for lb in lookbacks:
                for min_h in min_hedge_returns:
                    yield rule, lb, 0, min_h, 0.0

        elif rule == "hedge_beats_a":
            for lb in lookbacks:
                for spread in min_spreads_vs_a:
                    yield rule, lb, 0, 0.0, spread

        elif rule in {
            "hedge_positive_and_beats_a",
            "hedge_positive_and_beats_a_not_6m_extended",
            "hedge_positive_and_beats_a_not_6m_12m_extended",
			"hedge_positive_and_beats_a_a_3m_positive",
            "hedge_positive_and_a_negative",
            "hedge_positive_and_a_lb_negative",
        }:
            for lb in lookbacks:
                for min_h in min_hedge_returns:
                    for spread in min_spreads_vs_a:
                        yield rule, lb, 0, min_h, spread

        elif rule == "hedge_ema_positive":
            for ema in ema_spans:
                yield rule, 1, ema, 0.0, 0.0

        elif rule == "hedge_ema_positive_and_beats_a":
            for lb in lookbacks:
                for ema in ema_spans:
                    for spread in min_spreads_vs_a:
                        yield rule, lb, ema, 0.0, spread

        else:
            raise ValueError(f"Nieznana reguła: {rule}")


# =========================
# DAILY OVERLAY
# =========================

def build_daily_overlay_returns_from_monthly_signal(
    a_daily: pd.Series,
    baseline_daily: pd.Series,
    hedge_daily: pd.Series,
    monthly_signal: pd.Series,
    hedge_weight: float,
) -> pd.DataFrame:
    df = pd.concat(
        [
            a_daily.rename("A"),
            baseline_daily.rename("BASELINE"),
            hedge_daily.rename("HEDGE"),
        ],
        axis=1,
    ).dropna()

    df = df.sort_index()

    df["month_end"] = month_end_index(pd.DatetimeIndex(df.index))

    signal_map = monthly_signal.copy()
    signal_map.index = pd.to_datetime(signal_map.index)

    df["hedge_on"] = df["month_end"].map(signal_map).fillna(False).astype(bool)

    wh = float(hedge_weight)
    wa = 1.0 - wh

    df["overlay_return"] = np.where(
        df["hedge_on"],
        wa * df["A"] + wh * df["HEDGE"],
        df["A"],
    )

    df["overlay_weight_a"] = np.where(df["hedge_on"], wa, 1.0)
    df["overlay_weight_hedge"] = np.where(df["hedge_on"], wh, 0.0)

    df["overlay_equity"] = compound_returns(df["overlay_return"])
    df["baseline_equity"] = compound_returns(df["BASELINE"])
    df["a_equity"] = compound_returns(df["A"])
    df["hedge_equity"] = compound_returns(df["HEDGE"])

    df["overlay_drawdown"] = calc_drawdown(df["overlay_equity"])
    df["baseline_drawdown"] = calc_drawdown(df["baseline_equity"])
    df["a_drawdown"] = calc_drawdown(df["a_equity"])

    return df


# =========================
# HEDGE ATTRIBUTION / DIAGNOSTICS
# =========================

def build_monthly_hedge_attribution(
    label: str,
    overlay_result: pd.DataFrame,
    hedge_weight: float,
) -> pd.DataFrame:
    """
    Monthly diagnostic table: when did the hedge overlay help or hurt vs pure A?

    Important:
    - hedge_delta for month M is overlay_return_M - A_return_M,
    - feature columns ending with _prev are shifted by one month, so they are
      known before month M starts,
    - this is diagnostic output, not a fitted rule.
    """
    df = overlay_result.copy().sort_index()

    monthly = pd.DataFrame({
        "a_return": df["A"].resample("M").apply(period_return),
        "baseline_return": df["BASELINE"].resample("M").apply(period_return),
        "hedge_return": df["HEDGE"].resample("M").apply(period_return),
        "overlay_return": df["overlay_return"].resample("M").apply(period_return),
        "hedge_on": df["hedge_on"].resample("M").max().astype(bool),
        "overlay_weight_a": df["overlay_weight_a"].resample("M").last(),
        "overlay_weight_hedge": df["overlay_weight_hedge"].resample("M").last(),
    })

    monthly.index.name = "month_end"
    monthly["portfolio"] = label
    monthly["hedge_weight_config"] = float(hedge_weight)

    # Realized contribution of the overlay in month M vs pure A.
    monthly["hedge_delta"] = monthly["overlay_return"] - monthly["a_return"]
    monthly["hedge_helped"] = monthly["hedge_delta"] > 0.0

    # Equity and drawdown streams at month-end.
    monthly["a_equity"] = compound_returns(monthly["a_return"])
    monthly["baseline_equity"] = compound_returns(monthly["baseline_return"])
    monthly["overlay_equity"] = compound_returns(monthly["overlay_return"])
    monthly["hedge_equity"] = compound_returns(monthly["hedge_return"])

    monthly["a_drawdown"] = calc_drawdown(monthly["a_equity"])
    monthly["baseline_drawdown"] = calc_drawdown(monthly["baseline_equity"])
    monthly["overlay_drawdown"] = calc_drawdown(monthly["overlay_equity"])
    monthly["hedge_drawdown"] = calc_drawdown(monthly["hedge_equity"])

    # Features known before month M starts.
    monthly["a_1m_prev"] = monthly["a_return"].shift(1)
    monthly["baseline_1m_prev"] = monthly["baseline_return"].shift(1)
    monthly["hedge_1m_prev"] = monthly["hedge_return"].shift(1)

    monthly["a_3m_prev"] = rolling_total_return(monthly["a_return"], 3).shift(1)
    monthly["a_6m_prev"] = rolling_total_return(monthly["a_return"], 6).shift(1)
    monthly["a_12m_prev"] = rolling_total_return(monthly["a_return"], 12).shift(1)

    monthly["hedge_3m_prev"] = rolling_total_return(monthly["hedge_return"], 3).shift(1)
    monthly["hedge_6m_prev"] = rolling_total_return(monthly["hedge_return"], 6).shift(1)
    monthly["hedge_12m_prev"] = rolling_total_return(monthly["hedge_return"], 12).shift(1)

    monthly["a_drawdown_prev"] = monthly["a_drawdown"].shift(1)
    monthly["baseline_drawdown_prev"] = monthly["baseline_drawdown"].shift(1)
    monthly["overlay_drawdown_prev"] = monthly["overlay_drawdown"].shift(1)
    monthly["hedge_drawdown_prev"] = monthly["hedge_drawdown"].shift(1)

    monthly["hedge_minus_a_1m_prev"] = monthly["hedge_1m_prev"] - monthly["a_1m_prev"]
    monthly["hedge_minus_a_3m_prev"] = monthly["hedge_3m_prev"] - monthly["a_3m_prev"]
    monthly["hedge_minus_a_6m_prev"] = monthly["hedge_6m_prev"] - monthly["a_6m_prev"]
    monthly["hedge_minus_a_12m_prev"] = monthly["hedge_12m_prev"] - monthly["a_12m_prev"]

    # Simple, interpretable candidate conditions. These are only diagnostics.
    monthly["a_1m_prev_negative"] = monthly["a_1m_prev"] < 0.0
    monthly["a_3m_prev_negative"] = monthly["a_3m_prev"] < 0.0
    monthly["a_6m_prev_negative"] = monthly["a_6m_prev"] < 0.0
    monthly["a_12m_prev_negative"] = monthly["a_12m_prev"] < 0.0

    monthly["a_drawdown_prev_lt_3pct"] = monthly["a_drawdown_prev"] < -0.03
    monthly["a_drawdown_prev_lt_5pct"] = monthly["a_drawdown_prev"] < -0.05
    monthly["a_drawdown_prev_lt_10pct"] = monthly["a_drawdown_prev"] < -0.10

    monthly["hedge_1m_prev_positive"] = monthly["hedge_1m_prev"] > 0.0
    monthly["hedge_3m_prev_positive"] = monthly["hedge_3m_prev"] > 0.0
    monthly["hedge_6m_prev_positive"] = monthly["hedge_6m_prev"] > 0.0
    monthly["hedge_12m_prev_positive"] = monthly["hedge_12m_prev"] > 0.0

    monthly["hedge_1m_prev_beats_a"] = monthly["hedge_minus_a_1m_prev"] > 0.0
    monthly["hedge_3m_prev_beats_a"] = monthly["hedge_minus_a_3m_prev"] > 0.0
    monthly["hedge_6m_prev_beats_a"] = monthly["hedge_minus_a_6m_prev"] > 0.0
    monthly["hedge_12m_prev_beats_a"] = monthly["hedge_minus_a_12m_prev"] > 0.0

    # Slightly more combined conditions, still not optimized.
    monthly["a_weak_and_hedge_positive_3m"] = (
        monthly["a_3m_prev_negative"] & monthly["hedge_3m_prev_positive"]
    )
    monthly["a_drawdown_5pct_and_hedge_positive_3m"] = (
        monthly["a_drawdown_prev_lt_5pct"] & monthly["hedge_3m_prev_positive"]
    )
    monthly["a_weak_and_hedge_beats_a_3m"] = (
        monthly["a_3m_prev_negative"] & monthly["hedge_3m_prev_beats_a"]
    )

    monthly = monthly.reset_index()
    return monthly


def add_regime_buckets(attribution: pd.DataFrame) -> pd.DataFrame:
    """
    Add categorical regime buckets and 2D regime labels.

    The thresholds are intentionally coarse and interpretable. They are meant
    for diagnosis, not for fitted optimization.
    """
    df = attribution.copy()

    def bucket_a_return(x: float) -> str:
        if pd.isna(x):
            return "missing"
        if x > 0.10:
            return "strong_up_gt_10"
        if x > 0.03:
            return "up_3_10"
        if x >= -0.03:
            return "flat_-3_3"
        if x >= -0.10:
            return "down_-10_-3"
        return "strong_down_lt_-10"

    def bucket_bond_return(x: float) -> str:
        if pd.isna(x):
            return "missing"
        if x > 0.05:
            return "strong_up_gt_5"
        if x > 0.01:
            return "up_1_5"
        if x >= -0.01:
            return "flat_-1_1"
        if x >= -0.05:
            return "down_-5_-1"
        return "strong_down_lt_-5"

    def bucket_drawdown(x: float) -> str:
        if pd.isna(x):
            return "missing"
        if x >= -0.02:
            return "near_high_gt_-2"
        if x >= -0.05:
            return "mild_dd_-5_-2"
        if x >= -0.10:
            return "medium_dd_-10_-5"
        return "deep_dd_lt_-10"

    def bucket_spread(x: float) -> str:
        if pd.isna(x):
            return "missing"
        if x < -0.10:
            return "a_leads_big_lt_-10"
        if x < -0.03:
            return "a_leads_-10_-3"
        if x <= 0.03:
            return "similar_-3_3"
        if x <= 0.10:
            return "hedge_leads_3_10"
        return "hedge_leads_big_gt_10"

    for src, out in [
        ("a_3m_prev", "a_3m_bucket"),
        ("a_6m_prev", "a_6m_bucket"),
        ("a_12m_prev", "a_12m_bucket"),
    ]:
        if src in df.columns:
            df[out] = df[src].apply(bucket_a_return)

    for src, out in [
        ("hedge_3m_prev", "hedge_3m_bucket"),
        ("hedge_6m_prev", "hedge_6m_bucket"),
        ("hedge_12m_prev", "hedge_12m_bucket"),
    ]:
        if src in df.columns:
            df[out] = df[src].apply(bucket_bond_return)

    if "a_drawdown_prev" in df.columns:
        df["a_drawdown_bucket"] = df["a_drawdown_prev"].apply(bucket_drawdown)

    for src, out in [
        ("hedge_minus_a_3m_prev", "spread_3m_bucket"),
        ("hedge_minus_a_6m_prev", "spread_6m_bucket"),
        ("hedge_minus_a_12m_prev", "spread_12m_bucket"),
    ]:
        if src in df.columns:
            df[out] = df[src].apply(bucket_spread)

    def combine(a: str, b: str, out: str) -> None:
        if a in df.columns and b in df.columns:
            df[out] = df[a].astype(str) + "__" + df[b].astype(str)

    combine("a_3m_bucket", "hedge_3m_bucket", "a3m_x_hedge3m")
    combine("a_3m_bucket", "spread_6m_bucket", "a3m_x_spread6m")
    combine("a_drawdown_bucket", "hedge_3m_bucket", "dd_x_hedge3m")
    combine("a_drawdown_bucket", "spread_6m_bucket", "dd_x_spread6m")
    combine("hedge_3m_bucket", "spread_6m_bucket", "hedge3m_x_spread6m")
    combine("a_6m_bucket", "spread_12m_bucket", "a6m_x_spread12m")
    combine("a_drawdown_bucket", "spread_12m_bucket", "dd_x_spread12m")

    return df


def build_hedge_attribution_buckets(attribution: pd.DataFrame) -> pd.DataFrame:
    """
    Summarize hedge_delta by simple conditions, categorical regimes and 2D regimes.

    Output is per portfolio/rule/weight. `is_reliable_bucket` is a guardrail for
    interpretation, not a filter: True means at least 12 months in the bucket and
    at least 5 hedge-active months inside that bucket.
    """
    attribution = add_regime_buckets(attribution)

    bucket_cols = [
        "hedge_on",

        "a_1m_prev_negative",
        "a_3m_prev_negative",
        "a_6m_prev_negative",
        "a_12m_prev_negative",

        "a_drawdown_prev_lt_3pct",
        "a_drawdown_prev_lt_5pct",
        "a_drawdown_prev_lt_10pct",

        "hedge_1m_prev_positive",
        "hedge_3m_prev_positive",
        "hedge_6m_prev_positive",
        "hedge_12m_prev_positive",

        "hedge_1m_prev_beats_a",
        "hedge_3m_prev_beats_a",
        "hedge_6m_prev_beats_a",
        "hedge_12m_prev_beats_a",

        "a_weak_and_hedge_positive_3m",
        "a_drawdown_5pct_and_hedge_positive_3m",
        "a_weak_and_hedge_beats_a_3m",

        "a_3m_bucket",
        "a_6m_bucket",
        "a_12m_bucket",
        "hedge_3m_bucket",
        "hedge_6m_bucket",
        "hedge_12m_bucket",
        "a_drawdown_bucket",
        "spread_3m_bucket",
        "spread_6m_bucket",
        "spread_12m_bucket",

        "a3m_x_hedge3m",
        "a3m_x_spread6m",
        "dd_x_hedge3m",
        "dd_x_spread6m",
        "hedge3m_x_spread6m",
        "a6m_x_spread12m",
        "dd_x_spread12m",
    ]

    rows: List[Dict[str, Any]] = []

    for portfolio, pg in attribution.groupby("portfolio", dropna=False):
        meta = pg.iloc[0].to_dict()

        for bucket in bucket_cols:
            if bucket not in pg.columns:
                continue

            for value, g in pg.groupby(bucket, dropna=False):
                hedge_active = g[g["hedge_on"].astype(bool)]
                months = int(len(g))
                hedge_active_months = int(g["hedge_on"].sum())

                row = {
                    "portfolio": portfolio,
                    "hedge": meta.get("hedge", np.nan),
                    "hedge_weight": meta.get("hedge_weight", np.nan),
                    "rule": meta.get("rule", np.nan),
                    "lookback": meta.get("lookback", np.nan),
                    "ema_span": meta.get("ema_span", np.nan),
                    "min_hedge_return": meta.get("min_hedge_return", np.nan),
                    "min_spread_vs_a": meta.get("min_spread_vs_a", np.nan),

                    "bucket": bucket,
                    "value": value,
                    "months": months,
                    "hedge_active_months": hedge_active_months,
                    "hedge_active_pct_months": float(g["hedge_on"].mean()),
                    "is_reliable_bucket": bool(months >= 12 and hedge_active_months >= 5),

                    "avg_hedge_delta_all_months": float(g["hedge_delta"].mean()),
                    "median_hedge_delta_all_months": float(g["hedge_delta"].median()),
                    "sum_hedge_delta_all_months": float(g["hedge_delta"].sum()),
                    "hit_rate_hedge_helped_all_months": float((g["hedge_delta"] > 0.0).mean()),

                    "avg_hedge_delta_active_months": (
                        float(hedge_active["hedge_delta"].mean())
                        if not hedge_active.empty else np.nan
                    ),
                    "median_hedge_delta_active_months": (
                        float(hedge_active["hedge_delta"].median())
                        if not hedge_active.empty else np.nan
                    ),
                    "sum_hedge_delta_active_months": (
                        float(hedge_active["hedge_delta"].sum())
                        if not hedge_active.empty else np.nan
                    ),
                    "hit_rate_hedge_helped_active_months": (
                        float((hedge_active["hedge_delta"] > 0.0).mean())
                        if not hedge_active.empty else np.nan
                    ),

                    "avg_a_return": float(g["a_return"].mean()),
                    "avg_overlay_return": float(g["overlay_return"].mean()),
                    "worst_a_return": float(g["a_return"].min()),
                    "worst_overlay_return": float(g["overlay_return"].min()),
                    "best_a_return": float(g["a_return"].max()),
                    "best_overlay_return": float(g["overlay_return"].max()),

                    # Useful for sorting regimes where hedge is likely valuable.
                    "tail_improvement_worst_month": (
                        float(g["overlay_return"].min() - g["a_return"].min())
                    ),
                }
                rows.append(row)

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values(
        ["portfolio", "is_reliable_bucket", "avg_hedge_delta_active_months", "bucket", "value"],
        ascending=[True, False, False, True, True],
    )


def build_hedge_attribution_regime_matrix(attribution: pd.DataFrame) -> pd.DataFrame:
    """
    Long-form 2D regime matrix for selected bucket pairs.

    This is easier to pivot in Excel/LibreOffice:
    rows = row_bucket_value, columns = col_bucket_value,
    values = avg_hedge_delta_active_months / hit_rate / tail improvement.
    """
    attribution = add_regime_buckets(attribution)

    matrix_pairs = [
        ("a_3m_bucket", "hedge_3m_bucket"),
        ("a_3m_bucket", "spread_6m_bucket"),
        ("a_drawdown_bucket", "hedge_3m_bucket"),
        ("a_drawdown_bucket", "spread_6m_bucket"),
        ("hedge_3m_bucket", "spread_6m_bucket"),
        ("a_6m_bucket", "spread_12m_bucket"),
        ("a_drawdown_bucket", "spread_12m_bucket"),
    ]

    rows: List[Dict[str, Any]] = []

    for portfolio, pg in attribution.groupby("portfolio", dropna=False):
        meta = pg.iloc[0].to_dict()

        for row_bucket, col_bucket in matrix_pairs:
            if row_bucket not in pg.columns or col_bucket not in pg.columns:
                continue

            for (row_value, col_value), g in pg.groupby([row_bucket, col_bucket], dropna=False):
                hedge_active = g[g["hedge_on"].astype(bool)]
                months = int(len(g))
                hedge_active_months = int(g["hedge_on"].sum())

                rows.append({
                    "portfolio": portfolio,
                    "hedge": meta.get("hedge", np.nan),
                    "hedge_weight": meta.get("hedge_weight", np.nan),
                    "rule": meta.get("rule", np.nan),
                    "lookback": meta.get("lookback", np.nan),
                    "ema_span": meta.get("ema_span", np.nan),
                    "min_hedge_return": meta.get("min_hedge_return", np.nan),
                    "min_spread_vs_a": meta.get("min_spread_vs_a", np.nan),
                    "matrix": f"{row_bucket}__x__{col_bucket}",
                    "row_bucket": row_bucket,
                    "row_value": row_value,
                    "col_bucket": col_bucket,
                    "col_value": col_value,
                    "months": months,
                    "hedge_active_months": hedge_active_months,
                    "is_reliable_cell": bool(months >= 12 and hedge_active_months >= 5),
                    "avg_hedge_delta_all_months": float(g["hedge_delta"].mean()),
                    "hit_rate_hedge_helped_all_months": float((g["hedge_delta"] > 0.0).mean()),
                    "avg_hedge_delta_active_months": (
                        float(hedge_active["hedge_delta"].mean())
                        if not hedge_active.empty else np.nan
                    ),
                    "hit_rate_hedge_helped_active_months": (
                        float((hedge_active["hedge_delta"] > 0.0).mean())
                        if not hedge_active.empty else np.nan
                    ),
                    "worst_a_return": float(g["a_return"].min()),
                    "worst_overlay_return": float(g["overlay_return"].min()),
                    "tail_improvement_worst_month": float(g["overlay_return"].min() - g["a_return"].min()),
                })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values(
        ["portfolio", "matrix", "is_reliable_cell", "avg_hedge_delta_active_months"],
        ascending=[True, True, False, False],
    )

def build_top_hedge_attribution_months(
    attribution: pd.DataFrame,
    top_n: int = 20,
) -> pd.DataFrame:
    """Top helpful and harmful months per portfolio by hedge_delta."""
    attribution = add_regime_buckets(attribution)
    rows: List[pd.DataFrame] = []

    for portfolio, g in attribution.groupby("portfolio", dropna=False):
        cols = [
            "month_end",
            "portfolio",
            "hedge",
            "hedge_weight",
            "rule",
            "lookback",
            "ema_span",
            "min_hedge_return",
            "min_spread_vs_a",
            "a_return",
            "hedge_return",
            "overlay_return",
            "hedge_delta",
            "hedge_on",
            "a_3m_prev",
            "a_drawdown_prev",
            "hedge_3m_prev",
            "hedge_minus_a_3m_prev",
            "a_3m_bucket",
            "a_6m_bucket",
            "a_12m_bucket",
            "hedge_3m_bucket",
            "hedge_6m_bucket",
            "hedge_12m_bucket",
            "a_drawdown_bucket",
            "spread_3m_bucket",
            "spread_6m_bucket",
            "spread_12m_bucket",
            "a3m_x_hedge3m",
            "a3m_x_spread6m",
            "dd_x_hedge3m",
            "dd_x_spread6m",
            "hedge3m_x_spread6m",
        ]
        existing = [c for c in cols if c in g.columns]

        best = g.sort_values("hedge_delta", ascending=False).head(top_n).copy()
        best["side"] = "best_helped"
        rows.append(best[["side"] + existing])

        worst = g.sort_values("hedge_delta", ascending=True).head(top_n).copy()
        worst["side"] = "worst_hurt"
        rows.append(worst[["side"] + existing])

    if not rows:
        return pd.DataFrame()

    return pd.concat(rows, ignore_index=True)


# =========================
# UNDERWATER DAILY
# =========================

def underwater_episodes(equity: pd.Series) -> pd.DataFrame:
    equity = equity.dropna().copy()

    if equity.empty:
        return pd.DataFrame()

    dd = calc_drawdown(equity)
    underwater = dd < 0

    episodes: List[Dict[str, Any]] = []

    in_episode = False
    start_date = None
    trough_date = None
    trough_dd = 0.0
    days = 0

    for date, is_underwater in underwater.items():
        current_dd = float(dd.loc[date])

        if is_underwater and not in_episode:
            in_episode = True
            start_date = date
            trough_date = date
            trough_dd = current_dd
            days = 1

        elif is_underwater and in_episode:
            days += 1

            if current_dd < trough_dd:
                trough_dd = current_dd
                trough_date = date

        elif not is_underwater and in_episode:
            episodes.append({
                "start_date": start_date,
                "trough_date": trough_date,
                "recovery_date": date,
                "is_recovered": True,
                "underwater_days": days,
                "maxdd_in_episode": trough_dd,
            })

            in_episode = False
            start_date = None
            trough_date = None
            trough_dd = 0.0
            days = 0

    if in_episode:
        episodes.append({
            "start_date": start_date,
            "trough_date": trough_date,
            "recovery_date": pd.NaT,
            "is_recovered": False,
            "underwater_days": days,
            "maxdd_in_episode": trough_dd,
        })

    return pd.DataFrame(episodes)


def summarize_underwater_daily(equity: pd.Series) -> Dict[str, Any]:
    equity = equity.dropna().copy()

    if equity.empty:
        return {
            "underwater_days": np.nan,
            "underwater_pct_days": np.nan,
            "max_underwater_days": np.nan,
            "avg_underwater_episode_days": np.nan,
            "drawdown_episode_count": np.nan,
            "unrecovered_episode_count": np.nan,
            "ulcer_index": np.nan,
            "avg_drawdown": np.nan,
            "median_drawdown": np.nan,
            "time_to_recover_maxdd_days": np.nan,
        }

    dd = calc_drawdown(equity)
    underwater = dd < 0
    episodes = underwater_episodes(equity)

    ulcer_index = float(np.sqrt(np.mean(np.square(dd.clip(upper=0.0)))))
    avg_drawdown = float(dd[dd < 0].mean()) if (dd < 0).any() else 0.0
    median_drawdown = float(dd[dd < 0].median()) if (dd < 0).any() else 0.0

    if episodes.empty:
        return {
            "underwater_days": int(underwater.sum()),
            "underwater_pct_days": float(underwater.mean()),
            "max_underwater_days": 0,
            "avg_underwater_episode_days": 0.0,
            "drawdown_episode_count": 0,
            "unrecovered_episode_count": 0,
            "ulcer_index": ulcer_index,
            "avg_drawdown": avg_drawdown,
            "median_drawdown": median_drawdown,
            "time_to_recover_maxdd_days": 0,
        }

    maxdd_date = dd.idxmin()

    episode_with_maxdd = episodes[
        (episodes["start_date"] <= maxdd_date)
        & (
            episodes["recovery_date"].isna()
            | (episodes["recovery_date"] >= maxdd_date)
        )
    ]

    time_to_recover_maxdd_days = np.nan

    if not episode_with_maxdd.empty:
        ep = episode_with_maxdd.iloc[0]

        if pd.notna(ep["recovery_date"]):
            time_to_recover_maxdd_days = int(
                (pd.Timestamp(ep["recovery_date"]) - pd.Timestamp(maxdd_date)).days
            )

    return {
        "underwater_days": int(underwater.sum()),
        "underwater_pct_days": float(underwater.mean()),
        "max_underwater_days": int(episodes["underwater_days"].max()),
        "avg_underwater_episode_days": float(episodes["underwater_days"].mean()),
        "drawdown_episode_count": int(len(episodes)),
        "unrecovered_episode_count": int((~episodes["is_recovered"]).sum()),
        "ulcer_index": ulcer_index,
        "avg_drawdown": avg_drawdown,
        "median_drawdown": median_drawdown,
        "time_to_recover_maxdd_days": time_to_recover_maxdd_days,
    }


# =========================
# SUMMARY DAILY
# =========================

def summarize_daily_stream(
    label: str,
    daily_return: pd.Series,
    hedge_on: pd.Series | None = None,
) -> Dict[str, Any]:
    r = daily_return.dropna().copy()

    if r.empty:
        raise ValueError(f"Brak danych dla {label}")

    equity = compound_returns(r)
    dd = calc_drawdown(equity)

    start_date = pd.Timestamp(r.index[0])
    end_date = pd.Timestamp(r.index[-1])

    final_equity = float(equity.iloc[-1])
    cagr = calc_cagr(1.0, final_equity, start_date, end_date)
    maxdd = float(dd.min())

    monthly = daily_to_monthly_returns(r)
    negative_months = monthly < 0

    worst_3m = monthly.rolling(3).apply(lambda x: np.prod(1.0 + x) - 1.0, raw=False).min()
    worst_6m = monthly.rolling(6).apply(lambda x: np.prod(1.0 + x) - 1.0, raw=False).min()
    worst_12m = monthly.rolling(12).apply(lambda x: np.prod(1.0 + x) - 1.0, raw=False).min()

    out: Dict[str, Any] = {
        "portfolio": label,
        "start_date": start_date,
        "end_date": end_date,
        "days": len(r),
        "months": len(monthly),

        "final_equity_daily": final_equity,
        "total_return_daily": final_equity - 1.0,
        "cagr": cagr,
        "maxdd_daily": maxdd,
        "maxdd_daily_date": dd.idxmin(),
        "calmar": safe_calmar(cagr, maxdd),

        "vol_daily": float(r.std()),
        "vol_annualized": float(r.std() * np.sqrt(252)),

        "positive_days_pct": float((r > 0).mean()),
        "negative_days_pct": float((r < 0).mean()),
        "worst_day": float(r.min()),
        "best_day": float(r.max()),

        "positive_months_pct": float((monthly > 0).mean()),
        "negative_months": int(negative_months.sum()),
        "negative_months_pct": float(negative_months.mean()),
        "avg_monthly_return": float(monthly.mean()),
        "avg_positive_month": float(monthly[monthly > 0].mean()) if (monthly > 0).any() else np.nan,
        "avg_negative_month": float(monthly[monthly < 0].mean()) if (monthly < 0).any() else np.nan,
        "worst_month": float(monthly.min()),
        "best_month": float(monthly.max()),
        "max_consecutive_negative_months": max_consecutive_true(negative_months),

        "worst_3m_return": float(worst_3m) if not pd.isna(worst_3m) else np.nan,
        "worst_6m_return": float(worst_6m) if not pd.isna(worst_6m) else np.nan,
        "worst_12m_return": float(worst_12m) if not pd.isna(worst_12m) else np.nan,
    }

    out.update(summarize_underwater_daily(equity))

    if hedge_on is not None:
        h = hedge_on.reindex(r.index).fillna(False).astype(bool)

        out["hedge_on_days"] = int(h.sum())
        out["hedge_on_pct_days"] = float(h.mean())

        hedge_on_months = (
            pd.Series(h.values, index=r.index)
            .groupby(month_end_index(pd.DatetimeIndex(r.index)))
            .max()
        )

        out["hedge_on_months"] = int(hedge_on_months.sum())
        out["hedge_on_pct_months"] = float(hedge_on_months.mean())

        if h.any():
            out["avg_daily_return_when_hedge_on"] = float(r[h].mean())
            out["negative_days_pct_when_hedge_on"] = float((r[h] < 0).mean())
        else:
            out["avg_daily_return_when_hedge_on"] = np.nan
            out["negative_days_pct_when_hedge_on"] = np.nan

        if (~h).any():
            out["avg_daily_return_when_hedge_off"] = float(r[~h].mean())
            out["negative_days_pct_when_hedge_off"] = float((r[~h] < 0).mean())
        else:
            out["avg_daily_return_when_hedge_off"] = np.nan
            out["negative_days_pct_when_hedge_off"] = np.nan

    else:
        out["hedge_on_days"] = 0
        out["hedge_on_pct_days"] = 0.0
        out["hedge_on_months"] = 0
        out["hedge_on_pct_months"] = 0.0
        out["avg_daily_return_when_hedge_on"] = np.nan
        out["negative_days_pct_when_hedge_on"] = np.nan
        out["avg_daily_return_when_hedge_off"] = float(r.mean())
        out["negative_days_pct_when_hedge_off"] = float((r < 0).mean())

    return out


def build_relative_to_baseline(
    summary: pd.DataFrame,
    baseline_label: str,
) -> pd.DataFrame:
    if baseline_label not in set(summary["portfolio"]):
        raise ValueError(
            f"Brak baseline '{baseline_label}' w summary. "
            f"Dostępne: {list(summary['portfolio'])}"
        )

    base = summary[summary["portfolio"] == baseline_label].iloc[0].to_dict()

    rows: List[Dict[str, Any]] = []

    for _, row_raw in summary.iterrows():
        row = row_raw.to_dict()

        out = {
            "portfolio": row["portfolio"],
            "baseline": baseline_label,

            "delta_final_equity_daily": row["final_equity_daily"] - base["final_equity_daily"],
            "delta_cagr": row["cagr"] - base["cagr"],

            # Dodatnie = lepiej, bo -0.13 - (-0.26) = +0.13.
            "delta_maxdd_daily": row["maxdd_daily"] - base["maxdd_daily"],
            "delta_calmar": row["calmar"] - base["calmar"],

            # Ujemne = lepiej.
            "delta_negative_months": row["negative_months"] - base["negative_months"],
            "delta_negative_months_pct": row["negative_months_pct"] - base["negative_months_pct"],
            "delta_underwater_days": row["underwater_days"] - base["underwater_days"],
            "delta_underwater_pct_days": row["underwater_pct_days"] - base["underwater_pct_days"],
            "delta_max_underwater_days": row["max_underwater_days"] - base["max_underwater_days"],
            "delta_avg_underwater_episode_days": (
                row["avg_underwater_episode_days"]
                - base["avg_underwater_episode_days"]
            ),

            # Ujemne = lepiej.
            "delta_ulcer_index": row["ulcer_index"] - base["ulcer_index"],

            # Dodatnie = lepiej.
            "delta_worst_month": row["worst_month"] - base["worst_month"],
            "delta_worst_3m_return": row["worst_3m_return"] - base["worst_3m_return"],
            "delta_worst_6m_return": row["worst_6m_return"] - base["worst_6m_return"],
            "delta_worst_12m_return": row["worst_12m_return"] - base["worst_12m_return"],

            "delta_max_consecutive_negative_months": (
                row["max_consecutive_negative_months"]
                - base["max_consecutive_negative_months"]
            ),
        }

        rows.append(out)

    return pd.DataFrame(rows)


def add_quality_score(relative: pd.DataFrame) -> pd.DataFrame:
    df = relative.copy()

    def rank_high(col: str) -> pd.Series:
        return df[col].rank(pct=True, ascending=True)

    def rank_low(col: str) -> pd.Series:
        return df[col].rank(pct=True, ascending=False)

    df["quality_score_vs_baseline"] = (
        0.18 * rank_high("delta_calmar")
        + 0.14 * rank_high("delta_maxdd_daily")
        + 0.12 * rank_low("delta_ulcer_index")
        + 0.10 * rank_low("delta_underwater_pct_days")
        + 0.10 * rank_low("delta_max_underwater_days")
        + 0.10 * rank_low("delta_negative_months_pct")
        + 0.10 * rank_high("delta_worst_6m_return")
        + 0.08 * rank_high("delta_worst_12m_return")
        + 0.08 * rank_high("delta_cagr")
    )

    return df.sort_values("quality_score_vs_baseline", ascending=False)


# =========================
# ROLLINGS
# =========================

def build_daily_rolling_table(
    portfolio_returns: Dict[str, pd.Series],
    windows: List[int],
) -> pd.DataFrame:
    rows: List[pd.DataFrame] = []

    for label, r in portfolio_returns.items():
        r = r.dropna().sort_index()

        for window in windows:
            tmp = pd.DataFrame({
                "date": r.index,
                "portfolio": label,
                "window_days": window,
                "rolling_return": rolling_total_return(r, window).values,
                "rolling_maxdd": rolling_maxdd_from_returns(r, window).values,
                "rolling_vol_annualized": (r.rolling(window).std() * np.sqrt(252)).values,
            })

            rows.append(tmp)

    if not rows:
        return pd.DataFrame()

    return pd.concat(rows, ignore_index=True)


def build_monthly_rolling_table(
    portfolio_returns: Dict[str, pd.Series],
    windows: List[int],
) -> pd.DataFrame:
    rows: List[pd.DataFrame] = []

    for label, r_daily in portfolio_returns.items():
        r_monthly = daily_to_monthly_returns(r_daily.dropna())

        for window in windows:
            rolling_ret = rolling_total_return(r_monthly, window)

            tmp = pd.DataFrame({
                "date": r_monthly.index,
                "portfolio": label,
                "window_months": window,
                "rolling_return": rolling_ret.values,
            })

            rows.append(tmp)

    if not rows:
        return pd.DataFrame()

    return pd.concat(rows, ignore_index=True)


def build_rolling_summary(
    daily_rolling: pd.DataFrame,
    monthly_rolling: pd.DataFrame,
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []

    if not daily_rolling.empty:
        for (portfolio, window), g in daily_rolling.groupby(["portfolio", "window_days"]):
            rows.append({
                "portfolio": portfolio,
                "type": "daily",
                "window": int(window),
                "worst_rolling_return": float(g["rolling_return"].min()),
                "best_rolling_return": float(g["rolling_return"].max()),
                "avg_rolling_return": float(g["rolling_return"].mean()),
                "worst_rolling_maxdd": float(g["rolling_maxdd"].min()),
                "avg_rolling_maxdd": float(g["rolling_maxdd"].mean()),
                "avg_rolling_vol_annualized": float(g["rolling_vol_annualized"].mean()),
            })

    if not monthly_rolling.empty:
        for (portfolio, window), g in monthly_rolling.groupby(["portfolio", "window_months"]):
            rows.append({
                "portfolio": portfolio,
                "type": "monthly",
                "window": int(window),
                "worst_rolling_return": float(g["rolling_return"].min()),
                "best_rolling_return": float(g["rolling_return"].max()),
                "avg_rolling_return": float(g["rolling_return"].mean()),
                "worst_rolling_maxdd": np.nan,
                "avg_rolling_maxdd": np.nan,
                "avg_rolling_vol_annualized": np.nan,
            })

    return pd.DataFrame(rows)


# =========================
# MAIN
# =========================

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Miesięczny aktywny hedge overlay z dziennym liczeniem equity, "
            "daily MaxDD, underwater oraz rolling returns."
        )
    )

    parser.add_argument(
        "--daily-equity-all",
        required=True,
        help="daily_equity_all.csv z compare_monthly_replays_daily.py.",
    )

    parser.add_argument(
        "--daily-close",
        required=True,
        help="daily_close.csv z cenami hedge tickerów.",
    )

    parser.add_argument(
        "--a-strategy",
        default="A",
        help="Nazwa strategii A w daily_equity_all.csv.",
    )

    parser.add_argument(
        "--baseline-strategy",
        default="COMBINED",
        help="Baseline, czyli obecne A80/B20. Domyślnie COMBINED.",
    )

    parser.add_argument(
        "--hedges",
        nargs="+",
        required=True,
        help="Tickery hedge, np. tlt.us uup.us iau.us rwm.us sh.us.",
    )

    parser.add_argument(
        "--hedge-weights",
        nargs="+",
        type=float,
        default=[0.10, 0.15, 0.20],
        help="Wagi hedge w miesiącach hedge_on.",
    )

    parser.add_argument(
        "--rules",
        nargs="+",
        default=[
            "hedge_1m_positive",
            "hedge_lb_positive",
            "hedge_positive_and_beats_a",
            "hedge_positive_and_beats_a_not_6m_extended",
            "hedge_positive_and_beats_a_not_6m_12m_extended",
            "hedge_positive_and_a_negative",
            "hedge_positive_and_a_lb_negative",
            "hedge_ema_positive",
            "hedge_ema_positive_and_beats_a",
			"hedge_positive_and_beats_a_a_3m_positive"
        ],
        choices=[
            "hedge_1m_positive",
            "hedge_lb_positive",
            "hedge_beats_a",
            "hedge_positive_and_beats_a",
            "hedge_positive_and_beats_a_not_6m_extended",
            "hedge_positive_and_beats_a_not_6m_12m_extended",
            "hedge_positive_and_a_negative",
            "hedge_positive_and_a_lb_negative",
            "hedge_ema_positive",
            "hedge_ema_positive_and_beats_a",
			"hedge_positive_and_beats_a_a_3m_positive"
        ],
    )

    parser.add_argument(
        "--lookbacks",
        nargs="+",
        type=int,
        default=[1, 3, 6],
    )

    parser.add_argument(
        "--ema-spans",
        nargs="+",
        type=int,
        default=[3, 6, 10],
    )

    parser.add_argument(
        "--min-hedge-returns",
        nargs="+",
        type=float,
        default=[0.0],
    )

    parser.add_argument(
        "--min-spreads-vs-a",
        nargs="+",
        type=float,
        default=[0.0],
    )

    parser.add_argument(
        "--rolling-day-windows",
        nargs="+",
        type=int,
        default=[21, 63, 126, 252],
    )

    parser.add_argument(
        "--rolling-month-windows",
        nargs="+",
        type=int,
        default=[3, 6, 12],
    )

    parser.add_argument(
        "--save-daily-detail-top-n",
        type=int,
        default=30,
        help=(
            "Ile najlepszych overlayów zapisać do pliku daily detail. "
            "0 = nie zapisuj szczegółów dziennych overlayów."
        ),
    )

    parser.add_argument(
        "--output-dir",
        default="output_monthly_hedge_momentum_daily",
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    daily_all = load_daily_equity_all(Path(args.daily_equity_all))
    daily_close = load_daily_close(Path(args.daily_close))

    a_daily = get_strategy_daily_returns(daily_all, args.a_strategy)
    baseline_daily = get_strategy_daily_returns(daily_all, args.baseline_strategy)

    a_monthly = daily_to_monthly_returns(a_daily)
    baseline_monthly = daily_to_monthly_returns(baseline_daily)

    summary_rows: List[Dict[str, Any]] = []
    overlay_store: Dict[str, pd.DataFrame] = {}
    portfolio_returns: Dict[str, pd.Series] = {}

    # Baseline
    common_base = pd.concat(
        [
            a_daily.rename("A"),
            baseline_daily.rename("BASELINE"),
        ],
        axis=1,
    ).dropna()

    baseline_r = common_base["BASELINE"]
    a_r = common_base["A"]

    baseline_summary = summarize_daily_stream(
        label=args.baseline_strategy,
        daily_return=baseline_r,
        hedge_on=None,
    )
    summary_rows.append(baseline_summary)
    portfolio_returns[args.baseline_strategy] = baseline_r

    a100_summary = summarize_daily_stream(
        label="A100",
        daily_return=a_r,
        hedge_on=None,
    )
    summary_rows.append(a100_summary)
    portfolio_returns["A100"] = a_r

    signal_rows: List[pd.DataFrame] = []
    attribution_rows: List[pd.DataFrame] = []

    for hedge in args.hedges:
        hedge_daily = get_ticker_daily_returns(daily_close, hedge)
        hedge_monthly = daily_to_monthly_returns(hedge_daily)

        monthly = align_monthly_returns(
            a_monthly=a_monthly,
            baseline_monthly=baseline_monthly,
            hedge_monthly=hedge_monthly,
        )

        for rule, lookback, ema_span, min_h, spread in iter_rule_configs(
            rules=args.rules,
            lookbacks=args.lookbacks,
            ema_spans=args.ema_spans,
            min_hedge_returns=args.min_hedge_returns,
            min_spreads_vs_a=args.min_spreads_vs_a,
        ):
            signal = build_monthly_hedge_signal(
                monthly=monthly,
                rule=rule,
                lookback=lookback,
                ema_span=ema_span,
                min_hedge_return=min_h,
                min_spread_vs_a=spread,
            )

            for hedge_weight in args.hedge_weights:
                result = build_daily_overlay_returns_from_monthly_signal(
                    a_daily=a_daily,
                    baseline_daily=baseline_daily,
                    hedge_daily=hedge_daily,
                    monthly_signal=signal,
                    hedge_weight=hedge_weight,
                )

                label = (
                    f"ACTIVE_{hedge}"
                    f"_w{int(round(hedge_weight * 100)):03d}"
                    f"_{rule}"
                    f"_lb{lookback}"
                    f"_ema{ema_span}"
                    f"_minh{int(round(min_h * 10000)):05d}"
                    f"_spread{int(round(spread * 10000)):05d}"
                )

                summary = summarize_daily_stream(
                    label=label,
                    daily_return=result["overlay_return"],
                    hedge_on=result["hedge_on"],
                )

                summary.update({
                    "hedge": hedge,
                    "hedge_weight": hedge_weight,
                    "rule": rule,
                    "lookback": lookback,
                    "ema_span": ema_span,
                    "min_hedge_return": min_h,
                    "min_spread_vs_a": spread,
                })

                summary_rows.append(summary)

                overlay_store[label] = result
                portfolio_returns[label] = result["overlay_return"]

                attribution = build_monthly_hedge_attribution(
                    label=label,
                    overlay_result=result,
                    hedge_weight=hedge_weight,
                )
                attribution["hedge"] = hedge
                attribution["hedge_weight"] = hedge_weight
                attribution["rule"] = rule
                attribution["lookback"] = lookback
                attribution["ema_span"] = ema_span
                attribution["min_hedge_return"] = min_h
                attribution["min_spread_vs_a"] = spread
                attribution_rows.append(attribution)

                sig = pd.DataFrame({
                    "month_end": monthly.index,
                    "portfolio": label,
                    "hedge": hedge,
                    "rule": rule,
                    "lookback": lookback,
                    "ema_span": ema_span,
                    "min_hedge_return": min_h,
                    "min_spread_vs_a": spread,
                    "hedge_weight": hedge_weight,
                    "hedge_on_next_month": signal.reindex(monthly.index).fillna(False).astype(bool).values,
                    "a_monthly_return": monthly["A"].values,
                    "hedge_monthly_return": monthly["HEDGE"].values,
                    "baseline_monthly_return": monthly["BASELINE"].values,
                })

                signal_rows.append(sig)

    summary_df = pd.DataFrame(summary_rows)

    relative = build_relative_to_baseline(
        summary=summary_df,
        baseline_label=args.baseline_strategy,
    )
    relative = add_quality_score(relative)

    full = summary_df.merge(
        relative,
        on="portfolio",
        how="left",
        suffixes=("", "_rel"),
    )

    full = full.sort_values("quality_score_vs_baseline", ascending=False)

    # Rolling liczymy dla baseline, A100 i top N overlayów, żeby pliki nie eksplodowały.
    top_n = int(args.save_daily_detail_top_n)
    top_labels = list(full["portfolio"].head(max(top_n, 0)))

    rolling_portfolio_returns = {
        label: portfolio_returns[label]
        for label in top_labels
        if label in portfolio_returns
    }

    daily_rolling = build_daily_rolling_table(
        portfolio_returns=rolling_portfolio_returns,
        windows=args.rolling_day_windows,
    )

    monthly_rolling = build_monthly_rolling_table(
        portfolio_returns=rolling_portfolio_returns,
        windows=args.rolling_month_windows,
    )

    rolling_summary = build_rolling_summary(
        daily_rolling=daily_rolling,
        monthly_rolling=monthly_rolling,
    )

    summary_file = output_dir / "monthly_active_hedge_daily_summary.csv"
    relative_file = output_dir / "monthly_active_hedge_daily_relative_vs_baseline.csv"
    full_file = output_dir / "monthly_active_hedge_daily_full_ranked.csv"
    signals_file = output_dir / "monthly_active_hedge_signals.csv"
    rolling_daily_file = output_dir / "rolling_daily_top.csv"
    rolling_monthly_file = output_dir / "rolling_monthly_top.csv"
    rolling_summary_file = output_dir / "rolling_summary_top.csv"
    daily_detail_file = output_dir / "daily_detail_top.csv"
    attribution_file = output_dir / "hedge_monthly_attribution.csv"
    attribution_buckets_file = output_dir / "hedge_attribution_buckets.csv"
    attribution_top_months_file = output_dir / "hedge_attribution_top_months.csv"
    attribution_reliable_buckets_file = output_dir / "hedge_attribution_buckets_reliable.csv"
    attribution_regime_matrix_file = output_dir / "hedge_attribution_regime_matrix.csv"

    summary_df.to_csv(summary_file, index=False, float_format="%.10f")
    relative.to_csv(relative_file, index=False, float_format="%.10f")
    full.to_csv(full_file, index=False, float_format="%.10f")

    if signal_rows:
        signals = pd.concat(signal_rows, ignore_index=True)
        signals.to_csv(signals_file, index=False, float_format="%.10f")

    if attribution_rows:
        attribution_all = pd.concat(attribution_rows, ignore_index=True)
        attribution_all.to_csv(attribution_file, index=False, float_format="%.10f")

        attribution_buckets = build_hedge_attribution_buckets(attribution_all)
        attribution_buckets.to_csv(
            attribution_buckets_file,
            index=False,
            float_format="%.10f",
        )

        attribution_buckets_reliable = attribution_buckets[
            attribution_buckets["is_reliable_bucket"].astype(bool)
        ].copy()
        attribution_buckets_reliable.to_csv(
            attribution_reliable_buckets_file,
            index=False,
            float_format="%.10f",
        )

        attribution_regime_matrix = build_hedge_attribution_regime_matrix(attribution_all)
        attribution_regime_matrix.to_csv(
            attribution_regime_matrix_file,
            index=False,
            float_format="%.10f",
        )

        attribution_top_months = build_top_hedge_attribution_months(
            attribution_all,
            top_n=20,
        )
        attribution_top_months.to_csv(
            attribution_top_months_file,
            index=False,
            float_format="%.10f",
        )

    daily_rolling.to_csv(rolling_daily_file, index=False, float_format="%.10f")
    monthly_rolling.to_csv(rolling_monthly_file, index=False, float_format="%.10f")
    rolling_summary.to_csv(rolling_summary_file, index=False, float_format="%.10f")

    if top_n > 0:
        detail_rows: List[pd.DataFrame] = []

        for label in top_labels:
            if label not in overlay_store:
                continue

            d = overlay_store[label].copy().reset_index().rename(columns={"index": "date"})
            d.insert(0, "portfolio", label)
            detail_rows.append(d)

        if detail_rows:
            detail = pd.concat(detail_rows, ignore_index=True)
            detail.to_csv(daily_detail_file, index=False, float_format="%.10f")

    print(f"[OK] zapisano: {summary_file}")
    print(f"[OK] zapisano: {relative_file}")
    print(f"[OK] zapisano: {full_file}")
    print(f"[OK] zapisano: {signals_file}")

    if attribution_rows:
        print(f"[OK] zapisano: {attribution_file}")
        print(f"[OK] zapisano: {attribution_buckets_file}")
        print(f"[OK] zapisano: {attribution_top_months_file}")
        print(f"[OK] zapisano: {attribution_reliable_buckets_file}")
        print(f"[OK] zapisano: {attribution_regime_matrix_file}")

    print(f"[OK] zapisano: {rolling_daily_file}")
    print(f"[OK] zapisano: {rolling_monthly_file}")
    print(f"[OK] zapisano: {rolling_summary_file}")

    if top_n > 0:
        print(f"[OK] zapisano: {daily_detail_file}")

    show_cols = [
        "portfolio",
        "hedge",
        "hedge_weight",
        "rule",
        "lookback",
        "ema_span",
        "hedge_on_months",
        "hedge_on_pct_months",
        "final_equity_daily",
        "cagr",
        "maxdd_daily",
        "maxdd_daily_date",
        "calmar",
        "negative_months",
        "negative_months_pct",
        "ulcer_index",
        "underwater_pct_days",
        "max_underwater_days",
        "worst_month",
        "worst_6m_return",
        "worst_12m_return",
        "delta_cagr",
        "delta_maxdd_daily",
        "delta_calmar",
        "delta_negative_months",
        "delta_ulcer_index",
        "quality_score_vs_baseline",
    ]

    existing = [c for c in show_cols if c in full.columns]

    print("\n=== TOP MONTHLY SIGNAL / DAILY EQUITY OVERLAYS VS BASELINE ===")
    print(full[existing].head(50).to_string(index=False))


if __name__ == "__main__":
    main()