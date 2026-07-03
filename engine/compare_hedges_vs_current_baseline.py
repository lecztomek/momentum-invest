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


# =========================
# LOADERS
# =========================

def load_daily_equity_all(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = clean_columns(df)

    date_col = find_date_column(df)
    df = df.rename(columns={date_col: "date"})

    required = {"date", "strategy"}

    if "portfolio_daily_return" not in df.columns and "equity_daily" not in df.columns:
        raise ValueError(
            "Plik musi mieć portfolio_daily_return albo equity_daily."
        )

    missing = required - set(df.columns)

    if missing:
        raise ValueError(f"Brakuje kolumn: {missing}")

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["strategy", "date"])

    if "portfolio_daily_return" not in df.columns:
        df["portfolio_daily_return"] = (
            df.groupby("strategy")["equity_daily"]
            .pct_change()
            .fillna(0.0)
        )

    if "equity_daily" not in df.columns:
        df["equity_daily"] = (
            df.groupby("strategy")["portfolio_daily_return"]
            .transform(lambda x: compound_returns_to_equity(x))
        )

    df["portfolio_daily_return"] = pd.to_numeric(
        df["portfolio_daily_return"],
        errors="coerce",
    )

    df["equity_daily"] = pd.to_numeric(
        df["equity_daily"],
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


def build_ticker_returns(daily_close: pd.DataFrame) -> pd.DataFrame:
    prices = daily_close.copy().ffill()
    rets = prices.pct_change()
    rets = rets.replace([np.inf, -np.inf], np.nan)

    return rets


# =========================
# UNDERWATER / DRAWDOWN EPISODES
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
            recovery_date = date

            episodes.append({
                "start_date": start_date,
                "trough_date": trough_date,
                "recovery_date": recovery_date,
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


def summarize_underwater(equity: pd.Series) -> Dict[str, Any]:
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

    underwater_days = int(underwater.sum())
    underwater_pct_days = float(underwater.mean())

    ulcer_index = float(np.sqrt(np.mean(np.square(dd.clip(upper=0.0)))))

    avg_drawdown = float(dd[dd < 0].mean()) if (dd < 0).any() else 0.0
    median_drawdown = float(dd[dd < 0].median()) if (dd < 0).any() else 0.0

    if episodes.empty:
        return {
            "underwater_days": underwater_days,
            "underwater_pct_days": underwater_pct_days,
            "max_underwater_days": 0,
            "avg_underwater_episode_days": 0,
            "drawdown_episode_count": 0,
            "unrecovered_episode_count": 0,
            "ulcer_index": ulcer_index,
            "avg_drawdown": avg_drawdown,
            "median_drawdown": median_drawdown,
            "time_to_recover_maxdd_days": 0,
        }

    max_underwater_days = int(episodes["underwater_days"].max())
    avg_underwater_episode_days = float(episodes["underwater_days"].mean())
    drawdown_episode_count = int(len(episodes))
    unrecovered_episode_count = int((~episodes["is_recovered"]).sum())

    maxdd_date = dd.idxmin()

    episode_with_maxdd = episodes[
        (episodes["start_date"] <= maxdd_date)
        & (
            (episodes["recovery_date"].isna())
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
        "underwater_days": underwater_days,
        "underwater_pct_days": underwater_pct_days,
        "max_underwater_days": max_underwater_days,
        "avg_underwater_episode_days": avg_underwater_episode_days,
        "drawdown_episode_count": drawdown_episode_count,
        "unrecovered_episode_count": unrecovered_episode_count,
        "ulcer_index": ulcer_index,
        "avg_drawdown": avg_drawdown,
        "median_drawdown": median_drawdown,
        "time_to_recover_maxdd_days": time_to_recover_maxdd_days,
    }


# =========================
# METRICS
# =========================

def monthly_returns_from_daily_returns(r: pd.Series) -> pd.Series:
    return r.resample("M").apply(period_return)


def summarize_stream(
    label: str,
    daily_return: pd.Series,
) -> Dict[str, Any]:
    r = daily_return.dropna().copy()

    if r.empty:
        raise ValueError(f"Brak danych dla {label}")

    equity = compound_returns_to_equity(r)
    dd = calc_drawdown(equity)

    start_date = pd.Timestamp(r.index[0])
    end_date = pd.Timestamp(r.index[-1])

    final_equity = float(equity.iloc[-1])
    cagr = calc_cagr(1.0, final_equity, start_date, end_date)
    maxdd = float(dd.min())

    monthly = monthly_returns_from_daily_returns(r).dropna()

    monthly_negative = monthly < 0

    worst_3m = monthly.rolling(3).apply(lambda x: np.prod(1.0 + x) - 1.0, raw=False).min()
    worst_6m = monthly.rolling(6).apply(lambda x: np.prod(1.0 + x) - 1.0, raw=False).min()
    worst_12m = monthly.rolling(12).apply(lambda x: np.prod(1.0 + x) - 1.0, raw=False).min()

    underwater_stats = summarize_underwater(equity)

    out: Dict[str, Any] = {
        "portfolio": label,
        "start_date": start_date,
        "end_date": end_date,
        "days": len(r),

        "final_equity": final_equity,
        "total_return": final_equity - 1.0,
        "cagr": cagr,
        "maxdd": maxdd,
        "calmar": safe_calmar(cagr, maxdd),

        "vol_daily": float(r.std()),
        "vol_annualized": float(r.std() * np.sqrt(252)),

        "positive_days_pct": float((r > 0).mean()),
        "negative_days_pct": float((r < 0).mean()),
        "avg_daily_return": float(r.mean()),
        "avg_positive_day": float(r[r > 0].mean()) if (r > 0).any() else np.nan,
        "avg_negative_day": float(r[r < 0].mean()) if (r < 0).any() else np.nan,
        "worst_day": float(r.min()),
        "best_day": float(r.max()),

        "months": len(monthly),
        "negative_months": int(monthly_negative.sum()),
        "negative_months_pct": float(monthly_negative.mean()),
        "positive_months_pct": float((monthly > 0).mean()),
        "avg_monthly_return": float(monthly.mean()),
        "avg_positive_month": float(monthly[monthly > 0].mean()) if (monthly > 0).any() else np.nan,
        "avg_negative_month": float(monthly[monthly < 0].mean()) if (monthly < 0).any() else np.nan,
        "worst_month": float(monthly.min()) if len(monthly) else np.nan,
        "best_month": float(monthly.max()) if len(monthly) else np.nan,
        "max_consecutive_negative_months": max_consecutive_true(monthly_negative),

        "worst_3m_return": float(worst_3m) if not pd.isna(worst_3m) else np.nan,
        "worst_6m_return": float(worst_6m) if not pd.isna(worst_6m) else np.nan,
        "worst_12m_return": float(worst_12m) if not pd.isna(worst_12m) else np.nan,
    }

    out.update(underwater_stats)

    return out


def build_relative_to_baseline(
    summary: pd.DataFrame,
    baseline_label: str,
) -> pd.DataFrame:
    if baseline_label not in set(summary["portfolio"]):
        raise ValueError(
            f"Nie znaleziono baseline '{baseline_label}' w summary. "
            f"Dostępne: {list(summary['portfolio'])}"
        )

    base = summary[summary["portfolio"] == baseline_label].iloc[0].to_dict()

    rows: List[Dict[str, Any]] = []

    for _, row_raw in summary.iterrows():
        row = row_raw.to_dict()

        out = {
            "portfolio": row["portfolio"],
            "baseline": baseline_label,

            "delta_final_equity": row["final_equity"] - base["final_equity"],
            "delta_cagr": row["cagr"] - base["cagr"],

            # Dodatnie delta_maxdd = lepiej, bo np. -0.19 - (-0.26) = +0.07
            "delta_maxdd": row["maxdd"] - base["maxdd"],
            "delta_calmar": row["calmar"] - base["calmar"],

            # Dodatnie = więcej miesięcy minusowych, czyli gorzej
            "delta_negative_months": row["negative_months"] - base["negative_months"],
            "delta_negative_months_pct": row["negative_months_pct"] - base["negative_months_pct"],

            # Dodatnie = gorszy / dłuższy underwater, czyli gorzej
            "delta_underwater_days": row["underwater_days"] - base["underwater_days"],
            "delta_underwater_pct_days": row["underwater_pct_days"] - base["underwater_pct_days"],
            "delta_max_underwater_days": row["max_underwater_days"] - base["max_underwater_days"],
            "delta_avg_underwater_episode_days": (
                row["avg_underwater_episode_days"] - base["avg_underwater_episode_days"]
            ),

            # Ujemne = lepiej, bo niższy Ulcer Index
            "delta_ulcer_index": row["ulcer_index"] - base["ulcer_index"],

            # Dodatnie = lepiej, bo mniej ujemny najgorszy okres
            "delta_worst_month": row["worst_month"] - base["worst_month"],
            "delta_worst_3m_return": row["worst_3m_return"] - base["worst_3m_return"],
            "delta_worst_6m_return": row["worst_6m_return"] - base["worst_6m_return"],
            "delta_worst_12m_return": row["worst_12m_return"] - base["worst_12m_return"],

            # Dodatnie = gorzej, bo dłuższa seria minusowych miesięcy
            "delta_max_consecutive_negative_months": (
                row["max_consecutive_negative_months"]
                - base["max_consecutive_negative_months"]
            ),
        }

        rows.append(out)

    return pd.DataFrame(rows)


def add_composite_score_vs_baseline(relative: pd.DataFrame) -> pd.DataFrame:
    """
    Score preferuje:
    - wyższy Calmar,
    - mniejszy MaxDD,
    - mniej underwater,
    - niższy Ulcer Index,
    - mniej minusowych miesięcy,
    - lepsze najgorsze rolling okresy,
    ale karze za spadek CAGR.

    To nie jest prawda absolutna, tylko ranking pomocniczy.
    """
    df = relative.copy()

    def rank_high(col: str) -> pd.Series:
        return df[col].rank(pct=True, ascending=True)

    def rank_low(col: str) -> pd.Series:
        return df[col].rank(pct=True, ascending=False)

    df["quality_score_vs_baseline"] = (
        0.20 * rank_high("delta_calmar")
        + 0.15 * rank_high("delta_maxdd")
        + 0.10 * rank_low("delta_ulcer_index")
        + 0.10 * rank_low("delta_underwater_pct_days")
        + 0.10 * rank_low("delta_max_underwater_days")
        + 0.10 * rank_low("delta_negative_months_pct")
        + 0.10 * rank_high("delta_worst_6m_return")
        + 0.10 * rank_high("delta_worst_12m_return")
        + 0.05 * rank_high("delta_cagr")
    )

    return df.sort_values("quality_score_vs_baseline", ascending=False)


# =========================
# PORTFOLIO BUILDERS
# =========================

def get_strategy_returns(
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

    return df["portfolio_daily_return"].astype(float)


def build_candidate_portfolios(
    a_return: pd.Series,
    baseline_return: pd.Series,
    ticker_returns: pd.DataFrame,
    hedges: List[str],
    hedge_weights: List[float],
    baseline_label: str,
) -> Dict[str, pd.Series]:
    portfolios: Dict[str, pd.Series] = {}

    portfolios[baseline_label] = baseline_return.copy()
    portfolios["A100"] = a_return.copy()

    ticker_map = {normalize_ticker(c): str(c) for c in ticker_returns.columns}

    for hedge in hedges:
        key = normalize_ticker(hedge)

        if key not in ticker_map:
            print(f"[WARN] Brak hedge tickera w daily_close: {hedge}")
            continue

        col = ticker_map[key]
        h_return = ticker_returns[col]

        pair = pd.concat(
            [
                a_return.rename("A"),
                h_return.rename("HEDGE"),
            ],
            axis=1,
        ).dropna()

        if pair.empty:
            print(f"[WARN] Brak wspólnych dat dla hedge: {hedge}")
            continue

        for wh in hedge_weights:
            wa = 1.0 - wh
            label = f"A{int(round(wa * 100)):03d}_{col}_{int(round(wh * 100)):03d}"

            portfolios[label] = wa * pair["A"] + wh * pair["HEDGE"]

    return portfolios


# =========================
# MONTHLY DETAIL
# =========================

def build_monthly_table(portfolios: Dict[str, pd.Series]) -> pd.DataFrame:
    rows: List[pd.DataFrame] = []

    for label, r in portfolios.items():
        m = monthly_returns_from_daily_returns(r.dropna())

        tmp = pd.DataFrame({
            "date": m.index,
            "portfolio": label,
            "monthly_return": m.values,
        })

        rows.append(tmp)

    return pd.concat(rows, ignore_index=True)


def build_underwater_episodes_table(portfolios: Dict[str, pd.Series]) -> pd.DataFrame:
    rows: List[pd.DataFrame] = []

    for label, r in portfolios.items():
        eq = compound_returns_to_equity(r.dropna())
        ep = underwater_episodes(eq)

        if ep.empty:
            continue

        ep.insert(0, "portfolio", label)
        rows.append(ep)

    if not rows:
        return pd.DataFrame()

    return pd.concat(rows, ignore_index=True)


# =========================
# MAIN
# =========================

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Kompleksowo porównuje hedge warianty do obecnego baseline, np. A80/B20: "
            "miesiące stratne, underwater, recovery, Ulcer Index, rolling losses."
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
        help="daily_close.csv z cenami tickerów.",
    )

    parser.add_argument(
        "--a-strategy",
        default="A",
        help="Nazwa strategii A w daily_equity_all.csv. Domyślnie A.",
    )

    parser.add_argument(
        "--baseline-strategy",
        default="COMBINED",
        help="Nazwa obecnego portfela bazowego, np. COMBINED.",
    )

    parser.add_argument(
        "--hedges",
        nargs="+",
        required=True,
        help="Tickery hedge do testu, np. tlt.us edv.us rwm.us sh.us.",
    )

    parser.add_argument(
        "--hedge-weights",
        nargs="+",
        type=float,
        default=[0.05, 0.10, 0.15, 0.20, 0.30],
        help="Wagi hedge do testu.",
    )

    parser.add_argument(
        "--output-dir",
        default="output_hedge_vs_baseline",
        help="Folder wyjściowy.",
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    daily_all = load_daily_equity_all(Path(args.daily_equity_all))
    daily_close = load_daily_close(Path(args.daily_close))
    ticker_returns = build_ticker_returns(daily_close)

    a_return = get_strategy_returns(daily_all, args.a_strategy)
    baseline_return = get_strategy_returns(daily_all, args.baseline_strategy)

    # Wspólny zakres A i baseline
    common = pd.concat(
        [
            a_return.rename("A"),
            baseline_return.rename("BASELINE"),
        ],
        axis=1,
    ).dropna()

    a_return = common["A"]
    baseline_return = common["BASELINE"]

    portfolios = build_candidate_portfolios(
        a_return=a_return,
        baseline_return=baseline_return,
        ticker_returns=ticker_returns,
        hedges=args.hedges,
        hedge_weights=args.hedge_weights,
        baseline_label=args.baseline_strategy,
    )

    summary_rows: List[Dict[str, Any]] = []

    for label, r in portfolios.items():
        summary_rows.append(summarize_stream(label, r))

    summary = pd.DataFrame(summary_rows)

    relative = build_relative_to_baseline(
        summary=summary,
        baseline_label=args.baseline_strategy,
    )

    relative_scored = add_composite_score_vs_baseline(relative)

    monthly_table = build_monthly_table(portfolios)
    episodes_table = build_underwater_episodes_table(portfolios)

    summary_file = output_dir / "hedge_vs_baseline_summary.csv"
    relative_file = output_dir / "hedge_vs_baseline_relative.csv"
    monthly_file = output_dir / "hedge_vs_baseline_monthly_returns.csv"
    episodes_file = output_dir / "hedge_vs_baseline_underwater_episodes.csv"

    summary.to_csv(summary_file, index=False, float_format="%.10f")
    relative_scored.to_csv(relative_file, index=False, float_format="%.10f")
    monthly_table.to_csv(monthly_file, index=False, float_format="%.10f")
    episodes_table.to_csv(episodes_file, index=False, float_format="%.10f")

    print(f"[OK] zapisano: {summary_file}")
    print(f"[OK] zapisano: {relative_file}")
    print(f"[OK] zapisano: {monthly_file}")
    print(f"[OK] zapisano: {episodes_file}")

    print("\n=== SUMMARY ===")
    show_cols = [
        "portfolio",
        "final_equity",
        "cagr",
        "maxdd",
        "calmar",
        "negative_months",
        "negative_months_pct",
        "ulcer_index",
        "underwater_pct_days",
        "max_underwater_days",
        "avg_underwater_episode_days",
        "time_to_recover_maxdd_days",
        "worst_month",
        "worst_3m_return",
        "worst_6m_return",
        "worst_12m_return",
        "max_consecutive_negative_months",
    ]

    print(
        summary[show_cols]
        .sort_values("calmar", ascending=False)
        .to_string(index=False)
    )

    print("\n=== RELATIVE VS BASELINE ===")
    rel_cols = [
        "portfolio",
        "baseline",
        "quality_score_vs_baseline",
        "delta_cagr",
        "delta_maxdd",
        "delta_calmar",
        "delta_negative_months",
        "delta_negative_months_pct",
        "delta_underwater_pct_days",
        "delta_max_underwater_days",
        "delta_ulcer_index",
        "delta_worst_month",
        "delta_worst_6m_return",
        "delta_worst_12m_return",
    ]

    print(
        relative_scored[rel_cols]
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()