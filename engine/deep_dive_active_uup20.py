from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List, Tuple

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


def period_return(r: pd.Series) -> float:
    if len(r) == 0:
        return np.nan

    return float((1.0 + r.fillna(0.0)).prod() - 1.0)


def compound_returns(r: pd.Series) -> pd.Series:
    return (1.0 + r.fillna(0.0)).cumprod()


def calc_drawdown(equity: pd.Series) -> pd.Series:
    return equity / equity.cummax() - 1.0


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
    if pd.isna(cagr) or pd.isna(maxdd) or maxdd >= 0:
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


def rolling_total_return(r: pd.Series, window: int) -> pd.Series:
    return (1.0 + r.fillna(0.0)).rolling(window).apply(np.prod, raw=True) - 1.0


def rolling_maxdd_from_returns(r: pd.Series, window: int) -> pd.Series:
    def _maxdd(x: np.ndarray) -> float:
        eq = np.cumprod(1.0 + x)
        peak = np.maximum.accumulate(eq)
        dd = eq / peak - 1.0
        return float(np.min(dd))

    return r.fillna(0.0).rolling(window).apply(_maxdd, raw=True)


def drawdown_stats(equity: pd.Series) -> Dict[str, Any]:
    """
    Basic drawdown statistics for any equity curve.

    Works for daily or month-end equity. The caller decides the frequency.
    maxdd_start_date is the date of the equity peak immediately before the trough.
    maxdd_recovery_date is the first date after the trough when equity gets back
    to the previous peak, or NaT if unrecovered in the sample.
    """
    eq = equity.dropna().copy()

    if eq.empty:
        return {
            "maxdd": np.nan,
            "maxdd_start_date": pd.NaT,
            "maxdd_trough_date": pd.NaT,
            "maxdd_recovery_date": pd.NaT,
            "maxdd_duration_periods": np.nan,
        }

    running_peak = eq.cummax()
    dd = eq / running_peak - 1.0
    trough_date = dd.idxmin()
    maxdd = float(dd.loc[trough_date])

    peak_value = running_peak.loc[trough_date]
    peak_candidates = eq.loc[:trough_date]
    peak_candidates = peak_candidates[peak_candidates >= peak_value - 1e-12]
    start_date = peak_candidates.index[-1] if not peak_candidates.empty else eq.index[0]

    after_trough = eq.loc[trough_date:]
    recovered = after_trough[after_trough >= peak_value - 1e-12]
    recovery_date = recovered.index[0] if not recovered.empty else pd.NaT

    if pd.notna(recovery_date):
        loc_start = int(eq.index.get_loc(start_date))
        loc_recovery = int(eq.index.get_loc(recovery_date))
        duration = loc_recovery - loc_start
    else:
        duration = np.nan

    return {
        "maxdd": maxdd,
        "maxdd_start_date": start_date,
        "maxdd_trough_date": trough_date,
        "maxdd_recovery_date": recovery_date,
        "maxdd_duration_periods": duration,
    }


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
        raise ValueError("Plik daily_equity_all musi mieć kolumnę strategy.")

    if "portfolio_daily_return" not in df.columns and "equity_daily" not in df.columns:
        raise ValueError(
            "Plik daily_equity_all musi mieć portfolio_daily_return albo equity_daily."
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
    ret = price.pct_change().replace([np.inf, -np.inf], np.nan)

    return ret.rename(col)


# =========================
# MONTHLY SIGNAL + DAILY EXECUTION
# =========================

def daily_to_monthly_returns(daily_return: pd.Series) -> pd.Series:
    r = daily_return.dropna().copy()
    r.index = pd.to_datetime(r.index)

    out = r.resample("M").apply(period_return)
    out.index.name = "month_end"

    return out.dropna()


def build_uup_signal(
    uup_monthly: pd.Series,
    threshold: float,
) -> pd.Series:
    """
    Sygnał liczony na końcu miesiąca M.
    Jeśli UUP monthly return > threshold, hedge działa w miesiącu M+1.
    """
    raw = (uup_monthly > threshold).fillna(False).astype(bool)
    signal = raw.shift(1).fillna(False).astype(bool)
    signal.name = "uup_hedge_on_next_month"
    return signal


def build_active_uup_overlay_daily(
    a_daily: pd.Series,
    baseline_daily: pd.Series,
    uup_daily: pd.Series,
    threshold: float,
    uup_weight: float,
    cost_bps: float,
) -> pd.DataFrame:
    """
    Jednopoziomowy UUP overlay:

    Na koniec miesiąca M:
        jeśli UUP monthly return > threshold:
            w miesiącu M+1 UUP weight = uup_weight
        else:
            w miesiącu M+1 UUP weight = 0

    Bez look-ahead: sygnał jest shift(1).
    """
    uup_monthly = daily_to_monthly_returns(uup_daily)

    signal = build_uup_signal(
        uup_monthly=uup_monthly,
        threshold=threshold,
    )

    df = pd.concat(
        [
            a_daily.rename("A"),
            baseline_daily.rename("BASELINE"),
            uup_daily.rename("UUP"),
        ],
        axis=1,
    ).dropna()

    df = df.sort_index()
    df["month_end"] = month_end_index(pd.DatetimeIndex(df.index))
    df["hedge_on"] = df["month_end"].map(signal).fillna(False).astype(bool)

    wh = float(uup_weight)
    wa = 1.0 - wh

    df["weight_a"] = np.where(df["hedge_on"], wa, 1.0)
    df["weight_uup"] = np.where(df["hedge_on"], wh, 0.0)
    df["hedge_level"] = np.where(df["hedge_on"], 1, 0)

    turnover = df["weight_uup"].diff().abs().fillna(df["weight_uup"].abs())
    cost = turnover * (float(cost_bps) / 10000.0)

    df["gross_overlay_return"] = (
        df["weight_a"] * df["A"]
        + df["weight_uup"] * df["UUP"]
    )

    df["turnover_uup_weight"] = turnover
    df["cost_return_drag"] = cost
    df["overlay_return"] = df["gross_overlay_return"] - df["cost_return_drag"]

    df["overlay_equity"] = compound_returns(df["overlay_return"])
    df["baseline_equity"] = compound_returns(df["BASELINE"])
    df["a_equity"] = compound_returns(df["A"])
    df["uup_equity"] = compound_returns(df["UUP"])

    df["overlay_drawdown"] = calc_drawdown(df["overlay_equity"])
    df["baseline_drawdown"] = calc_drawdown(df["baseline_equity"])
    df["a_drawdown"] = calc_drawdown(df["a_equity"])

    df["threshold"] = threshold
    df["threshold_2"] = np.nan
    df["uup_weight"] = uup_weight
    df["uup_weight_2"] = np.nan
    df["cost_bps"] = cost_bps
    df["two_level"] = False

    return df


def build_active_uup_overlay_daily_two_level(
    a_daily: pd.Series,
    baseline_daily: pd.Series,
    uup_daily: pd.Series,
    threshold_1: float,
    threshold_2: float,
    uup_weight_1: float,
    uup_weight_2: float,
    cost_bps: float,
) -> pd.DataFrame:
    """
    Dwupoziomowy UUP overlay:

    Na koniec miesiąca M:
        jeśli UUP monthly return > threshold_2:
            w miesiącu M+1 UUP weight = uup_weight_2
        elif UUP monthly return > threshold_1:
            w miesiącu M+1 UUP weight = uup_weight_1
        else:
            w miesiącu M+1 UUP weight = 0

    Przykład:
        threshold_1 = 0.0025, uup_weight_1 = 0.20
        threshold_2 = 0.0100, uup_weight_2 = 0.50

    Bez look-ahead: target weight jest shift(1).
    """
    if threshold_2 <= threshold_1:
        raise ValueError("threshold_2 musi być większy niż threshold_1.")

    if uup_weight_2 <= uup_weight_1:
        raise ValueError("uup_weight_2 powinno być większe niż uup_weight_1.")

    uup_monthly = daily_to_monthly_returns(uup_daily)

    raw_weight = pd.Series(0.0, index=uup_monthly.index)
    raw_weight[uup_monthly > threshold_1] = float(uup_weight_1)
    raw_weight[uup_monthly > threshold_2] = float(uup_weight_2)

    monthly_target_weight = raw_weight.shift(1).fillna(0.0)
    monthly_target_weight.name = "target_uup_weight"

    df = pd.concat(
        [
            a_daily.rename("A"),
            baseline_daily.rename("BASELINE"),
            uup_daily.rename("UUP"),
        ],
        axis=1,
    ).dropna()

    df = df.sort_index()
    df["month_end"] = month_end_index(pd.DatetimeIndex(df.index))

    df["weight_uup"] = (
        df["month_end"]
        .map(monthly_target_weight)
        .fillna(0.0)
        .astype(float)
    )

    df["weight_a"] = 1.0 - df["weight_uup"]
    df["hedge_on"] = df["weight_uup"] > 0.0

    df["hedge_level"] = np.select(
        [
            df["weight_uup"] >= float(uup_weight_2) - 1e-12,
            df["weight_uup"] >= float(uup_weight_1) - 1e-12,
        ],
        [
            2,
            1,
        ],
        default=0,
    )

    turnover = df["weight_uup"].diff().abs().fillna(df["weight_uup"].abs())
    cost = turnover * (float(cost_bps) / 10000.0)

    df["gross_overlay_return"] = (
        df["weight_a"] * df["A"]
        + df["weight_uup"] * df["UUP"]
    )

    df["turnover_uup_weight"] = turnover
    df["cost_return_drag"] = cost
    df["overlay_return"] = df["gross_overlay_return"] - df["cost_return_drag"]

    df["overlay_equity"] = compound_returns(df["overlay_return"])
    df["baseline_equity"] = compound_returns(df["BASELINE"])
    df["a_equity"] = compound_returns(df["A"])
    df["uup_equity"] = compound_returns(df["UUP"])

    df["overlay_drawdown"] = calc_drawdown(df["overlay_equity"])
    df["baseline_drawdown"] = calc_drawdown(df["baseline_equity"])
    df["a_drawdown"] = calc_drawdown(df["a_equity"])

    df["threshold"] = threshold_1
    df["threshold_2"] = threshold_2
    df["uup_weight"] = uup_weight_1
    df["uup_weight_2"] = uup_weight_2
    df["cost_bps"] = cost_bps
    df["two_level"] = True

    return df


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
        return {}

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
# MONTHLY HISTOGRAMS / STREAKS
# =========================

def monthly_return_histogram(monthly: pd.Series) -> Dict[str, Any]:
    m = monthly.dropna().copy()

    if m.empty:
        return {
            "months_lt_minus_10": 0,
            "months_lt_minus_5": 0,
            "months_lt_minus_3": 0,
            "months_minus_3_to_0": 0,
            "months_0_to_3": 0,
            "months_gt_3": 0,
            "months_gt_5": 0,
            "months_gt_10": 0,
            "pct_lt_minus_5": np.nan,
            "pct_lt_minus_3": np.nan,
            "pct_gt_3": np.nan,
            "pct_gt_5": np.nan,
        }

    return {
        "months_lt_minus_10": int((m < -0.10).sum()),
        "months_lt_minus_5": int((m < -0.05).sum()),
        "months_lt_minus_3": int((m < -0.03).sum()),
        "months_minus_3_to_0": int(((m >= -0.03) & (m < 0.0)).sum()),
        "months_0_to_3": int(((m >= 0.0) & (m <= 0.03)).sum()),
        "months_gt_3": int((m > 0.03).sum()),
        "months_gt_5": int((m > 0.05).sum()),
        "months_gt_10": int((m > 0.10).sum()),
        "pct_lt_minus_5": float((m < -0.05).mean()),
        "pct_lt_minus_3": float((m < -0.03).mean()),
        "pct_gt_3": float((m > 0.03).mean()),
        "pct_gt_5": float((m > 0.05).mean()),
    }


def negative_month_streaks(monthly: pd.Series) -> pd.DataFrame:
    m = monthly.dropna().copy()

    rows: List[Dict[str, Any]] = []

    in_streak = False
    start_date = None
    values: List[float] = []
    prev_date = None

    for date, value in m.items():
        is_negative = value < 0.0

        if is_negative and not in_streak:
            in_streak = True
            start_date = date
            values = [float(value)]

        elif is_negative and in_streak:
            values.append(float(value))

        elif not is_negative and in_streak:
            end_date = prev_date
            cumulative_return = float(np.prod([1.0 + x for x in values]) - 1.0)

            rows.append({
                "start_date": start_date,
                "end_date": end_date,
                "months": len(values),
                "cumulative_return": cumulative_return,
                "avg_monthly_return": float(np.mean(values)),
                "worst_month_in_streak": float(np.min(values)),
            })

            in_streak = False
            start_date = None
            values = []

        prev_date = date

    if in_streak:
        end_date = m.index[-1]
        cumulative_return = float(np.prod([1.0 + x for x in values]) - 1.0)

        rows.append({
            "start_date": start_date,
            "end_date": end_date,
            "months": len(values),
            "cumulative_return": cumulative_return,
            "avg_monthly_return": float(np.mean(values)),
            "worst_month_in_streak": float(np.min(values)),
        })

    return pd.DataFrame(rows)


def summarize_negative_month_streaks(monthly: pd.Series) -> Dict[str, Any]:
    streaks = negative_month_streaks(monthly)

    if streaks.empty:
        return {
            "negative_streak_count": 0,
            "max_negative_streak_months": 0,
            "avg_negative_streak_months": 0.0,
            "worst_negative_streak_return": 0.0,
            "worst_negative_streak_start": pd.NaT,
            "worst_negative_streak_end": pd.NaT,
        }

    worst_idx = streaks["cumulative_return"].idxmin()

    return {
        "negative_streak_count": int(len(streaks)),
        "max_negative_streak_months": int(streaks["months"].max()),
        "avg_negative_streak_months": float(streaks["months"].mean()),
        "worst_negative_streak_return": float(streaks["cumulative_return"].min()),
        "worst_negative_streak_start": streaks.loc[worst_idx, "start_date"],
        "worst_negative_streak_end": streaks.loc[worst_idx, "end_date"],
    }


# =========================
# SUMMARIES
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
    monthly_equity = compound_returns(monthly)
    monthly_dd = calc_drawdown(monthly_equity)
    monthly_dd_stats = drawdown_stats(monthly_equity)
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

        "maxdd_monthly": float(monthly_dd.min()) if not monthly_dd.empty else np.nan,
        "maxdd_monthly_date": monthly_dd.idxmin() if not monthly_dd.empty else pd.NaT,
        "maxdd_monthly_start_date": monthly_dd_stats["maxdd_start_date"],
        "maxdd_monthly_trough_date": monthly_dd_stats["maxdd_trough_date"],
        "maxdd_monthly_recovery_date": monthly_dd_stats["maxdd_recovery_date"],
        "maxdd_monthly_duration_months": monthly_dd_stats["maxdd_duration_periods"],
        "calmar_monthly": safe_calmar(cagr, float(monthly_dd.min()) if not monthly_dd.empty else np.nan),

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
    out.update(monthly_return_histogram(monthly))
    out.update(summarize_negative_month_streaks(monthly))

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
        raise ValueError(f"Brak baseline '{baseline_label}' w summary.")

    base = summary[summary["portfolio"] == baseline_label].iloc[0].to_dict()

    rows: List[Dict[str, Any]] = []

    for _, row_raw in summary.iterrows():
        row = row_raw.to_dict()

        out = {
            "portfolio": row["portfolio"],
            "baseline": baseline_label,

            "delta_final_equity_daily": row["final_equity_daily"] - base["final_equity_daily"],
            "delta_cagr": row["cagr"] - base["cagr"],
            "delta_maxdd_daily": row["maxdd_daily"] - base["maxdd_daily"],
            "delta_calmar": row["calmar"] - base["calmar"],
            "delta_maxdd_monthly": row["maxdd_monthly"] - base["maxdd_monthly"],
            "delta_calmar_monthly": row["calmar_monthly"] - base["calmar_monthly"],

            "delta_negative_months": row["negative_months"] - base["negative_months"],
            "delta_negative_months_pct": row["negative_months_pct"] - base["negative_months_pct"],

            "delta_underwater_days": row["underwater_days"] - base["underwater_days"],
            "delta_underwater_pct_days": row["underwater_pct_days"] - base["underwater_pct_days"],
            "delta_max_underwater_days": row["max_underwater_days"] - base["max_underwater_days"],
            "delta_ulcer_index": row["ulcer_index"] - base["ulcer_index"],

            "delta_worst_month": row["worst_month"] - base["worst_month"],
            "delta_worst_3m_return": row["worst_3m_return"] - base["worst_3m_return"],
            "delta_worst_6m_return": row["worst_6m_return"] - base["worst_6m_return"],
            "delta_worst_12m_return": row["worst_12m_return"] - base["worst_12m_return"],

            "delta_months_lt_minus_10": row["months_lt_minus_10"] - base["months_lt_minus_10"],
            "delta_months_lt_minus_5": row["months_lt_minus_5"] - base["months_lt_minus_5"],
            "delta_months_lt_minus_3": row["months_lt_minus_3"] - base["months_lt_minus_3"],
            "delta_months_gt_3": row["months_gt_3"] - base["months_gt_3"],
            "delta_months_gt_5": row["months_gt_5"] - base["months_gt_5"],

            "delta_max_negative_streak_months": (
                row["max_negative_streak_months"] - base["max_negative_streak_months"]
            ),
            "delta_worst_negative_streak_return": (
                row["worst_negative_streak_return"] - base["worst_negative_streak_return"]
            ),
        }

        rows.append(out)

    return pd.DataFrame(rows)


# =========================
# SUBPERIODS / STREAK TABLE
# =========================

def build_subperiod_summary(
    portfolio_returns: Dict[str, pd.Series],
    subperiods: List[Tuple[str, str, str]],
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []

    for period_name, start_raw, end_raw in subperiods:
        start = pd.Timestamp(start_raw)
        end = pd.Timestamp(end_raw)

        for label, r in portfolio_returns.items():
            x = r.loc[(r.index >= start) & (r.index <= end)].dropna()

            if len(x) < 20:
                continue

            s = summarize_daily_stream(
                label=label,
                daily_return=x,
                hedge_on=None,
            )

            s["subperiod"] = period_name
            rows.append(s)

    return pd.DataFrame(rows)


def build_negative_streaks_table(
    portfolio_returns: Dict[str, pd.Series],
    subperiods: List[Tuple[str, str, str]],
) -> pd.DataFrame:
    rows: List[pd.DataFrame] = []

    for portfolio, daily_return in portfolio_returns.items():
        monthly = daily_to_monthly_returns(daily_return.dropna())

        full_streaks = negative_month_streaks(monthly)

        if not full_streaks.empty:
            full_streaks.insert(0, "portfolio", portfolio)
            full_streaks.insert(1, "period", "FULL")
            rows.append(full_streaks)

        for period_name, start_raw, end_raw in subperiods:
            start = pd.Timestamp(start_raw)
            end = pd.Timestamp(end_raw)

            m = monthly.loc[(monthly.index >= start) & (monthly.index <= end)]

            if len(m) < 2:
                continue

            streaks = negative_month_streaks(m)

            if streaks.empty:
                continue

            streaks.insert(0, "portfolio", portfolio)
            streaks.insert(1, "period", period_name)
            rows.append(streaks)

    if not rows:
        return pd.DataFrame()

    out = pd.concat(rows, ignore_index=True)

    return out.sort_values(
        ["period", "portfolio", "cumulative_return"],
        ascending=[True, True, True],
    )


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

    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def build_monthly_rolling_table(
    portfolio_returns: Dict[str, pd.Series],
    windows: List[int],
) -> pd.DataFrame:
    rows: List[pd.DataFrame] = []

    for label, r_daily in portfolio_returns.items():
        r_monthly = daily_to_monthly_returns(r_daily.dropna())

        for window in windows:
            tmp = pd.DataFrame({
                "date": r_monthly.index,
                "portfolio": label,
                "window_months": window,
                "rolling_return": rolling_total_return(r_monthly, window).values,
                "rolling_maxdd": rolling_maxdd_from_returns(r_monthly, window).values,
            })

            rows.append(tmp)

    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


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
                "worst_rolling_maxdd": float(g["rolling_maxdd"].min()),
                "avg_rolling_maxdd": float(g["rolling_maxdd"].mean()),
                "avg_rolling_vol_annualized": np.nan,
            })

    return pd.DataFrame(rows)


