from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


# =========================
# IO / FORMAT
# =========================

def safe_read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception as e:
        return pd.DataFrame({"_read_error": [str(e)], "_path": [str(path)]})


def safe_read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8-sig") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def as_num(value: Any) -> Optional[float]:
    x = pd.to_numeric(value, errors="coerce")
    if pd.isna(x):
        return None
    return float(x)


def fmt_pct(value: Any, digits: int = 2) -> str:
    x = as_num(value)
    if x is None:
        return "n/a"
    return f"{x * 100:.{digits}f}%"


def fmt_pp(value: Any, digits: int = 2) -> str:
    x = as_num(value)
    if x is None:
        return "n/a"
    return f"{x * 100:+.{digits}f} pp"


def fmt_num(value: Any, digits: int = 2) -> str:
    x = as_num(value)
    if x is None:
        return "n/a"
    return f"{x:.{digits}f}"


def fmt_int(value: Any) -> str:
    x = as_num(value)
    if x is None:
        return "n/a"
    return str(int(x))


def h1(title: str) -> str:
    return "\n" + "=" * 100 + "\n" + title.upper() + "\n" + "=" * 100 + "\n"


def h2(title: str) -> str:
    return "\n" + title + "\n" + "-" * 100 + "\n"


def bullet(label: str, value: Any) -> str:
    return f"- {label}: {value}\n"


def table(df: pd.DataFrame, max_rows: int = 30, max_cols: int = 18) -> str:
    if df.empty:
        return "Brak danych.\n"

    d = df.head(max_rows).copy()

    if len(d.columns) > max_cols:
        d = d.iloc[:, :max_cols].copy()

    with pd.option_context(
        "display.max_columns", max_cols,
        "display.width", 280,
        "display.max_colwidth", 100,
    ):
        return d.to_string(index=False) + "\n"


