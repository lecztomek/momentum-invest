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


def table(df: pd.DataFrame, max_rows: int = 25, max_cols: int = 18) -> str:
    if df.empty:
        return "Brak danych.\n"

    d = df.head(max_rows).copy()

    if len(d.columns) > max_cols:
        d = d.iloc[:, :max_cols].copy()

    with pd.option_context(
        "display.max_columns", max_cols,
        "display.width", 260,
        "display.max_colwidth", 90,
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


def numeric_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[col], errors="coerce")


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
        "us_build": run_dir / "02_build_us_data" / "output",
        "us_backtest": run_dir / "03_us_backtest",
        "us_daily_base": run_dir / "04_us_daily_base",
        "us_hedge_overlay": run_dir / "05_us_hedge_overlay_all",
        "us_selected_export": run_dir / "06_us_selected_hedge_export",
        "us_uup_deep": run_dir / "07_us_uup_deep_dive",
        "us_selected_vs_base": run_dir / "08_us_selected_vs_base",

        "uk_data_check": run_dir / "09_check_uk_data" / "uk_data_check.csv",
        "uk_build": run_dir / "10_build_uk_data" / "output",
        "uk_replay_selected": run_dir / "11_uk_replay_selected_hedge",
        "uk_daily_selected": run_dir / "12_uk_selected_daily_maxdd",

        "us_base_full": run_dir / "03_us_backtest" / "summary_full_period.csv",
        "us_base_rolling": run_dir / "03_us_backtest" / "summary_rolling.csv",
        "us_base_worst": run_dir / "03_us_backtest" / "worst_rolling_windows.csv",
        "us_base_underwater": run_dir / "03_us_backtest" / "summary_underwater_periods.csv",
        "us_base_monthly": run_dir / "03_us_backtest" / "all_strategies_monthly.csv",

        "us_base_daily_summary": run_dir / "04_us_daily_base" / "summary_daily_maxdd.csv",
        "us_base_daily_periods": run_dir / "04_us_daily_base" / "period_daily_maxdd.csv",
        "us_base_daily_equity": run_dir / "04_us_daily_base" / "daily_equity_drawdown.csv",

        "selected_us_monthly": run_dir / "06_us_selected_hedge_export" / "selected_us_monthly.csv",
        "selected_metadata": run_dir / "06_us_selected_hedge_export" / "selected_hedge_metadata.json",

        "us_selected_vs_base_summary": run_dir / "08_us_selected_vs_base" / "hedge_vs_baseline_summary.csv",
        "us_selected_vs_base_relative": run_dir / "08_us_selected_vs_base" / "hedge_vs_baseline_relative.csv",

        "uk_selected_monthly": run_dir / "11_uk_replay_selected_hedge" / "replayed_monthly.csv",
        "uk_selected_full": run_dir / "11_uk_replay_selected_hedge" / "summary_full_period.csv",
        "uk_selected_rolling": run_dir / "11_uk_replay_selected_hedge" / "summary_rolling.csv",
        "uk_selected_worst": run_dir / "11_uk_replay_selected_hedge" / "worst_rolling_windows.csv",
        "uk_selected_underwater": run_dir / "11_uk_replay_selected_hedge" / "summary_underwater_periods.csv",
        "uk_selected_holdings": run_dir / "11_uk_replay_selected_hedge" / "replayed_holdings.csv",
        "uk_selected_trades": run_dir / "11_uk_replay_selected_hedge" / "replayed_trades.csv",

        "uk_selected_daily_summary": run_dir / "12_uk_selected_daily_maxdd" / "summary_daily_maxdd.csv",
        "uk_selected_daily_periods": run_dir / "12_uk_selected_daily_maxdd" / "period_daily_maxdd.csv",
        "uk_selected_daily_equity": run_dir / "12_uk_selected_daily_maxdd" / "daily_equity_drawdown.csv",
    }