def build_rolling_winrate_vs_baseline(
    daily_rolling: pd.DataFrame,
    monthly_rolling: pd.DataFrame,
    baseline_label: str,
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []

    if not daily_rolling.empty:
        for window, g in daily_rolling.groupby("window_days"):
            pivot_ret = g.pivot_table(
                index="date",
                columns="portfolio",
                values="rolling_return",
                aggfunc="last",
            )

            pivot_dd = g.pivot_table(
                index="date",
                columns="portfolio",
                values="rolling_maxdd",
                aggfunc="last",
            )

            if baseline_label not in pivot_ret.columns:
                continue

            for portfolio in pivot_ret.columns:
                if portfolio == baseline_label:
                    continue

                pair_ret = pivot_ret[[baseline_label, portfolio]].dropna()
                pair_dd = pivot_dd[[baseline_label, portfolio]].dropna()

                rows.append({
                    "portfolio": portfolio,
                    "baseline": baseline_label,
                    "type": "daily",
                    "window": int(window),
                    "rolling_return_win_pct": float(
                        (pair_ret[portfolio] > pair_ret[baseline_label]).mean()
                    ) if len(pair_ret) else np.nan,
                    "rolling_maxdd_win_pct": float(
                        (pair_dd[portfolio] > pair_dd[baseline_label]).mean()
                    ) if len(pair_dd) else np.nan,
                    "avg_rolling_return_diff": float(
                        (pair_ret[portfolio] - pair_ret[baseline_label]).mean()
                    ) if len(pair_ret) else np.nan,
                    "avg_rolling_maxdd_diff": float(
                        (pair_dd[portfolio] - pair_dd[baseline_label]).mean()
                    ) if len(pair_dd) else np.nan,
                    "obs": len(pair_ret),
                })

    if not monthly_rolling.empty:
        for window, g in monthly_rolling.groupby("window_months"):
            pivot_ret = g.pivot_table(
                index="date",
                columns="portfolio",
                values="rolling_return",
                aggfunc="last",
            )

            pivot_dd = g.pivot_table(
                index="date",
                columns="portfolio",
                values="rolling_maxdd",
                aggfunc="last",
            )

            if baseline_label not in pivot_ret.columns:
                continue

            for portfolio in pivot_ret.columns:
                if portfolio == baseline_label:
                    continue

                pair_ret = pivot_ret[[baseline_label, portfolio]].dropna()
                pair_dd = pivot_dd[[baseline_label, portfolio]].dropna()

                rows.append({
                    "portfolio": portfolio,
                    "baseline": baseline_label,
                    "type": "monthly",
                    "window": int(window),
                    "rolling_return_win_pct": float(
                        (pair_ret[portfolio] > pair_ret[baseline_label]).mean()
                    ) if len(pair_ret) else np.nan,
                    "rolling_maxdd_win_pct": float(
                        (pair_dd[portfolio] > pair_dd[baseline_label]).mean()
                    ) if len(pair_dd) else np.nan,
                    "avg_rolling_return_diff": float(
                        (pair_ret[portfolio] - pair_ret[baseline_label]).mean()
                    ) if len(pair_ret) else np.nan,
                    "avg_rolling_maxdd_diff": float(
                        (pair_dd[portfolio] - pair_dd[baseline_label]).mean()
                    ) if len(pair_dd) else np.nan,
                    "obs": len(pair_ret),
                })

    return pd.DataFrame(rows)


# =========================
# ANNUAL RETURNS
# =========================

def build_annual_returns_table(
    portfolio_returns: Dict[str, pd.Series],
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []

    for portfolio, daily_return in portfolio_returns.items():
        r = daily_return.dropna().sort_index()

        if r.empty:
            continue

        monthly = daily_to_monthly_returns(r)

        for year, r_year in r.groupby(r.index.year):
            if r_year.empty:
                continue

            equity_daily = compound_returns(r_year)
            dd_daily = calc_drawdown(equity_daily)

            m_year = monthly[monthly.index.year == year]
            equity_monthly = compound_returns(m_year)
            dd_monthly = calc_drawdown(equity_monthly) if not equity_monthly.empty else pd.Series(dtype=float)

            rows.append({
                "year": int(year),
                "portfolio": portfolio,
                "start_date": pd.Timestamp(r_year.index[0]),
                "end_date": pd.Timestamp(r_year.index[-1]),
                "days": int(len(r_year)),
                "months": int(len(m_year)),
                "annual_return": period_return(r_year),
                "maxdd_daily_in_year": float(dd_daily.min()) if not dd_daily.empty else np.nan,
                "maxdd_daily_date_in_year": dd_daily.idxmin() if not dd_daily.empty else pd.NaT,
                "maxdd_monthly_in_year": float(dd_monthly.min()) if not dd_monthly.empty else np.nan,
                "maxdd_monthly_date_in_year": dd_monthly.idxmin() if not dd_monthly.empty else pd.NaT,
                "positive_months": int((m_year > 0).sum()) if not m_year.empty else 0,
                "negative_months": int((m_year < 0).sum()) if not m_year.empty else 0,
                "worst_month": float(m_year.min()) if not m_year.empty else np.nan,
                "best_month": float(m_year.max()) if not m_year.empty else np.nan,
                "worst_day": float(r_year.min()),
                "best_day": float(r_year.max()),
            })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values(["portfolio", "year"])


# =========================
# ATTRIBUTION
# =========================

def build_hedge_on_attribution(
    overlay_df: pd.DataFrame,
) -> pd.DataFrame:
    df = overlay_df.copy()

    monthly = pd.DataFrame({
        "A": daily_to_monthly_returns(df["A"]),
        "BASELINE": daily_to_monthly_returns(df["BASELINE"]),
        "UUP": daily_to_monthly_returns(df["UUP"]),
        "OVERLAY": daily_to_monthly_returns(df["overlay_return"]),
    }).dropna()

    hedge_on_monthly = (
        df["hedge_on"]
        .groupby(month_end_index(pd.DatetimeIndex(df.index)))
        .max()
        .reindex(monthly.index)
        .fillna(False)
        .astype(bool)
    )

    monthly["hedge_on"] = hedge_on_monthly

    if "hedge_level" in df.columns:
        level_monthly = (
            df["hedge_level"]
            .groupby(month_end_index(pd.DatetimeIndex(df.index)))
            .max()
            .reindex(monthly.index)
            .fillna(0)
            .astype(int)
        )
        monthly["hedge_level"] = level_monthly
    else:
        monthly["hedge_level"] = np.where(monthly["hedge_on"], 1, 0)

    rows: List[Dict[str, Any]] = []

    buckets = [
        ("hedge_on", monthly["hedge_on"]),
        ("hedge_off", ~monthly["hedge_on"]),
        ("level_1", monthly["hedge_level"] == 1),
        ("level_2", monthly["hedge_level"] == 2),
        ("all", pd.Series(True, index=monthly.index)),
    ]

    for state_name, mask in buckets:
        x = monthly.loc[mask].copy()

        if x.empty:
            continue

        rows.append({
            "bucket": state_name,
            "months": len(x),
            "overlay_avg_month": float(x["OVERLAY"].mean()),
            "a_avg_month": float(x["A"].mean()),
            "baseline_avg_month": float(x["BASELINE"].mean()),
            "uup_avg_month": float(x["UUP"].mean()),

            "overlay_minus_a_avg": float((x["OVERLAY"] - x["A"]).mean()),
            "overlay_minus_baseline_avg": float((x["OVERLAY"] - x["BASELINE"]).mean()),

            "overlay_win_vs_a_pct": float((x["OVERLAY"] > x["A"]).mean()),
            "overlay_win_vs_baseline_pct": float((x["OVERLAY"] > x["BASELINE"]).mean()),

            "overlay_negative_months_pct": float((x["OVERLAY"] < 0).mean()),
            "a_negative_months_pct": float((x["A"] < 0).mean()),
            "baseline_negative_months_pct": float((x["BASELINE"] < 0).mean()),

            "overlay_worst_month": float(x["OVERLAY"].min()),
            "a_worst_month": float(x["A"].min()),
            "baseline_worst_month": float(x["BASELINE"].min()),
        })

    return pd.DataFrame(rows)


# =========================
# CORRELATIONS
# =========================

def build_correlation_report(
    daily_close: pd.DataFrame,
    a_daily: pd.Series,
    baseline_daily: pd.Series,
    uup_daily: pd.Series,
    group_assets: List[str],
) -> pd.DataFrame:
    series = {
        "A": a_daily,
        "COMBINED": baseline_daily,
        "UUP": uup_daily,
    }

    ticker_map = {normalize_ticker(c): str(c) for c in daily_close.columns}

    for ticker in group_assets:
        key = normalize_ticker(ticker)

        if key == "_cash":
            continue

        if key not in ticker_map:
            print(f"[WARN] Brak group asset w daily_close: {ticker}")
            continue

        col = ticker_map[key]
        series[col] = get_ticker_daily_returns(daily_close, col)

    monthly_series = {
        name: daily_to_monthly_returns(s)
        for name, s in series.items()
    }

    df = pd.concat(monthly_series, axis=1).dropna(how="all")
    corr = df.corr()

    rows: List[Dict[str, Any]] = []

    for col in corr.columns:
        rows.append({
            "asset": col,
            "corr_to_uup": float(corr.loc[col, "UUP"]) if "UUP" in corr.columns else np.nan,
            "corr_to_a": float(corr.loc[col, "A"]) if "A" in corr.columns else np.nan,
            "corr_to_combined": float(corr.loc[col, "COMBINED"]) if "COMBINED" in corr.columns else np.nan,
        })

    return pd.DataFrame(rows)


# =========================
# MAIN
# =========================

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Deep dive dla Active UUP overlay vs COMBINED: "
            "daily MaxDD, rolling windows, named periods, monthly histograms, "
            "negative month streaks, attribution, correlation, costs, one-level and two-level UUP."
        )
    )

    parser.add_argument("--daily-equity-all", required=True)
    parser.add_argument("--daily-close", required=True)

    parser.add_argument("--a-strategy", default="A")
    parser.add_argument("--baseline-strategy", default="COMBINED")
    parser.add_argument("--uup-ticker", default="uup.us")

    parser.add_argument(
        "--thresholds",
        nargs="+",
        type=float,
        default=[0.0, 0.0025, 0.005, 0.01],
        help="Progi monthly return UUP dla jednopoziomowego overlayu.",
    )

    parser.add_argument(
        "--weights",
        nargs="+",
        type=float,
        default=[0.05, 0.10, 0.15, 0.20, 0.25, 0.30],
        help="Wagi UUP w miesiącach hedge_on dla jednopoziomowego overlayu.",
    )

    parser.add_argument(
        "--cost-bps",
        nargs="+",
        type=float,
        default=[0.0, 5.0, 10.0, 20.0],
        help="Koszt w bps od zmiany wagi UUP.",
    )

    parser.add_argument(
        "--two-level",
        action="store_true",
        help="Włącza test dwupoziomowy UUP: np. 20% po progu 1 i 50% po progu 2.",
    )

    parser.add_argument(
        "--thresholds-level1",
        nargs="+",
        type=float,
        default=[0.0, 0.0025, 0.005],
        help="Progi dla poziomu 1, np. 0 0.0025 0.005.",
    )

    parser.add_argument(
        "--thresholds-level2",
        nargs="+",
        type=float,
        default=[0.0075, 0.01, 0.015, 0.02],
        help="Progi dla poziomu 2, np. 0.0075 0.01 0.015 0.02.",
    )

    parser.add_argument(
        "--weight-level1",
        type=float,
        default=0.20,
        help="Waga UUP dla poziomu 1. Domyślnie 20%.",
    )

    parser.add_argument(
        "--weight-level2",
        type=float,
        default=0.50,
        help="Waga UUP dla poziomu 2. Domyślnie 50%.",
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
        default=[3, 6, 12, 24, 36, 48, 60, 84, 120, 180],
    )

    parser.add_argument(
        "--group-assets",
        nargs="+",
        default=["xlk.us", "ivv.us", "dbc.us", "iau.us"],
        help="Aktywa z group_set A do korelacji z UUP.",
    )

    parser.add_argument(
        "--output-dir",
        default="output_deep_dive_active_uup20",
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    daily_all = load_daily_equity_all(Path(args.daily_equity_all))
    daily_close = load_daily_close(Path(args.daily_close))

    a_daily = get_strategy_daily_returns(daily_all, args.a_strategy)
    baseline_daily = get_strategy_daily_returns(daily_all, args.baseline_strategy)
    uup_daily = get_ticker_daily_returns(daily_close, args.uup_ticker)

    common = pd.concat(
        [
            a_daily.rename("A"),
            baseline_daily.rename("BASELINE"),
            uup_daily.rename("UUP"),
        ],
        axis=1,
    ).dropna()

    a_daily = common["A"]
    baseline_daily = common["BASELINE"]
    uup_daily = common["UUP"]

    portfolio_returns: Dict[str, pd.Series] = {}
    overlay_details: Dict[str, pd.DataFrame] = {}

    portfolio_returns[args.baseline_strategy] = baseline_daily
    portfolio_returns["A100"] = a_daily

    summary_rows: List[Dict[str, Any]] = []

    baseline_summary = summarize_daily_stream(
        label=args.baseline_strategy,
        daily_return=baseline_daily,
        hedge_on=None,
    )
    baseline_summary.update({
        "threshold": np.nan,
        "threshold_2": np.nan,
        "uup_weight": np.nan,
        "uup_weight_2": np.nan,
        "cost_bps": np.nan,
        "two_level": False,
        "level1_months": 0,
        "level2_months": 0,
    })
    summary_rows.append(baseline_summary)

    a100_summary = summarize_daily_stream(
        label="A100",
        daily_return=a_daily,
        hedge_on=None,
    )
    a100_summary.update({
        "threshold": np.nan,
        "threshold_2": np.nan,
        "uup_weight": np.nan,
        "uup_weight_2": np.nan,
        "cost_bps": np.nan,
        "two_level": False,
        "level1_months": 0,
        "level2_months": 0,
    })
    summary_rows.append(a100_summary)

    # =========================
    # ONE-LEVEL GRID
    # =========================
    for threshold in args.thresholds:
        for weight in args.weights:
            for cost_bps in args.cost_bps:
                overlay = build_active_uup_overlay_daily(
                    a_daily=a_daily,
                    baseline_daily=baseline_daily,
                    uup_daily=uup_daily,
                    threshold=threshold,
                    uup_weight=weight,
                    cost_bps=cost_bps,
                )

                label = (
                    f"ACTIVE_UUP"
                    f"_w{int(round(weight * 100)):03d}"
                    f"_thr{int(round(threshold * 10000)):05d}"
                    f"_cost{int(round(cost_bps)):03d}bps"
                )

                level_by_month = (
                    overlay["hedge_level"]
                    .groupby(month_end_index(pd.DatetimeIndex(overlay.index)))
                    .max()
                )

                summary = summarize_daily_stream(
                    label=label,
                    daily_return=overlay["overlay_return"],
                    hedge_on=overlay["hedge_on"],
                )

                summary.update({
                    "threshold": threshold,
                    "threshold_2": np.nan,
                    "uup_weight": weight,
                    "uup_weight_2": np.nan,
                    "cost_bps": cost_bps,
                    "two_level": False,
                    "level1_months": int((level_by_month == 1).sum()),
                    "level2_months": 0,
                })

                summary_rows.append(summary)

                portfolio_returns[label] = overlay["overlay_return"]
                overlay_details[label] = overlay

    # =========================
    # TWO-LEVEL GRID
    # =========================
    if args.two_level:
        for threshold_1 in args.thresholds_level1:
            for threshold_2 in args.thresholds_level2:
                if threshold_2 <= threshold_1:
                    continue

                for cost_bps in args.cost_bps:
                    overlay = build_active_uup_overlay_daily_two_level(
                        a_daily=a_daily,
                        baseline_daily=baseline_daily,
                        uup_daily=uup_daily,
                        threshold_1=threshold_1,
                        threshold_2=threshold_2,
                        uup_weight_1=args.weight_level1,
                        uup_weight_2=args.weight_level2,
                        cost_bps=cost_bps,
                    )

                    label = (
                        f"ACTIVE_UUP_2LEVEL"
                        f"_w{int(round(args.weight_level1 * 100)):03d}"
                        f"_{int(round(args.weight_level2 * 100)):03d}"
                        f"_thr{int(round(threshold_1 * 10000)):05d}"
                        f"_{int(round(threshold_2 * 10000)):05d}"
                        f"_cost{int(round(cost_bps)):03d}bps"
                    )

                    level_by_month = (
                        overlay["hedge_level"]
                        .groupby(month_end_index(pd.DatetimeIndex(overlay.index)))
                        .max()
                    )

                    summary = summarize_daily_stream(
                        label=label,
                        daily_return=overlay["overlay_return"],
                        hedge_on=overlay["hedge_on"],
                    )

                    summary.update({
                        "threshold": threshold_1,
                        "threshold_2": threshold_2,
                        "uup_weight": args.weight_level1,
                        "uup_weight_2": args.weight_level2,
                        "cost_bps": cost_bps,
                        "two_level": True,
                        "level1_months": int((level_by_month == 1).sum()),
                        "level2_months": int((level_by_month == 2).sum()),
                    })

                    summary_rows.append(summary)

                    portfolio_returns[label] = overlay["overlay_return"]
                    overlay_details[label] = overlay

    summary_df = pd.DataFrame(summary_rows)

    relative = build_relative_to_baseline(
        summary=summary_df,
        baseline_label=args.baseline_strategy,
    )

    full = summary_df.merge(relative, on="portfolio", how="left")
    full = full.sort_values(
        [
            "delta_calmar",
            "delta_maxdd_daily",
            "delta_cagr",
            "delta_ulcer_index",
        ],
        ascending=[False, False, False, True],
    )

    # =========================
    # ROLLINGS
    # =========================
    daily_rolling = build_daily_rolling_table(
        portfolio_returns=portfolio_returns,
        windows=args.rolling_day_windows,
    )

    monthly_rolling = build_monthly_rolling_table(
        portfolio_returns=portfolio_returns,
        windows=args.rolling_month_windows,
    )

    rolling_summary = build_rolling_summary(
        daily_rolling=daily_rolling,
        monthly_rolling=monthly_rolling,
    )

    rolling_winrate = build_rolling_winrate_vs_baseline(
        daily_rolling=daily_rolling,
        monthly_rolling=monthly_rolling,
        baseline_label=args.baseline_strategy,
    )

    annual_returns = build_annual_returns_table(
        portfolio_returns=portfolio_returns,
    )

    # =========================
    # NAMED PERIODS
    # =========================
    subperiods = [
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
        ("overlap_uk_available", "2020-01-01", "2026-03-01"),
    ]

    top_labels = list(full["portfolio"].head(10))
    selected_for_subperiods = {
        label: portfolio_returns[label]
        for label in top_labels
        if label in portfolio_returns
    }

    if args.baseline_strategy in portfolio_returns:
        selected_for_subperiods[args.baseline_strategy] = portfolio_returns[args.baseline_strategy]

    if "A100" in portfolio_returns:
        selected_for_subperiods["A100"] = portfolio_returns["A100"]

    subperiod_summary = build_subperiod_summary(
        portfolio_returns=selected_for_subperiods,
        subperiods=subperiods,
    )

    negative_streaks_table = build_negative_streaks_table(
        portfolio_returns=selected_for_subperiods,
        subperiods=subperiods,
    )

    # =========================
    # ATTRIBUTION
    # =========================
    default_label = "ACTIVE_UUP_w020_thr00000_cost000bps"
    attribution = pd.DataFrame()

    if default_label in overlay_details:
        attribution = build_hedge_on_attribution(overlay_details[default_label])

    best_label = str(full.iloc[0]["portfolio"])
    best_attribution = pd.DataFrame()

    if best_label in overlay_details:
        best_attribution = build_hedge_on_attribution(overlay_details[best_label])

    # =========================
    # CORRELATIONS
    # =========================
    correlation_report = build_correlation_report(
        daily_close=daily_close,
        a_daily=a_daily,
        baseline_daily=baseline_daily,
        uup_daily=uup_daily,
        group_assets=args.group_assets,
    )

    # =========================
    # DAILY DETAIL SELECTED
    # =========================
    detail_rows: List[pd.DataFrame] = []
    detail_labels: List[str] = []

    if default_label in overlay_details:
        detail_labels.append(default_label)

    if best_label in overlay_details and best_label not in detail_labels:
        detail_labels.append(best_label)

    for label in top_labels:
        if label in overlay_details and label not in detail_labels:
            detail_labels.append(label)

    for label in detail_labels[:10]:
        d = overlay_details[label].reset_index().rename(columns={"index": "date"})
        d.insert(0, "portfolio", label)
        detail_rows.append(d)

    daily_detail = pd.concat(detail_rows, ignore_index=True) if detail_rows else pd.DataFrame()

    # =========================
    # SAVE
    # =========================
    full_file = output_dir / "uup_deep_dive_full_sensitivity.csv"
    relative_file = output_dir / "uup_deep_dive_relative_vs_baseline.csv"
    rolling_daily_file = output_dir / "uup_deep_dive_rolling_daily.csv"
    rolling_monthly_file = output_dir / "uup_deep_dive_rolling_monthly.csv"
    rolling_summary_file = output_dir / "uup_deep_dive_rolling_summary.csv"
    rolling_winrate_file = output_dir / "uup_deep_dive_rolling_winrate_vs_baseline.csv"
    annual_returns_file = output_dir / "uup_deep_dive_annual_returns.csv"
    subperiod_file = output_dir / "uup_deep_dive_subperiod_summary.csv"
    negative_streaks_file = output_dir / "uup_deep_dive_negative_month_streaks.csv"
    attribution_file = output_dir / "uup_deep_dive_default_uup20_attribution.csv"
    best_attribution_file = output_dir / "uup_deep_dive_best_variant_attribution.csv"
    corr_file = output_dir / "uup_deep_dive_correlations.csv"
    detail_file = output_dir / "uup_deep_dive_daily_detail_selected.csv"

    full.to_csv(full_file, index=False, float_format="%.10f")
    relative.to_csv(relative_file, index=False, float_format="%.10f")
    daily_rolling.to_csv(rolling_daily_file, index=False, float_format="%.10f")
    monthly_rolling.to_csv(rolling_monthly_file, index=False, float_format="%.10f")
    rolling_summary.to_csv(rolling_summary_file, index=False, float_format="%.10f")
    rolling_winrate.to_csv(rolling_winrate_file, index=False, float_format="%.10f")
    annual_returns.to_csv(annual_returns_file, index=False, float_format="%.10f")
    subperiod_summary.to_csv(subperiod_file, index=False, float_format="%.10f")
    negative_streaks_table.to_csv(negative_streaks_file, index=False, float_format="%.10f")
    attribution.to_csv(attribution_file, index=False, float_format="%.10f")
    best_attribution.to_csv(best_attribution_file, index=False, float_format="%.10f")
    correlation_report.to_csv(corr_file, index=False, float_format="%.10f")
    daily_detail.to_csv(detail_file, index=False, float_format="%.10f")

    print(f"[OK] zapisano: {full_file}")
    print(f"[OK] zapisano: {relative_file}")
    print(f"[OK] zapisano: {rolling_daily_file}")
    print(f"[OK] zapisano: {rolling_monthly_file}")
    print(f"[OK] zapisano: {rolling_summary_file}")
    print(f"[OK] zapisano: {rolling_winrate_file}")
    print(f"[OK] zapisano: {annual_returns_file}")
    print(f"[OK] zapisano: {subperiod_file}")
    print(f"[OK] zapisano: {negative_streaks_file}")
    print(f"[OK] zapisano: {attribution_file}")
    print(f"[OK] zapisano: {best_attribution_file}")
    print(f"[OK] zapisano: {corr_file}")
    print(f"[OK] zapisano: {detail_file}")

    show_cols = [
        "portfolio",
        "two_level",
        "threshold",
        "threshold_2",
        "uup_weight",
        "uup_weight_2",
        "level1_months",
        "level2_months",
        "cost_bps",
        "hedge_on_months",
        "hedge_on_pct_months",
        "final_equity_daily",
        "cagr",
        "maxdd_daily",
        "maxdd_daily_date",
        "calmar",
        "maxdd_monthly",
        "maxdd_monthly_date",
        "maxdd_monthly_start_date",
        "maxdd_monthly_trough_date",
        "maxdd_monthly_recovery_date",
        "maxdd_monthly_duration_months",
        "calmar_monthly",
        "negative_months",
        "negative_months_pct",
        "months_lt_minus_10",
        "months_lt_minus_5",
        "months_lt_minus_3",
        "months_gt_3",
        "months_gt_5",
        "max_negative_streak_months",
        "worst_negative_streak_return",
        "ulcer_index",
        "underwater_pct_days",
        "max_underwater_days",
        "worst_month",
        "worst_6m_return",
        "worst_12m_return",
        "delta_cagr",
        "delta_maxdd_daily",
        "delta_calmar",
        "delta_maxdd_monthly",
        "delta_calmar_monthly",
        "delta_negative_months",
        "delta_months_lt_minus_5",
        "delta_months_lt_minus_3",
        "delta_months_gt_3",
        "delta_months_gt_5",
        "delta_max_negative_streak_months",
        "delta_worst_negative_streak_return",
        "delta_ulcer_index",
    ]

    existing = [c for c in show_cols if c in full.columns]

    print("\n=== TOP UUP SENSITIVITY VS BASELINE ===")
    print(full[existing].head(50).to_string(index=False))

    if not annual_returns.empty:
        print("\n=== ANNUAL RETURNS SAMPLE ===")
        annual_cols = [
            "year",
            "portfolio",
            "annual_return",
            "maxdd_daily_in_year",
            "maxdd_monthly_in_year",
            "worst_month",
            "best_month",
        ]
        print(annual_returns[annual_cols].head(80).to_string(index=False))

    if not attribution.empty:
        print("\n=== DEFAULT UUP20 ATTRIBUTION ===")
        print(attribution.to_string(index=False))

    if not best_attribution.empty:
        print("\n=== BEST VARIANT ATTRIBUTION ===")
        print(best_attribution.to_string(index=False))

    print("\n=== CORRELATIONS ===")
    print(correlation_report.to_string(index=False))


if __name__ == "__main__":
    main()