def select_cols(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    existing = [c for c in cols if c in df.columns]
    if not existing:
        return df.copy()
    return df[existing].copy()


def pick(row: Dict[str, Any], names: List[str]) -> Any:
    for name in names:
        if name in row and pd.notna(row.get(name)):
            return row.get(name)
    return None


def pick_num(row: Dict[str, Any], names: List[str]) -> Optional[float]:
    return as_num(pick(row, names))


def sort_numeric(df: pd.DataFrame, col: str, ascending: bool = True) -> pd.DataFrame:
    if df.empty or col not in df.columns:
        return pd.DataFrame()

    d = df.copy()
    d[col] = pd.to_numeric(d[col], errors="coerce")
    d = d.dropna(subset=[col])

    if d.empty:
        return pd.DataFrame()

    return d.sort_values(col, ascending=ascending)


# =========================
# PATHS
# =========================

def discover_paths(run_dir: Path) -> Dict[str, Path]:
    return {
        "manifest": run_dir / "RUN_MANIFEST.json",

        "us_data_check": run_dir / "01_check_us_data" / "us_data_check.csv",

        "us_base_full": run_dir / "03_us_backtest_base" / "summary_full_period.csv",
        "us_base_rolling": run_dir / "03_us_backtest_base" / "summary_rolling.csv",
        "us_base_worst": run_dir / "03_us_backtest_base" / "worst_rolling_windows.csv",
        "us_base_underwater": run_dir / "03_us_backtest_base" / "summary_underwater_periods.csv",
        "us_base_named": run_dir / "03_us_backtest_base" / "summary_named_periods.csv",
        "us_base_monthly": run_dir / "03_us_backtest_base" / "all_strategies_monthly.csv",

        "us_base_daily_summary": run_dir / "04_us_daily_base" / "summary_daily_maxdd.csv",
        "us_base_daily_periods": run_dir / "04_us_daily_base" / "period_daily_maxdd.csv",
        "us_base_daily_equity": run_dir / "04_us_daily_base" / "daily_equity_drawdown.csv",

        "us_hedge_overlay_dir": run_dir / "05_us_hedge_overlay_all",
        "us_hedge_summary": run_dir / "05_us_hedge_overlay_all" / "monthly_active_hedge_daily_summary.csv",
        "us_hedge_relative": run_dir / "05_us_hedge_overlay_all" / "monthly_active_hedge_daily_relative_vs_baseline.csv",
        "us_hedge_ranked": run_dir / "05_us_hedge_overlay_all" / "monthly_active_hedge_daily_full_ranked.csv",

        "selected_us_monthly": run_dir / "06_us_selected_hedge_export" / "selected_us_monthly.csv",
        "selected_metadata": run_dir / "06_us_selected_hedge_export" / "selected_hedge_metadata.json",

        "us_selected_daily_summary": run_dir / "07_us_selected_daily_maxdd" / "summary_daily_maxdd.csv",
        "us_selected_daily_periods": run_dir / "07_us_selected_daily_maxdd" / "period_daily_maxdd.csv",
        "us_selected_daily_equity": run_dir / "07_us_selected_daily_maxdd" / "daily_equity_drawdown.csv",

        "us_selected_vs_base_summary": run_dir / "08_us_selected_vs_base" / "hedge_vs_baseline_summary.csv",
        "us_selected_vs_base_relative": run_dir / "08_us_selected_vs_base" / "hedge_vs_baseline_relative.csv",

        "uk_data_check": run_dir / "09_check_uk_data" / "uk_data_check.csv",

        "uk_base_monthly": run_dir / "11_uk_replay_base_A" / "replayed_monthly.csv",
        "uk_base_full": run_dir / "11_uk_replay_base_A" / "summary_full_period.csv",
        "uk_base_rolling": run_dir / "11_uk_replay_base_A" / "summary_rolling.csv",
        "uk_base_worst": run_dir / "11_uk_replay_base_A" / "worst_rolling_windows.csv",
        "uk_base_underwater": run_dir / "11_uk_replay_base_A" / "summary_underwater_periods.csv",
        "uk_base_named": run_dir / "11_uk_replay_base_A" / "summary_named_periods.csv",
        "uk_base_holdings": run_dir / "11_uk_replay_base_A" / "replayed_holdings.csv",
        "uk_base_trades": run_dir / "11_uk_replay_base_A" / "replayed_trades.csv",

        "uk_base_daily_summary": run_dir / "12_uk_daily_base_A" / "summary_daily_maxdd.csv",
        "uk_base_daily_periods": run_dir / "12_uk_daily_base_A" / "period_daily_maxdd.csv",
        "uk_base_daily_equity": run_dir / "12_uk_daily_base_A" / "daily_equity_drawdown.csv",

        "uk_selected_monthly": run_dir / "13_uk_replay_selected_hedge" / "replayed_monthly.csv",
        "uk_selected_full": run_dir / "13_uk_replay_selected_hedge" / "summary_full_period.csv",
        "uk_selected_rolling": run_dir / "13_uk_replay_selected_hedge" / "summary_rolling.csv",
        "uk_selected_worst": run_dir / "13_uk_replay_selected_hedge" / "worst_rolling_windows.csv",
        "uk_selected_underwater": run_dir / "13_uk_replay_selected_hedge" / "summary_underwater_periods.csv",
        "uk_selected_named": run_dir / "13_uk_replay_selected_hedge" / "summary_named_periods.csv",
        "uk_selected_holdings": run_dir / "13_uk_replay_selected_hedge" / "replayed_holdings.csv",
        "uk_selected_trades": run_dir / "13_uk_replay_selected_hedge" / "replayed_trades.csv",

        "uk_selected_daily_summary": run_dir / "14_uk_daily_selected_hedge" / "summary_daily_maxdd.csv",
        "uk_selected_daily_periods": run_dir / "14_uk_daily_selected_hedge" / "period_daily_maxdd.csv",
        "uk_selected_daily_equity": run_dir / "14_uk_daily_selected_hedge" / "daily_equity_drawdown.csv",
    }


def load_data(run_dir: Path) -> Tuple[Dict[str, Path], Dict[str, pd.DataFrame], Dict[str, Any]]:
    paths = discover_paths(run_dir)

    csv_keys = [
        "us_data_check",
        "us_base_full",
        "us_base_rolling",
        "us_base_worst",
        "us_base_underwater",
        "us_base_named",
        "us_base_monthly",
        "us_base_daily_summary",
        "us_base_daily_periods",
        "us_base_daily_equity",
        "us_hedge_summary",
        "us_hedge_relative",
        "us_hedge_ranked",
        "selected_us_monthly",
        "us_selected_daily_summary",
        "us_selected_daily_periods",
        "us_selected_daily_equity",
        "us_selected_vs_base_summary",
        "us_selected_vs_base_relative",
        "uk_data_check",
        "uk_base_monthly",
        "uk_base_full",
        "uk_base_rolling",
        "uk_base_worst",
        "uk_base_underwater",
        "uk_base_named",
        "uk_base_holdings",
        "uk_base_trades",
        "uk_base_daily_summary",
        "uk_base_daily_periods",
        "uk_base_daily_equity",
        "uk_selected_monthly",
        "uk_selected_full",
        "uk_selected_rolling",
        "uk_selected_worst",
        "uk_selected_underwater",
        "uk_selected_named",
        "uk_selected_holdings",
        "uk_selected_trades",
        "uk_selected_daily_summary",
        "uk_selected_daily_periods",
        "uk_selected_daily_equity",
    ]

    data = {k: safe_read_csv(paths[k]) for k in csv_keys}
    manifest = safe_read_json(paths["manifest"])

    return paths, data, manifest


# =========================
# METRICS
# =========================

@dataclass
class Metrics:
    label: str
    source: str
    start: Any = None
    end: Any = None
    months: Optional[float] = None
    days: Optional[float] = None
    final_equity: Optional[float] = None
    total_return: Optional[float] = None
    cagr: Optional[float] = None
    ann_vol: Optional[float] = None
    sharpe: Optional[float] = None
    maxdd: Optional[float] = None
    calmar: Optional[float] = None
    benchmark_final_equity: Optional[float] = None
    benchmark_total_return: Optional[float] = None
    benchmark_cagr: Optional[float] = None
    benchmark_maxdd: Optional[float] = None
    total_return_vs_benchmark: Optional[float] = None
    cagr_vs_benchmark: Optional[float] = None
    maxdd_vs_benchmark: Optional[float] = None
    hit_rate_excess: Optional[float] = None
    turnover: Optional[float] = None
    operations: Optional[float] = None


def extract_metrics(df: pd.DataFrame, label: str, source: str) -> Metrics:
    m = Metrics(label=label, source=source)

    if df.empty:
        return m

    row = df.iloc[0].to_dict()

    m.start = pick(row, ["start", "start_date"])
    m.end = pick(row, ["end", "end_date"])
    m.months = pick_num(row, ["months"])
    m.days = pick_num(row, ["days"])

    m.final_equity = pick_num(row, ["final_equity", "final_equity_daily", "strategy_final_equity"])
    m.total_return = pick_num(row, ["total_return"])
    m.cagr = pick_num(row, ["cagr"])
    m.ann_vol = pick_num(row, ["ann_vol", "vol_annualized"])
    m.sharpe = pick_num(row, ["sharpe"])
    m.maxdd = pick_num(row, ["max_drawdown", "maxdd", "maxdd_daily", "strategy_daily_maxdd"])
    m.calmar = pick_num(row, ["calmar"])

    m.benchmark_final_equity = pick_num(row, ["benchmark_final_equity", "benchmark_equity_final"])
    m.benchmark_total_return = pick_num(row, ["benchmark_total_return"])
    m.benchmark_cagr = pick_num(row, ["benchmark_cagr"])
    m.benchmark_maxdd = pick_num(row, ["benchmark_max_drawdown", "benchmark_maxdd", "benchmark_daily_maxdd"])

    m.total_return_vs_benchmark = pick_num(row, ["total_return_vs_benchmark", "relative_return_vs_benchmark"])
    m.cagr_vs_benchmark = pick_num(row, ["cagr_vs_benchmark"])
    m.maxdd_vs_benchmark = pick_num(row, ["maxdd_vs_benchmark", "maxdd_diff_vs_benchmark"])
    m.hit_rate_excess = pick_num(row, ["hit_rate_excess"])

    m.turnover = pick_num(row, ["total_turnover", "avg_monthly_turnover", "turnover"])
    m.operations = pick_num(row, ["total_operations", "operations"])

    return m


def metric_block(m: Metrics) -> str:
    out = ""
    out += bullet("Źródło", m.source)
    out += bullet("Okres", f"{m.start or 'n/a'} -> {m.end or 'n/a'}")
    if m.months is not None:
        out += bullet("Miesięcy", fmt_int(m.months))
    if m.days is not None:
        out += bullet("Dni", fmt_int(m.days))

    out += bullet("Final equity", fmt_num(m.final_equity))
    out += bullet("Total return", fmt_pct(m.total_return))
    out += bullet("CAGR", fmt_pct(m.cagr))
    out += bullet("Ann. vol", fmt_pct(m.ann_vol))
    out += bullet("Sharpe", fmt_num(m.sharpe))
    out += bullet("MaxDD", fmt_pct(m.maxdd))
    out += bullet("Calmar", fmt_num(m.calmar))

    if any(x is not None for x in [m.benchmark_final_equity, m.benchmark_cagr, m.benchmark_maxdd]):
        out += "\nBenchmark:\n"
        out += bullet("Benchmark final equity", fmt_num(m.benchmark_final_equity))
        out += bullet("Benchmark total return", fmt_pct(m.benchmark_total_return))
        out += bullet("Benchmark CAGR", fmt_pct(m.benchmark_cagr))
        out += bullet("Benchmark MaxDD", fmt_pct(m.benchmark_maxdd))

    if any(x is not None for x in [m.total_return_vs_benchmark, m.cagr_vs_benchmark, m.maxdd_vs_benchmark]):
        out += "\nRóżnica vs benchmark:\n"
        out += bullet("Total return vs benchmark", fmt_pp(m.total_return_vs_benchmark))
        out += bullet("CAGR vs benchmark", fmt_pp(m.cagr_vs_benchmark))
        out += bullet("MaxDD vs benchmark", fmt_pp(m.maxdd_vs_benchmark))
        out += bullet("Hit rate excess", fmt_pct(m.hit_rate_excess))

    if any(x is not None for x in [m.turnover, m.operations]):
        out += "\nObrót / operacje:\n"
        out += bullet("Turnover", fmt_num(m.turnover))
        out += bullet("Operations", fmt_int(m.operations))

    return out


def compare_metric_blocks(title: str, a: Metrics, b: Metrics, a_label: str, b_label: str) -> str:
    out = h2(title)

    out += bullet(f"{a_label} final equity", fmt_num(a.final_equity))
    out += bullet(f"{b_label} final equity", fmt_num(b.final_equity))
    if a.final_equity is not None and b.final_equity is not None and b.final_equity != 0:
        out += bullet(f"{a_label}/{b_label} final equity ratio", fmt_num(a.final_equity / b.final_equity, 4))

    out += bullet(f"{a_label} CAGR", fmt_pct(a.cagr))
    out += bullet(f"{b_label} CAGR", fmt_pct(b.cagr))
    if a.cagr is not None and b.cagr is not None:
        out += bullet(f"{a_label} - {b_label} CAGR", fmt_pp(a.cagr - b.cagr))

    out += bullet(f"{a_label} MaxDD", fmt_pct(a.maxdd))
    out += bullet(f"{b_label} MaxDD", fmt_pct(b.maxdd))
    if a.maxdd is not None and b.maxdd is not None:
        out += bullet(f"{a_label} - {b_label} MaxDD", fmt_pp(a.maxdd - b.maxdd))

    out += bullet(f"{a_label} Calmar", fmt_num(a.calmar))
    out += bullet(f"{b_label} Calmar", fmt_num(b.calmar))
    if a.calmar is not None and b.calmar is not None:
        out += bullet(f"{a_label} - {b_label} Calmar", fmt_num(a.calmar - b.calmar))

    return out


# =========================
# COVERAGE
# =========================

def date_coverage_from_df(df: pd.DataFrame, label: str) -> Dict[str, Any]:
    if df.empty:
        return {"dataset": label, "rows": 0, "start": None, "end": None, "months": None, "days": None}

    date_col = None
    for col in ["date", "start", "start_date", "period_start"]:
        if col in df.columns:
            date_col = col
            break

    if date_col is None:
        return {"dataset": label, "rows": len(df), "start": None, "end": None, "months": None, "days": None}

    dates = pd.to_datetime(df[date_col], errors="coerce").dropna()

    if dates.empty:
        return {"dataset": label, "rows": len(df), "start": None, "end": None, "months": None, "days": None}

    start = dates.min()
    end = dates.max()
    days = (end - start).days + 1
    months = (end.year - start.year) * 12 + (end.month - start.month) + 1

    return {
        "dataset": label,
        "rows": len(df),
        "start": start.date().isoformat(),
        "end": end.date().isoformat(),
        "months": months,
        "days": days,
    }


def coverage_block(data: Dict[str, pd.DataFrame]) -> str:
    out = h1("DATA COVERAGE")

    rows = [
        date_coverage_from_df(data["us_base_monthly"], "US base monthly"),
        date_coverage_from_df(data["selected_us_monthly"], "US selected hedge monthly"),
        date_coverage_from_df(data["uk_base_monthly"], "UK base A monthly"),
        date_coverage_from_df(data["uk_selected_monthly"], "UK selected hedge monthly"),
        date_coverage_from_df(data["us_base_daily_equity"], "US base daily equity"),
        date_coverage_from_df(data["us_selected_daily_equity"], "US selected daily equity"),
        date_coverage_from_df(data["uk_base_daily_equity"], "UK base daily equity"),
        date_coverage_from_df(data["uk_selected_daily_equity"], "UK selected daily equity"),
    ]

    out += table(pd.DataFrame(rows), 20)

    out += h2("Common monthly comparison ranges")
    comparisons = [
        ("US base vs UK base", data["us_base_monthly"], data["uk_base_monthly"]),
        ("US selected vs UK selected", data["selected_us_monthly"], data["uk_selected_monthly"]),
        ("US base vs US selected", data["us_base_monthly"], data["selected_us_monthly"]),
        ("UK base vs UK selected", data["uk_base_monthly"], data["uk_selected_monthly"]),
    ]

    common_rows = []
    for label, a, b in comparisons:
        common_rows.append(common_monthly_range(a, b, label))

    out += table(pd.DataFrame(common_rows), 20)
    return out


def common_monthly_range(a: pd.DataFrame, b: pd.DataFrame, label: str) -> Dict[str, Any]:
    if a.empty or b.empty or "date" not in a.columns or "date" not in b.columns:
        return {"comparison": label, "common_months": 0, "start": None, "end": None}

    aa = pd.to_datetime(a["date"], errors="coerce").dropna().dt.to_period("M")
    bb = pd.to_datetime(b["date"], errors="coerce").dropna().dt.to_period("M")

    common = sorted(set(aa) & set(bb))

    if not common:
        return {"comparison": label, "common_months": 0, "start": None, "end": None}

    return {
        "comparison": label,
        "common_months": len(common),
        "start": common[0].to_timestamp().date().isoformat(),
        "end": common[-1].to_timestamp().date().isoformat(),
    }


def data_quality_assessment(name: str, df: pd.DataFrame) -> str:
    out = h2(f"{name} data quality")

    if df.empty:
        out += "Brak raportu check_ranges.\n"
        return out

    if "status" not in df.columns:
        out += table(df, 30)
        return out

    status = df["status"].astype(str).str.upper()

    out += bullet("Tickery łącznie", len(df))
    out += bullet("Znalezione", int((status == "FOUND").sum()))
    out += bullet("Brakujące", int((status == "MISSING").sum()))
    out += bullet("Błędy", int((status == "ERROR").sum()))

    if {"date_from", "date_to"}.issubset(df.columns):
        valid = df[status == "FOUND"].copy()

        if not valid.empty:
            out += bullet("Najwcześniejszy start", valid["date_from"].dropna().min())
            out += bullet("Najpóźniejszy start", valid["date_from"].dropna().max())
            out += bullet("Najwcześniejszy koniec", valid["date_to"].dropna().min())
            out += bullet("Najpóźniejszy koniec", valid["date_to"].dropna().max())

            if "rows" in valid.columns:
                valid["rows_num"] = pd.to_numeric(valid["rows"], errors="coerce")
                shortest = valid.sort_values("rows_num", ascending=True).head(12)
                out += "\nNajkrótsze historie:\n"
                out += table(select_cols(shortest, ["ticker", "status", "date_from", "date_to", "rows", "file_path"]), 12)

    bad = df[status != "FOUND"].copy()

    if not bad.empty:
        out += "\nProblematyczne tickery:\n"
        out += table(select_cols(bad, ["ticker", "status", "date_from", "date_to", "rows", "error"]), 50)

    return out


# =========================
# JSON WEIGHTS
# =========================

def parse_weights_json(value: Any) -> Dict[str, float]:
    if pd.isna(value):
        return {}

    if isinstance(value, dict):
        return {str(k): float(v) for k, v in value.items()}

    text = str(value).strip()
    if not text:
        return {}

    try:
        obj = json.loads(text)
    except Exception:
        return {}

    if not isinstance(obj, dict):
        return {}

    out: Dict[str, float] = {}

    for k, v in obj.items():
        x = pd.to_numeric(v, errors="coerce")
        if pd.notna(x):
            out[str(k)] = float(x)

    return out


def summarize_weights(df: pd.DataFrame, label: str, json_col: str = "weights_used_json") -> str:
    out = h2(label)

    if df.empty:
        out += "Brak danych monthly.\n"
        return out

    if json_col not in df.columns:
        out += f"Brak kolumny {json_col}.\n"
        return out

    rows = []

    for _, r in df.iterrows():
        weights = parse_weights_json(r.get(json_col))
        date = r.get("date")

        for asset, weight in weights.items():
            rows.append({
                "date": date,
                "asset": asset,
                "weight": weight,
            })

    if not rows:
        out += "Nie udało się sparsować wag.\n"
        return out

    w = pd.DataFrame(rows)

    agg = (
        w.groupby("asset", as_index=False)
        .agg(
            months_present=("weight", lambda s: int((s > 1e-12).sum())),
            avg_weight=("weight", "mean"),
            max_weight=("weight", "max"),
        )
        .sort_values(["months_present", "avg_weight"], ascending=False)
    )

    out += "Ekspozycje wg wag monthly:\n"
    out += table(agg, 40)

    return out


def compare_us_uk_weights(us_df: pd.DataFrame, uk_df: pd.DataFrame, title: str) -> str:
    out = h2(title)

    if us_df.empty or uk_df.empty:
        out += "Brak US albo UK monthly.\n"
        return out

    if "date" not in us_df.columns or "date" not in uk_df.columns:
        out += "Brak kolumn date.\n"
        return out

    if "weights_used_json" not in us_df.columns or "weights_used_json" not in uk_df.columns:
        out += "Brak kolumn weights_used_json.\n"
        return out

    u = us_df[["date", "weights_used_json"]].copy()
    k = uk_df[["date", "weights_used_json"]].copy()

    u["date"] = pd.to_datetime(u["date"], errors="coerce")
    k["date"] = pd.to_datetime(k["date"], errors="coerce")

    u = u.dropna(subset=["date"])
    k = k.dropna(subset=["date"])

    merged = u.merge(k, on="date", how="inner", suffixes=("_us", "_uk"))

    if merged.empty:
        out += "Brak wspólnych miesięcy US/UK.\n"
        return out

    diffs = []

    for _, r in merged.iterrows():
        us_w = parse_weights_json(r["weights_used_json_us"])
        uk_w = parse_weights_json(r["weights_used_json_uk"])

        diffs.append({
            "date": r["date"],
            "us_assets": ",".join(sorted([a for a, w in us_w.items() if abs(w) > 1e-12])),
            "uk_assets": ",".join(sorted([a for a, w in uk_w.items() if abs(w) > 1e-12])),
            "us_asset_count": len([a for a, w in us_w.items() if abs(w) > 1e-12]),
            "uk_asset_count": len([a for a, w in uk_w.items() if abs(w) > 1e-12]),
            "us_cash_weight": us_w.get("_CASH", 0.0),
            "uk_cash_weight": uk_w.get("_CASH", 0.0),
        })

    d = pd.DataFrame(diffs)

    out += bullet("Wspólne miesiące", len(d))
    out += bullet("Średnia liczba aktywów US", fmt_num(d["us_asset_count"].mean()))
    out += bullet("Średnia liczba aktywów UK", fmt_num(d["uk_asset_count"].mean()))
    out += bullet("Miesiące z cash US > 0", int((d["us_cash_weight"] > 0).sum()))
    out += bullet("Miesiące z cash UK > 0", int((d["uk_cash_weight"] > 0).sum()))

    mismatch = d[
        (d["us_asset_count"] != d["uk_asset_count"])
        | ((d["us_cash_weight"] > 0) != (d["uk_cash_weight"] > 0))
    ].copy()

    out += bullet("Miesiące z różnicą liczby aktywów albo cash status", len(mismatch))

    if not mismatch.empty:
        out += "\nNajważniejsze mismatch months:\n"
        out += table(mismatch, 30)

    return out


# =========================
# RETURNS / CONSISTENCY
# =========================

def monthly_returns_from_monthly(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "date" not in df.columns:
        return pd.DataFrame()

    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"]).sort_values("date")

    ret_col = None
    for col in ["net_return", "return", "strategy_return", "gross_return", "portfolio_return"]:
        if col in d.columns:
            ret_col = col
            break

    if ret_col is None:
        return pd.DataFrame()

    d["return"] = pd.to_numeric(d[ret_col], errors="coerce")
    d = d.dropna(subset=["return"])
    return d[["date", "return"]]


def consistency_block(us_monthly: pd.DataFrame, uk_monthly: pd.DataFrame, title: str) -> str:
    out = h2(title)

    us_ret = monthly_returns_from_monthly(us_monthly)
    uk_ret = monthly_returns_from_monthly(uk_monthly)

    if us_ret.empty or uk_ret.empty:
        out += "Brak miesięcznych zwrotów US albo UK do porównania.\n"
        return out

    merged = us_ret.merge(uk_ret, on="date", how="inner", suffixes=("_us", "_uk"))

    if merged.empty:
        out += "Brak wspólnych miesięcy dla US i UK.\n"
        return out

    merged["diff"] = merged["return_uk"] - merged["return_us"]
    merged["abs_diff"] = merged["diff"].abs()

    corr = merged["return_us"].corr(merged["return_uk"])
    mae = merged["abs_diff"].mean()
    mean_diff = merged["diff"].mean()
    max_abs = merged["abs_diff"].max()

    out += bullet("Wspólne miesiące", len(merged))
    out += bullet("Korelacja monthly returns UK vs US", fmt_num(corr, 4))
    out += bullet("Średnia różnica UK - US monthly return", fmt_pp(mean_diff))
    out += bullet("MAE monthly return difference", fmt_pct(mae))
    out += bullet("Max abs monthly return difference", fmt_pct(max_abs))

    us_cum = (1 + merged["return_us"]).prod()
    uk_cum = (1 + merged["return_uk"]).prod()

    out += "\nNa wspólnym okresie:\n"
    out += bullet("US cumulative return", fmt_pct(us_cum - 1))
    out += bullet("UK cumulative return", fmt_pct(uk_cum - 1))
    out += bullet("UK/US cumulative ratio", fmt_num(uk_cum / us_cum if us_cum else None, 4))

    out += "\nNajwiększe rozjazdy miesięczne UK vs US:\n"
    out += table(merged.sort_values("abs_diff", ascending=False).head(20), 20)

    return out


# =========================
# NAMED PERIODS
# =========================

def named_periods_block(
    us_base: pd.DataFrame,
    uk_base: pd.DataFrame,
    us_selected: pd.DataFrame,
    uk_selected: pd.DataFrame,
) -> str:
    out = h1("NAMED PERIODS")

    out += h2("US base A named periods")
    out += table(clean_named(us_base), 50)

    out += h2("UK base A named periods")
    out += table(clean_named(uk_base), 50)

    out += h2("US selected hedge named periods")
    out += table(clean_named(us_selected), 50)

    out += h2("UK selected hedge named periods")
    out += table(clean_named(uk_selected), 50)

    out += h2("Named periods comparison: UK base A vs US base A")
    out += compare_named_periods(us_base, uk_base, "US_A", "UK_A")

    out += h2("Named periods comparison: UK selected hedge vs US selected hedge")
    out += compare_named_periods(us_selected, uk_selected, "US_SELECTED", "UK_SELECTED")

    out += h2("Named periods comparison: US selected hedge vs US base A")
    out += compare_named_periods(us_base, us_selected, "US_A", "US_SELECTED")

    out += h2("Named periods comparison: UK selected hedge vs UK base A")
    out += compare_named_periods(uk_base, uk_selected, "UK_A", "UK_SELECTED")

    return out


def clean_named(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    cols = [
        "period_name", "name", "period", "start", "end", "months",
        "total_return", "cagr", "max_drawdown", "maxdd", "calmar",
        "benchmark_total_return", "benchmark_cagr", "benchmark_max_drawdown",
        "cagr_vs_benchmark", "maxdd_vs_benchmark",
        "hit_rate_excess",
    ]

    return select_cols(df, cols)


def period_name_col(df: pd.DataFrame) -> Optional[str]:
    for col in ["period_name", "name", "period"]:
        if col in df.columns:
            return col
    return None


def compare_named_periods(a: pd.DataFrame, b: pd.DataFrame, a_label: str, b_label: str) -> str:
    if a.empty or b.empty:
        return "Brak danych named periods dla jednej ze stron.\n"

    ac = period_name_col(a)
    bc = period_name_col(b)

    if ac is None or bc is None:
        return "Brak kolumny period_name/name/period.\n"

    aa = a.copy()
    bb = b.copy()

    aa["__period"] = aa[ac].astype(str)
    bb["__period"] = bb[bc].astype(str)

    metric_cols = [
        "total_return",
        "cagr",
        "max_drawdown",
        "maxdd",
        "calmar",
        "benchmark_total_return",
        "benchmark_cagr",
        "benchmark_max_drawdown",
        "cagr_vs_benchmark",
        "maxdd_vs_benchmark",
    ]

    keep_a = ["__period"] + [c for c in metric_cols if c in aa.columns]
    keep_b = ["__period"] + [c for c in metric_cols if c in bb.columns]

    merged = aa[keep_a].merge(bb[keep_b], on="__period", how="inner", suffixes=(f"_{a_label}", f"_{b_label}"))

    if merged.empty:
        return "Brak wspólnych named periods.\n"

    for col in metric_cols:
        ca = f"{col}_{a_label}"
        cb = f"{col}_{b_label}"
        if ca in merged.columns and cb in merged.columns:
            merged[f"delta_{col}_{b_label}_minus_{a_label}"] = (
                pd.to_numeric(merged[cb], errors="coerce")
                - pd.to_numeric(merged[ca], errors="coerce")
            )

    return table(merged, 80, 24)


# =========================
# ROLLING / UNDERWATER / COSTS
# =========================

def rolling_assessment(title: str, rolling: pd.DataFrame, worst: pd.DataFrame) -> str:
    out = h2(title)

    if rolling.empty and worst.empty:
        out += "Brak rolling windows.\n"
        return out

    if not rolling.empty:
        out += "Podsumowanie okresów / rolling:\n"
        out += table(select_cols(rolling, [
            "strategy", "benchmark", "period_type", "period_name", "start", "end", "months",
            "cagr", "benchmark_cagr", "cagr_vs_benchmark",
            "max_drawdown", "benchmark_max_drawdown", "maxdd_vs_benchmark",
            "hit_rate_excess",
        ]), 30)

    if not worst.empty:
        out += "\nNajgorsze rolling windows wg CAGR vs benchmark:\n"

        if "cagr_vs_benchmark" in worst.columns:
            w = sort_numeric(worst, "cagr_vs_benchmark", ascending=True).head(15)
            out += table(select_cols(w, [
                "strategy", "window_months", "window_start", "window_end",
                "strategy_cagr", "benchmark_cagr", "cagr_vs_benchmark",
                "strategy_max_drawdown", "benchmark_max_drawdown", "maxdd_vs_benchmark",
                "strategy_final_equity", "benchmark_final_equity",
            ]), 15)
        else:
            out += table(worst, 15)

    return out


def underwater_assessment(title: str, df: pd.DataFrame) -> str:
    out = h2(title)

    if df.empty:
        out += "Brak underwater periods.\n"
        return out

    d = df.copy()

    if "max_drawdown" in d.columns:
        d["max_drawdown"] = pd.to_numeric(d["max_drawdown"], errors="coerce")
        d = d.sort_values("max_drawdown", ascending=True)

    out += "Najgorsze underwater periods:\n"
    out += table(select_cols(d, [
        "strategy", "benchmark", "series_type",
        "underwater_start", "underwater_bottom", "underwater_recovery",
        "duration_months", "months_to_bottom", "max_drawdown", "is_recovered",
    ]), 20)

    return out


def costs_holdings_block(title: str, trades: pd.DataFrame, holdings: pd.DataFrame, monthly: pd.DataFrame) -> str:
    out = h2(title)

    out += "\nTrades:\n"
    if trades.empty:
        out += "Brak trades.\n"
    else:
        out += bullet("Liczba wierszy trades", len(trades))
        for col in ["turnover", "trade_cost", "cost", "cost_amount", "tax_amount", "trade_value", "weight_change"]:
            if col in trades.columns:
                out += bullet(f"Suma {col}", fmt_num(pd.to_numeric(trades[col], errors="coerce").sum()))
        out += table(trades, 20)

    out += "\nHoldings:\n"
    if holdings.empty:
        out += "Brak holdings.\n"
    else:
        out += bullet("Liczba wierszy holdings", len(holdings))
        for col in ["asset", "ticker"]:
            if col in holdings.columns:
                out += "\nTop holdings:\n"
                out += holdings[col].astype(str).value_counts().head(30).to_string() + "\n"
                break

    out += "\nMonthly cost/tax:\n"
    if monthly.empty:
        out += "Brak replayed_monthly.\n"
    else:
        for col in ["turnover", "operations", "tax_amount", "tax_paid", "cost", "trade_cost", "transaction_cost"]:
            if col in monthly.columns:
                out += bullet(f"Suma {col}", fmt_num(pd.to_numeric(monthly[col], errors="coerce").sum()))

    return out


# =========================
# SELECTED / HEDGE SECTIONS
# =========================

def selected_variant_block(manifest: Dict[str, Any], selected_meta: Dict[str, Any]) -> str:
    out = h1("TESTED STRATEGY FROM CONFIG")

    selected = manifest.get("selected_hedge_variant", {})
    if not isinstance(selected, dict):
        selected = {}

    out += "To jest wariant strategii, który testujemy. Raport nie wybiera automatycznie zwycięzcy.\n\n"

    out += bullet("Base strategy", selected.get("base_strategy", "AUTO"))
    out += bullet("Hedge enabled", selected.get("enabled", "n/a"))
    out += bullet("Hedge asset US", selected.get("hedge_asset", "n/a"))
    out += bullet("Hedge weight", selected.get("hedge_weight", "n/a"))
    out += bullet("Rule", selected.get("rule", "n/a"))
    out += bullet("Lookback", selected.get("lookback", "n/a"))
    out += bullet("EMA span", selected.get("ema_span", "n/a"))
    out += bullet("Min hedge return", selected.get("min_hedge_return", "n/a"))
    out += bullet("Min spread vs A", selected.get("min_spread_vs_a", "n/a"))

    if selected_meta:
        out += "\nExport selected hedge metadata:\n"
        export = selected_meta.get("export", {})
        matched = selected_meta.get("matched_variant_row", {})

        out += bullet("Selected monthly rows", export.get("rows", "n/a"))
        out += bullet("Hedge active months", export.get("hedge_active_months", "n/a"))
        out += bullet("Hedge active % months", fmt_pct(export.get("hedge_active_pct_months")))
        out += bullet("Matched variant CAGR", fmt_pct(matched.get("cagr")))
        out += bullet("Matched variant MaxDD daily", fmt_pct(matched.get("maxdd_daily")))
        out += bullet("Matched variant Calmar", fmt_num(matched.get("calmar")))
        out += bullet("Matched variant final equity daily", fmt_num(matched.get("final_equity_daily")))
        out += bullet("Matched variant delta CAGR", fmt_pp(matched.get("delta_cagr")))
        out += bullet("Matched variant delta MaxDD daily", fmt_pp(matched.get("delta_maxdd_daily")))
        out += bullet("Matched variant delta Calmar", fmt_num(matched.get("delta_calmar")))

    return out


def hedge_context_block(summary: pd.DataFrame, relative: pd.DataFrame, ranked: pd.DataFrame) -> str:
    out = h1("US HEDGE CONTEXT - OTHER VARIANTS")

    if summary.empty and relative.empty and ranked.empty:
        out += "Brak danych z 05_us_hedge_overlay_all.\n"
        return out

    if not relative.empty:
        out += h2("Top variants by delta MaxDD daily")
        if "delta_maxdd_daily" in relative.columns:
            d = sort_numeric(relative, "delta_maxdd_daily", ascending=False)
            out += table(select_cols(d, [
                "hedge", "hedge_weight", "rule", "lookback", "ema_span",
                "delta_cagr", "delta_maxdd_daily", "delta_calmar", "delta_final_equity_daily",
            ]), 20)
        else:
            out += table(relative, 20)

    if not ranked.empty:
        out += h2("Top ranked hedge variants")
        out += table(select_cols(ranked, [
            "hedge", "hedge_weight", "rule", "lookback", "ema_span",
            "cagr", "delta_cagr", "maxdd_daily", "delta_maxdd_daily",
            "calmar", "delta_calmar", "final_equity_daily",
        ]), 20)

    return out


def selected_vs_base_block(summary: pd.DataFrame, relative: pd.DataFrame) -> str:
    out = h1("US SELECTED HEDGE VS PURE BASE A")

    if summary.empty and relative.empty:
        out += "Brak danych z 08_us_selected_vs_base.\n"
        return out

    if not relative.empty:
        out += h2("Relative selected hedge vs base")
        out += table(relative, 40)

    if not summary.empty:
        out += h2("Summary selected hedge / tested hedge candidates")
        out += table(summary, 40)

    return out


# =========================
# COMPACT TABLE
# =========================

def comparison_table_block(metrics: List[Metrics]) -> str:
    out = h1("COMPACT COMPARISON TABLE FOR FUTURE STRATEGY SELECTION")

    rows = []
    for m in metrics:
        rows.append({
            "scope": m.label,
            "final_equity": m.final_equity,
            "cagr": m.cagr,
            "maxdd": m.maxdd,
            "calmar": m.calmar,
            "benchmark_cagr": m.benchmark_cagr,
            "benchmark_maxdd": m.benchmark_maxdd,
            "cagr_vs_benchmark": m.cagr_vs_benchmark,
            "maxdd_vs_benchmark": m.maxdd_vs_benchmark,
        })

    d = pd.DataFrame(rows)

    display = d.copy()
    for col in ["cagr", "maxdd", "benchmark_cagr", "benchmark_maxdd", "cagr_vs_benchmark", "maxdd_vs_benchmark"]:
        if col in display.columns:
            display[col] = display[col].apply(fmt_pct)

    for col in ["final_equity", "calmar"]:
        if col in display.columns:
            display[col] = display[col].apply(fmt_num)

    out += table(display, 20)
    return out


# =========================
# BUILD REPORT
# =========================

def build_global_summary_txt(run_dir: Path, output_path: Path) -> None:
    paths, data, manifest = load_data(run_dir)
    selected_meta = safe_read_json(paths["selected_metadata"])

    us_base_monthly = extract_metrics(data["us_base_full"], "US base A monthly", "03_us_backtest_base/summary_full_period.csv")
    us_base_daily = extract_metrics(data["us_base_daily_summary"], "US base A daily", "04_us_daily_base/summary_daily_maxdd.csv")
    us_selected_daily = extract_metrics(data["us_selected_daily_summary"], "US selected hedge daily", "07_us_selected_daily_maxdd/summary_daily_maxdd.csv")

    uk_base_monthly = extract_metrics(data["uk_base_full"], "UK base A monthly", "11_uk_replay_base_A/summary_full_period.csv")
    uk_base_daily = extract_metrics(data["uk_base_daily_summary"], "UK base A daily", "12_uk_daily_base_A/summary_daily_maxdd.csv")

    uk_selected_monthly = extract_metrics(data["uk_selected_full"], "UK selected hedge monthly", "13_uk_replay_selected_hedge/summary_full_period.csv")
    uk_selected_daily = extract_metrics(data["uk_selected_daily_summary"], "UK selected hedge daily", "14_uk_daily_selected_hedge/summary_daily_maxdd.csv")

    parts: List[str] = []

    parts.append(
        "GLOBAL SUMMARY TXT\n"
        f"Generated at: {datetime.now().isoformat(timespec='seconds')}\n"
        f"Run dir: {run_dir}\n"
        f"Idea: {manifest.get('idea', 'n/a')}\n"
        f"Frequency: {manifest.get('frequency', 'n/a')}\n"
        f"US benchmark: {manifest.get('us_benchmark', 'n/a')}\n"
        f"UK benchmark: {manifest.get('uk_benchmark', 'n/a')}\n"
        "\n"
        "Cel raportu:\n"
        "- opisać jedną strategię zdefiniowaną w idea_config.json,\n"
        "- pokazać US base A,\n"
        "- pokazać US selected hedge vs base A,\n"
        "- pokazać UK replay base A,\n"
        "- pokazać UK replay selected hedge,\n"
        "- zmierzyć, czy mapping UK odtwarza US dla A i dla selected hedge,\n"
        "- pokazać named periods i coverage danych.\n"
        "\n"
        "Raport NIE wybiera automatycznie najlepszego wariantu.\n"
    )

    parts.append(selected_variant_block(manifest, selected_meta))
    parts.append(coverage_block(data))

    parts.append(h1("DATA QUALITY"))
    parts.append(data_quality_assessment("US", data["us_data_check"]))
    parts.append(data_quality_assessment("UK", data["uk_data_check"]))

    parts.append(h1("US BASE A"))
    parts.append(h2("US base A monthly metrics"))
    parts.append(metric_block(us_base_monthly))
    parts.append(h2("US base A daily metrics"))
    parts.append(metric_block(us_base_daily))
    parts.append(compare_metric_blocks("US base A daily vs monthly reconstruction check", us_base_daily, us_base_monthly, "US daily", "US monthly"))
    parts.append(rolling_assessment("US base A rolling robustness", data["us_base_rolling"], data["us_base_worst"]))
    parts.append(underwater_assessment("US base A underwater", data["us_base_underwater"]))

    parts.append(h1("US SELECTED HEDGE"))
    parts.append(h2("US selected hedge daily metrics"))
    parts.append(metric_block(us_selected_daily))
    parts.append(selected_vs_base_block(data["us_selected_vs_base_summary"], data["us_selected_vs_base_relative"]))
    parts.append(h2("US selected hedge daily vs US base A daily"))
    parts.append(compare_metric_blocks("US selected hedge daily vs US base A daily", us_selected_daily, us_base_daily, "US selected", "US base A"))
    parts.append(summarize_weights(data["selected_us_monthly"], "Selected US monthly exposure summary"))

    parts.append(hedge_context_block(data["us_hedge_summary"], data["us_hedge_relative"], data["us_hedge_ranked"]))

    parts.append(h1("UK REPLAY BASE A"))
    parts.append(h2("UK base A monthly metrics"))
    parts.append(metric_block(uk_base_monthly))
    parts.append(h2("UK base A daily metrics"))
    parts.append(metric_block(uk_base_daily))
    parts.append(compare_metric_blocks("UK base A daily vs monthly reconstruction check", uk_base_daily, uk_base_monthly, "UK daily", "UK monthly"))
    parts.append(rolling_assessment("UK base A rolling robustness", data["uk_base_rolling"], data["uk_base_worst"]))
    parts.append(underwater_assessment("UK base A underwater", data["uk_base_underwater"]))
    parts.append(summarize_weights(data["uk_base_monthly"], "UK base A exposure summary"))

    parts.append(h1("UK REPLAY SELECTED HEDGE"))
    parts.append(h2("UK selected hedge monthly metrics"))
    parts.append(metric_block(uk_selected_monthly))
    parts.append(h2("UK selected hedge daily metrics"))
    parts.append(metric_block(uk_selected_daily))
    parts.append(compare_metric_blocks("UK selected hedge daily vs monthly reconstruction check", uk_selected_daily, uk_selected_monthly, "UK daily", "UK monthly"))
    parts.append(compare_metric_blocks("UK selected hedge daily vs UK base A daily", uk_selected_daily, uk_base_daily, "UK selected", "UK base A"))
    parts.append(rolling_assessment("UK selected hedge rolling robustness", data["uk_selected_rolling"], data["uk_selected_worst"]))
    parts.append(underwater_assessment("UK selected hedge underwater", data["uk_selected_underwater"]))
    parts.append(summarize_weights(data["uk_selected_monthly"], "UK selected hedge exposure summary"))

    parts.append(h1("MAPPING CONSISTENCY"))
    parts.append(consistency_block(data["us_base_monthly"], data["uk_base_monthly"], "US base A vs UK base A monthly return consistency"))
    parts.append(consistency_block(data["selected_us_monthly"], data["uk_selected_monthly"], "US selected hedge vs UK selected hedge monthly return consistency"))
    parts.append(compare_us_uk_weights(data["us_base_monthly"], data["uk_base_monthly"], "US base A vs UK base A weights/mapping consistency"))
    parts.append(compare_us_uk_weights(data["selected_us_monthly"], data["uk_selected_monthly"], "US selected hedge vs UK selected hedge weights/mapping consistency"))

    parts.append(named_periods_block(
        us_base=data["us_base_named"],
        uk_base=data["uk_base_named"],
        us_selected=data["us_base_named"],
        uk_selected=data["uk_selected_named"],
    ))

    parts.append(h1("UK COSTS / HOLDINGS / TAX"))
    parts.append(costs_holdings_block("UK base A costs / holdings", data["uk_base_trades"], data["uk_base_holdings"], data["uk_base_monthly"]))
    parts.append(costs_holdings_block("UK selected hedge costs / holdings", data["uk_selected_trades"], data["uk_selected_holdings"], data["uk_selected_monthly"]))

    parts.append(h1("DAILY PERIOD MAXDD DETAILS"))
    parts.append(h2("US base A period daily MaxDD"))
    parts.append(table(select_cols(data["us_base_daily_periods"], [
        "strategy", "period_start", "period_end", "return_daily_rebuilt",
        "return_from_monthly_csv", "return_diff_vs_monthly_csv",
        "period_daily_maxdd", "period_min_equity",
    ]), 50))

    parts.append(h2("US selected hedge period daily MaxDD"))
    parts.append(table(select_cols(data["us_selected_daily_periods"], [
        "strategy", "period_start", "period_end", "return_daily_rebuilt",
        "return_from_monthly_csv", "return_diff_vs_monthly_csv",
        "period_daily_maxdd", "period_min_equity",
    ]), 50))

    parts.append(h2("UK base A period daily MaxDD"))
    parts.append(table(select_cols(data["uk_base_daily_periods"], [
        "strategy", "period_start", "period_end", "return_daily_rebuilt",
        "return_from_monthly_csv", "return_diff_vs_monthly_csv",
        "period_daily_maxdd", "period_min_equity",
    ]), 50))

    parts.append(h2("UK selected hedge period daily MaxDD"))
    parts.append(table(select_cols(data["uk_selected_daily_periods"], [
        "strategy", "period_start", "period_end", "return_daily_rebuilt",
        "return_from_monthly_csv", "return_diff_vs_monthly_csv",
        "period_daily_maxdd", "period_min_equity",
    ]), 50))

    parts.append(h1("RAW KEY PREVIEWS"))
    parts.append(h2("US base monthly preview"))
    parts.append(table(data["us_base_monthly"], 20))
    parts.append(h2("Selected US monthly preview"))
    parts.append(table(data["selected_us_monthly"], 20))
    parts.append(h2("UK base A monthly preview"))
    parts.append(table(data["uk_base_monthly"], 20))
    parts.append(h2("UK selected hedge monthly preview"))
    parts.append(table(data["uk_selected_monthly"], 20))

    parts.append(comparison_table_block([
        us_base_monthly,
        us_base_daily,
        us_selected_daily,
        uk_base_monthly,
        uk_base_daily,
        uk_selected_monthly,
        uk_selected_daily,
    ]))

    report = "".join(parts)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Buduje GLOBAL_SUMMARY.txt dla pipeline: US A, US selected hedge, UK A, UK selected hedge, named periods, coverage."
    )
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output", required=True)

    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    output_path = Path(args.output).resolve()

    if not run_dir.exists():
        raise FileNotFoundError(f"Run dir nie istnieje: {run_dir}")

    build_global_summary_txt(run_dir=run_dir, output_path=output_path)

    print(f"[OK] zapisano: {output_path}")


if __name__ == "__main__":
    main()