def load_data(run_dir: Path) -> Tuple[Dict[str, Path], Dict[str, pd.DataFrame], Dict[str, Any]]:
    paths = discover_paths(run_dir)

    csv_keys = [
        "us_data_check",
        "uk_data_check",

        "us_base_full",
        "us_base_rolling",
        "us_base_worst",
        "us_base_underwater",
        "us_base_monthly",
        "us_base_daily_summary",
        "us_base_daily_periods",
        "us_base_daily_equity",

        "selected_us_monthly",
        "us_selected_vs_base_summary",
        "us_selected_vs_base_relative",

        "uk_selected_monthly",
        "uk_selected_full",
        "uk_selected_rolling",
        "uk_selected_worst",
        "uk_selected_underwater",
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
# JSON WEIGHTS ANALYSIS
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
    out += table(agg, 30)

    return out


def compare_us_uk_weights(us_df: pd.DataFrame, uk_df: pd.DataFrame) -> str:
    out = h2("US selected vs UK replay - porównanie ekspozycji miesięcznych")

    if us_df.empty or uk_df.empty:
        out += "Brak US selected monthly albo UK replay monthly.\n"
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
# DATA QUALITY
# =========================

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
# ROLLING / UNDERWATER
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
            w = sort_numeric(worst, "cagr_vs_benchmark", ascending=True).head(12)
            out += table(select_cols(w, [
                "strategy", "window_months", "window_start", "window_end",
                "strategy_cagr", "benchmark_cagr", "cagr_vs_benchmark",
                "strategy_max_drawdown", "benchmark_max_drawdown", "maxdd_vs_benchmark",
                "strategy_final_equity", "benchmark_final_equity",
            ]), 12)
        else:
            out += table(worst, 12)

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
    ]), 15)

    if "is_recovered" in d.columns:
        unrecovered = d[pd.to_numeric(d["is_recovered"], errors="coerce").fillna(1) == 0]
        if not unrecovered.empty:
            out += "\nNiezrecoverowane okresy:\n"
            out += table(unrecovered, 10)

    return out


# =========================
# SELECTED HEDGE
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


def hedge_context_block(hedge_dir: Path) -> str:
    out = h1("US HEDGE CONTEXT - OTHER VARIANTS")

    summary = safe_read_csv(hedge_dir / "monthly_active_hedge_daily_summary.csv")
    relative = safe_read_csv(hedge_dir / "monthly_active_hedge_daily_relative_vs_baseline.csv")
    ranked = safe_read_csv(hedge_dir / "monthly_active_hedge_daily_full_ranked.csv")

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
            ]), 15)
        else:
            out += table(relative, 15)

    if not ranked.empty:
        out += h2("Top ranked hedge variants")
        out += table(select_cols(ranked, [
            "hedge", "hedge_weight", "rule", "lookback", "ema_span",
            "cagr", "delta_cagr", "maxdd_daily", "delta_maxdd_daily",
            "calmar", "delta_calmar", "final_equity_daily",
        ]), 15)

    return out


def selected_vs_base_block(summary: pd.DataFrame, relative: pd.DataFrame) -> str:
    out = h1("US SELECTED HEDGE VS PURE BASE A")

    if summary.empty and relative.empty:
        out += "Brak danych z 08_us_selected_vs_base.\n"
        return out

    if not relative.empty:
        out += h2("Relative selected hedge vs base")
        out += table(select_cols(relative, [
            "hedge", "hedge_weight", "delta_cagr", "delta_maxdd", "delta_calmar",
            "delta_final_equity", "delta_total_return", "delta_vol_annualized",
        ]), 30)

    if not summary.empty:
        out += h2("Summary selected hedge / tested hedge candidates")
        out += table(select_cols(summary, [
            "strategy", "hedge", "hedge_weight", "cagr", "maxdd", "calmar",
            "final_equity", "total_return", "vol_annualized", "sharpe",
        ]), 30)

    return out


# =========================
# CONSISTENCY
# =========================

def returns_from_equity(df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    d = df.copy()

    if date_col not in d.columns:
        return pd.DataFrame()

    d[date_col] = pd.to_datetime(d[date_col], errors="coerce")
    d = d.dropna(subset=[date_col]).sort_values(date_col)

    equity_col = None
    for col in ["equity", "portfolio_equity", "equity_daily", "strategy_equity", "final_equity"]:
        if col in d.columns:
            equity_col = col
            break

    if equity_col is None:
        for col in d.columns:
            lc = col.lower()
            if "equity" in lc and "benchmark" not in lc:
                equity_col = col
                break

    if equity_col is None:
        return pd.DataFrame()

    d[equity_col] = pd.to_numeric(d[equity_col], errors="coerce")
    d = d.dropna(subset=[equity_col])

    if d.empty:
        return pd.DataFrame()

    d["return"] = d[equity_col].pct_change()
    return d[[date_col, "return", equity_col]].rename(columns={date_col: "date", equity_col: "equity"})


def monthly_returns_from_monthly(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "date" not in df.columns:
        return pd.DataFrame()

    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"]).sort_values("date")

    ret_col = None
    for col in ["net_return", "return", "strategy_return", "gross_return"]:
        if col in d.columns:
            ret_col = col
            break

    if ret_col is None:
        return pd.DataFrame()

    d["return"] = pd.to_numeric(d[ret_col], errors="coerce")
    d = d.dropna(subset=["return"])
    return d[["date", "return"]]


def consistency_block(us_selected_monthly: pd.DataFrame, uk_selected_monthly: pd.DataFrame) -> str:
    out = h1("MAPPING CONSISTENCY - US SELECTED VS UK REPLAY")

    us_ret = monthly_returns_from_monthly(us_selected_monthly)
    uk_ret = monthly_returns_from_monthly(uk_selected_monthly)

    if us_ret.empty or uk_ret.empty:
        out += "Brak miesięcznych zwrotów US selected albo UK replay do porównania.\n"
        return out

    merged = us_ret.merge(uk_ret, on="date", how="inner", suffixes=("_us", "_uk"))

    if merged.empty:
        out += "Brak wspólnych miesięcy dla US selected i UK replay.\n"
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

    out += "\nNajwiększe rozjazdy miesięczne UK vs US:\n"
    worst = merged.sort_values("abs_diff", ascending=False).head(15)
    out += table(worst, 15)

    us_cum = (1 + merged["return_us"]).prod()
    uk_cum = (1 + merged["return_uk"]).prod()

    out += "\nNa wspólnym okresie:\n"
    out += bullet("US cumulative return", fmt_pct(us_cum - 1))
    out += bullet("UK cumulative return", fmt_pct(uk_cum - 1))
    out += bullet("UK/US cumulative ratio", fmt_num(uk_cum / us_cum if us_cum else None, 4))

    return out


# =========================
# COSTS / HOLDINGS
# =========================

def costs_holdings_block(trades: pd.DataFrame, holdings: pd.DataFrame, monthly: pd.DataFrame) -> str:
    out = h1("UK REPLAY COSTS / HOLDINGS / TAX")

    out += h2("Trades")
    if trades.empty:
        out += "Brak trades.\n"
    else:
        out += bullet("Liczba wierszy trades", len(trades))
        for col in ["turnover", "trade_cost", "cost", "cost_amount", "tax_amount", "trade_value", "weight_change"]:
            if col in trades.columns:
                out += bullet(f"Suma {col}", fmt_num(pd.to_numeric(trades[col], errors="coerce").sum()))
        out += table(trades, 30)

    out += h2("Holdings")
    if holdings.empty:
        out += "Brak holdings.\n"
    else:
        out += bullet("Liczba wierszy holdings", len(holdings))
        for col in ["asset", "ticker"]:
            if col in holdings.columns:
                out += "\nTop holdings:\n"
                out += holdings[col].astype(str).value_counts().head(30).to_string() + "\n"
                break

    out += h2("Monthly cost/tax")
    if monthly.empty:
        out += "Brak replayed_monthly.\n"
    else:
        for col in ["turnover", "operations", "tax_amount", "tax_paid", "cost", "trade_cost", "transaction_cost"]:
            if col in monthly.columns:
                out += bullet(f"Suma {col}", fmt_num(pd.to_numeric(monthly[col], errors="coerce").sum()))

    return out


# =========================
# COMPARISON TABLE
# =========================

def comparison_table_block(us_base: Metrics, uk_selected: Metrics, uk_daily: Metrics) -> str:
    out = h1("COMPACT COMPARISON TABLE FOR FUTURE STRATEGY SELECTION")

    rows = [
        {
            "scope": "US base monthly",
            "final_equity": us_base.final_equity,
            "cagr": us_base.cagr,
            "maxdd": us_base.maxdd,
            "calmar": us_base.calmar,
            "benchmark_cagr": us_base.benchmark_cagr,
            "benchmark_maxdd": us_base.benchmark_maxdd,
            "cagr_vs_benchmark": us_base.cagr_vs_benchmark,
            "maxdd_vs_benchmark": us_base.maxdd_vs_benchmark,
        },
        {
            "scope": "UK selected monthly",
            "final_equity": uk_selected.final_equity,
            "cagr": uk_selected.cagr,
            "maxdd": uk_selected.maxdd,
            "calmar": uk_selected.calmar,
            "benchmark_cagr": uk_selected.benchmark_cagr,
            "benchmark_maxdd": uk_selected.benchmark_maxdd,
            "cagr_vs_benchmark": uk_selected.cagr_vs_benchmark,
            "maxdd_vs_benchmark": uk_selected.maxdd_vs_benchmark,
        },
        {
            "scope": "UK selected daily",
            "final_equity": uk_daily.final_equity,
            "cagr": uk_daily.cagr,
            "maxdd": uk_daily.maxdd,
            "calmar": uk_daily.calmar,
            "benchmark_cagr": uk_daily.benchmark_cagr,
            "benchmark_maxdd": uk_daily.benchmark_maxdd,
            "cagr_vs_benchmark": uk_daily.cagr_vs_benchmark,
            "maxdd_vs_benchmark": uk_daily.maxdd_vs_benchmark,
        },
    ]

    d = pd.DataFrame(rows)

    display = d.copy()
    for col in ["cagr", "maxdd", "benchmark_cagr", "benchmark_maxdd", "cagr_vs_benchmark", "maxdd_vs_benchmark"]:
        if col in display.columns:
            display[col] = display[col].apply(fmt_pct)

    for col in ["final_equity", "calmar"]:
        if col in display.columns:
            display[col] = display[col].apply(fmt_num)

    out += table(display, 10)

    return out


# =========================
# BUILD REPORT
# =========================

def build_global_summary_txt(run_dir: Path, output_path: Path) -> None:
    paths, data, manifest = load_data(run_dir)

    selected_meta = safe_read_json(paths["selected_metadata"])

    us_base_monthly = extract_metrics(
        data["us_base_full"],
        "US base monthly",
        "03_us_backtest/summary_full_period.csv",
    )

    us_base_daily = extract_metrics(
        data["us_base_daily_summary"],
        "US base daily",
        "04_us_daily_base/summary_daily_maxdd.csv",
    )

    uk_selected_monthly = extract_metrics(
        data["uk_selected_full"],
        "UK selected replay monthly",
        "11_uk_replay_selected_hedge/summary_full_period.csv",
    )

    uk_selected_daily = extract_metrics(
        data["uk_selected_daily_summary"],
        "UK selected replay daily",
        "12_uk_selected_daily_maxdd/summary_daily_maxdd.csv",
    )

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
        "- pokazać US base,\n"
        "- pokazać US selected hedge vs base,\n"
        "- zrobić UK replay dokładnie tego selected US wariantu,\n"
        "- zmierzyć, czy mapping UK odtwarza zachowanie US.\n"
        "\n"
        "Raport NIE wybiera automatycznie najlepszego wariantu.\n"
    )

    parts.append(selected_variant_block(manifest, selected_meta))

    parts.append(h1("DATA QUALITY"))
    parts.append(data_quality_assessment("US", data["us_data_check"]))
    parts.append(data_quality_assessment("UK", data["uk_data_check"]))

    parts.append(h1("US BASE STRATEGY"))
    parts.append(h2("US base monthly metrics"))
    parts.append(metric_block(us_base_monthly))

    parts.append(h2("US base daily metrics"))
    parts.append(metric_block(us_base_daily))

    parts.append(compare_metric_blocks(
        "US base daily vs monthly reconstruction check",
        us_base_daily,
        us_base_monthly,
        "US daily",
        "US monthly",
    ))

    parts.append(rolling_assessment(
        "US base rolling robustness",
        data["us_base_rolling"],
        data["us_base_worst"],
    ))

    parts.append(underwater_assessment(
        "US base underwater",
        data["us_base_underwater"],
    ))

    parts.append(hedge_context_block(paths["us_hedge_overlay"]))

    parts.append(selected_vs_base_block(
        data["us_selected_vs_base_summary"],
        data["us_selected_vs_base_relative"],
    ))

    parts.append(h1("SELECTED US MONTHLY WEIGHTS"))
    parts.append(summarize_weights(
        data["selected_us_monthly"],
        "Selected US monthly exposure summary",
    ))

    parts.append(h1("UK REPLAY OF SELECTED US STRATEGY"))
    parts.append(h2("UK selected monthly replay metrics"))
    parts.append(metric_block(uk_selected_monthly))

    parts.append(h2("UK selected daily replay metrics"))
    parts.append(metric_block(uk_selected_daily))

    parts.append(compare_metric_blocks(
        "UK selected daily vs monthly reconstruction check",
        uk_selected_daily,
        uk_selected_monthly,
        "UK daily",
        "UK monthly",
    ))

    parts.append(rolling_assessment(
        "UK selected rolling robustness",
        data["uk_selected_rolling"],
        data["uk_selected_worst"],
    ))

    parts.append(underwater_assessment(
        "UK selected underwater",
        data["uk_selected_underwater"],
    ))

    parts.append(summarize_weights(
        data["uk_selected_monthly"],
        "UK replay monthly exposure summary",
    ))

    parts.append(consistency_block(
        data["selected_us_monthly"],
        data["uk_selected_monthly"],
    ))

    parts.append(compare_us_uk_weights(
        data["selected_us_monthly"],
        data["uk_selected_monthly"],
    ))

    parts.append(costs_holdings_block(
        trades=data["uk_selected_trades"],
        holdings=data["uk_selected_holdings"],
        monthly=data["uk_selected_monthly"],
    ))

    parts.append(h1("DAILY PERIOD MAXDD DETAILS"))
    parts.append(h2("US base period daily MaxDD"))
    parts.append(table(select_cols(data["us_base_daily_periods"], [
        "strategy", "period_start", "period_end", "return_daily_rebuilt",
        "return_from_monthly_csv", "return_diff_vs_monthly_csv",
        "period_daily_maxdd", "period_min_equity",
    ]), 40))

    parts.append(h2("UK selected period daily MaxDD"))
    parts.append(table(select_cols(data["uk_selected_daily_periods"], [
        "strategy", "period_start", "period_end", "return_daily_rebuilt",
        "return_from_monthly_csv", "return_diff_vs_monthly_csv",
        "period_daily_maxdd", "period_min_equity",
    ]), 40))

    parts.append(h1("RAW KEY PREVIEWS"))
    parts.append(h2("Selected US monthly preview"))
    parts.append(table(data["selected_us_monthly"], 25))

    parts.append(h2("UK replay selected monthly preview"))
    parts.append(table(data["uk_selected_monthly"], 25))

    parts.append(comparison_table_block(
        us_base=us_base_monthly,
        uk_selected=uk_selected_monthly,
        uk_daily=uk_selected_daily,
    ))

    report = "".join(parts)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")


# =========================
# CLI
# =========================

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Buduje GLOBAL_SUMMARY.txt dla pipeline: "
            "US base -> selected US hedge -> UK replay selected hedge -> mapping consistency."
        )
    )

    parser.add_argument(
        "--run-dir",
        required=True,
        help="Folder runu, np. ideas_out/best17_3m/runs/20260703_140000",
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Ścieżka do GLOBAL_SUMMARY.txt",
    )

    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    output_path = Path(args.output).resolve()

    if not run_dir.exists():
        raise FileNotFoundError(f"Run dir nie istnieje: {run_dir}")

    build_global_summary_txt(run_dir=run_dir, output_path=output_path)

    print(f"[OK] zapisano: {output_path}")


if __name__ == "__main__":
    main()