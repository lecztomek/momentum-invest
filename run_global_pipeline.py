from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


ROOT = Path(__file__).resolve().parent
ENGINE = ROOT / "engine"
IDEAS = ROOT / "ideas"
IDEAS_OUT = ROOT / "ideas_out"


# =========================
# BASIC HELPERS
# =========================

def now_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def run_cmd(cmd: List[str], cwd: Path, log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    with log_file.open("w", encoding="utf-8") as log:
        log.write("COMMAND:\n")
        log.write(" ".join(cmd))
        log.write("\n\n")
        log.flush()

        process = subprocess.run(
            cmd,
            cwd=str(cwd),
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

    if process.returncode != 0:
        print()
        print("=" * 100)
        print("PIPELINE STEP FAILED")
        print("=" * 100)
        print(f"Log file: {log_file}")
        print()
        print("Last log lines:")
        print("-" * 100)

        try:
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in lines[-160:]:
                print(line)
        except Exception as e:
            print(f"Nie udało się odczytać loga: {e}")

        print("-" * 100)
        print()

        raise RuntimeError(f"Command failed. Log: {log_file}")


def file_exists(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def step_done(step_dir: Path, required_files: List[Path], force: bool) -> bool:
    if force:
        return False

    done_file = step_dir / "_DONE.json"

    if not file_exists(done_file):
        return False

    return all(file_exists(p) for p in required_files)


def mark_done(step_dir: Path, meta: Dict[str, Any]) -> None:
    meta = dict(meta)
    meta["done_at"] = datetime.now().isoformat(timespec="seconds")
    write_json(step_dir / "_DONE.json", meta)


def copy_if_exists(src: Path, dst: Path) -> None:
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def list_arg(values: List[Any]) -> List[str]:
    return [str(v) for v in values]


# =========================
# CONFIG HELPERS
# =========================

def load_idea(idea_name: str) -> tuple[Path, Dict[str, Any]]:
    idea_dir = IDEAS / idea_name
    config_path = idea_dir / "idea_config.json"

    if not config_path.exists():
        raise FileNotFoundError(f"Brak idea_config.json: {config_path}")

    cfg = read_json(config_path)
    return idea_dir, cfg


def resolve_idea_path(idea_dir: Path, raw: str) -> Path:
    path = Path(raw)

    if path.is_absolute():
        return path

    candidate = idea_dir / path

    if candidate.exists():
        return candidate.resolve()

    return (ROOT / path).resolve()


def make_run_dir(idea_name: str, requested_run: Optional[str]) -> Path:
    idea_out = IDEAS_OUT / idea_name
    runs_dir = idea_out / "runs"
    ensure_dir(runs_dir)

    if requested_run:
        run_dir = Path(requested_run)
        if not run_dir.is_absolute():
            run_dir = ROOT / run_dir
        ensure_dir(run_dir)
        return run_dir.resolve()

    run_dir = runs_dir / now_run_id()
    ensure_dir(run_dir)
    return run_dir.resolve()


def cfg_list(cfg: Dict[str, Any], key: str, default: List[Any]) -> List[Any]:
    value = cfg.get(key, default)

    if value is None:
        return default

    if isinstance(value, list):
        return value

    return [value]


def resolve_strategy_name(
    requested: Any,
    daily_equity_file: Path,
    role: str,
) -> str:
    auto_values = {"", "AUTO", "__AUTO__", "A", "COMBINED"}

    if requested is not None:
        requested_str = str(requested).strip()
        if requested_str.upper() not in auto_values:
            return requested_str

    df = pd.read_csv(daily_equity_file, usecols=["strategy"])
    strategies = sorted(df["strategy"].astype(str).dropna().unique())

    if len(strategies) == 1:
        return strategies[0]

    raise ValueError(
        f"Nie mogę automatycznie wybrać {role}, bo jest więcej niż jedna strategia. "
        f"Dostępne: {strategies}. Ustaw w idea_config.json: {role}"
    )


# =========================
# HYBRID CONFIG PATCHING
# =========================

def patch_hybrid_config(
    source_config: Path,
    target_config: Path,
    us_build_output: Path,
) -> None:
    cfg = read_json(source_config)

    def patch_file_map(obj: Dict[str, str]) -> Dict[str, str]:
        out: Dict[str, str] = {}

        for name, raw_path in obj.items():
            original = Path(raw_path)
            out[name] = str((us_build_output / original.name).resolve())

        return out

    if "score_files" in cfg:
        cfg["score_files"] = patch_file_map(cfg["score_files"])

    if "signal_files" in cfg:
        cfg["signal_files"] = patch_file_map(cfg["signal_files"])

    if "returns_file" in cfg:
        cfg["returns_file"] = str(
            (us_build_output / Path(cfg["returns_file"]).name).resolve()
        )

    target_config.parent.mkdir(parents=True, exist_ok=True)
    write_json(target_config, cfg)


# =========================
# OUTPUT DISCOVERY
# =========================

def find_monthly_replay_files(backtest_dir: Path) -> List[Path]:
    candidates: List[Path] = []

    for path in backtest_dir.rglob("*.csv"):
        try:
            header = pd.read_csv(path, nrows=0).columns
        except Exception:
            continue

        cols = set(str(c) for c in header)

        if {"date", "weights_used_json"}.issubset(cols):
            candidates.append(path)

    def score(path: Path) -> tuple[int, str]:
        name = path.name.lower()
        points = 0

        if "all_strategies_monthly" in name:
            points -= 100
        if "combined" in name:
            points -= 80
        if "monthly" in name:
            points -= 20

        return points, str(path)

    return sorted(candidates, key=score)


def select_source_monthly(
    cfg: Dict[str, Any],
    backtest_dir: Path,
) -> Path:
    explicit = cfg.get("source_monthly_file")

    if explicit:
        p = Path(explicit)

        if not p.is_absolute():
            p = ROOT / p

        if not p.exists():
            raise FileNotFoundError(f"source_monthly_file nie istnieje: {p}")

        return p.resolve()

    candidates = find_monthly_replay_files(backtest_dir)

    if not candidates:
        raise FileNotFoundError(
            f"Nie znalazłem monthly replay z kolumną weights_used_json w: {backtest_dir}"
        )

    return candidates[0].resolve()


# =========================
# SELECTED HEDGE CONFIG
# =========================

def get_selected_hedge_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
    selected = cfg.get("selected_hedge_variant", {})

    if not isinstance(selected, dict):
        return {"enabled": False}

    out = dict(selected)
    out["enabled"] = bool(out.get("enabled", False))

    return out


def selected_hedge_enabled(cfg: Dict[str, Any]) -> bool:
    return bool(get_selected_hedge_cfg(cfg).get("enabled", False))


def build_selected_hedge_args(selected: Dict[str, Any]) -> List[str]:
    args: List[str] = []

    if selected.get("hedge_asset"):
        args += ["--hedge-asset", str(selected["hedge_asset"])]

    if selected.get("hedge_weight") is not None:
        args += ["--hedge-weight", str(selected["hedge_weight"])]

    if selected.get("rule"):
        args += ["--rule", str(selected["rule"])]

    if selected.get("lookback") is not None:
        args += ["--lookback", str(selected["lookback"])]

    if selected.get("ema_span") is not None:
        args += ["--ema-span", str(selected["ema_span"])]

    if selected.get("min_hedge_return") is not None:
        args += ["--min-hedge-return", str(selected["min_hedge_return"])]

    if selected.get("min_spread_vs_a") is not None:
        args += ["--min-spread-vs-a", str(selected["min_spread_vs_a"])]

    return args


# =========================
# HEDGE COMMANDS
# =========================

def run_us_hedge_overlay_all(
    step_dir: Path,
    daily_equity_all: Path,
    daily_close: Path,
    cfg: Dict[str, Any],
    force: bool,
) -> None:
    required = [
        step_dir / "monthly_active_hedge_daily_summary.csv",
        step_dir / "monthly_active_hedge_daily_relative_vs_baseline.csv",
    ]

    if step_done(step_dir, required, force):
        print("[SKIP] 05_us_hedge_overlay_all")
        return

    print("[RUN ] 05_us_hedge_overlay_all")
    ensure_dir(step_dir)

    hedge_cfg = cfg.get("hedges", {}).get("us", {})
    if not isinstance(hedge_cfg, dict):
        hedge_cfg = {}

    selected = get_selected_hedge_cfg(cfg)

    hedge_assets = cfg_list(
        hedge_cfg,
        "hedge_assets",
        [selected["hedge_asset"]] if selected.get("hedge_asset") else [],
    )

    if not hedge_assets:
        raise ValueError("Brak hedge_assets. Ustaw hedges.us.hedge_assets albo selected_hedge_variant.hedge_asset.")

    a_strategy = resolve_strategy_name(
        hedge_cfg.get("a_strategy", "AUTO"),
        daily_equity_all,
        "hedges.us.a_strategy",
    )

    baseline_strategy = resolve_strategy_name(
        hedge_cfg.get("baseline_strategy", "AUTO"),
        daily_equity_all,
        "hedges.us.baseline_strategy",
    )

    cmd = [
        sys.executable,
        str(ENGINE / "monthly_hedge_momentum_overlay.py"),
        "--daily-equity-all",
        str(daily_equity_all),
        "--daily-close",
        str(daily_close),
        "--a-strategy",
        a_strategy,
        "--baseline-strategy",
        baseline_strategy,
        "--hedges",
        *list_arg(hedge_assets),
        "--hedge-weights",
        *list_arg(cfg_list(
            hedge_cfg,
            "hedge_weights",
            [selected.get("hedge_weight", 0.20)],
        )),
        "--rules",
        *list_arg(cfg_list(
            hedge_cfg,
            "rules",
            [selected.get("rule", "hedge_positive_and_beats_a")],
        )),
        "--lookbacks",
        *list_arg(cfg_list(
            hedge_cfg,
            "lookbacks",
            [selected.get("lookback", 1)],
        )),
        "--ema-spans",
        *list_arg(cfg_list(
            hedge_cfg,
            "ema_spans",
            [selected.get("ema_span", 3) if selected.get("ema_span") is not None else 3],
        )),
        "--min-hedge-returns",
        *list_arg(cfg_list(
            hedge_cfg,
            "min_hedge_returns",
            [selected.get("min_hedge_return", 0.0)],
        )),
        "--min-spreads-vs-a",
        *list_arg(cfg_list(
            hedge_cfg,
            "min_spreads_vs_a",
            [selected.get("min_spread_vs_a", 0.0)],
        )),
        "--rolling-day-windows",
        *list_arg(cfg_list(hedge_cfg, "rolling_day_windows", [21, 63, 126, 252])),
        "--rolling-month-windows",
        *list_arg(cfg_list(hedge_cfg, "rolling_month_windows", [3, 6, 12])),
        "--save-daily-detail-top-n",
        str(hedge_cfg.get("save_daily_detail_top_n", 30)),
        "--output-dir",
        str(step_dir),
    ]

    run_cmd(cmd, cwd=ROOT, log_file=step_dir / "run.log")
    mark_done(step_dir, {"step": "us_hedge_overlay_all"})


def export_selected_hedge_variant(
    step_dir: Path,
    source_monthly: Path,
    hedge_overlay_dir: Path,
    daily_equity_all: Path,
    cfg: Dict[str, Any],
    force: bool,
) -> Path:
    selected_monthly = step_dir / "selected_us_monthly.csv"
    selected_meta = step_dir / "selected_hedge_metadata.json"

    required = [selected_monthly, selected_meta]

    if step_done(step_dir, required, force):
        print("[SKIP] 06_us_selected_hedge_export")
        return selected_monthly

    print("[RUN ] 06_us_selected_hedge_export")
    ensure_dir(step_dir)

    selected = get_selected_hedge_cfg(cfg)

    if not selected.get("enabled"):
        shutil.copy2(source_monthly, selected_monthly)
        write_json(
            selected_meta,
            {
                "enabled": False,
                "source": str(source_monthly),
                "note": "selected_hedge_variant disabled, copied base US monthly.",
            },
        )
        mark_done(step_dir, {"step": "us_selected_hedge_export", "enabled": False})
        return selected_monthly

    cmd = [
        sys.executable,
        str(ENGINE / "export_selected_hedge_variant.py"),
        "--base-monthly",
        str(source_monthly),
        "--hedge-overlay-dir",
        str(hedge_overlay_dir),
        "--daily-equity-all",
        str(daily_equity_all),
        "--output-monthly",
        str(selected_monthly),
        "--output-metadata",
        str(selected_meta),
        *build_selected_hedge_args(selected),
    ]

    run_cmd(cmd, cwd=ROOT, log_file=step_dir / "run.log")
    mark_done(step_dir, {"step": "us_selected_hedge_export", "enabled": True})

    return selected_monthly


def run_hedge_vs_baseline(
    step_dir: Path,
    daily_equity_all: Path,
    daily_close: Path,
    cfg: Dict[str, Any],
    force: bool,
) -> None:
    required = [
        step_dir / "hedge_vs_baseline_summary.csv",
        step_dir / "hedge_vs_baseline_relative.csv",
    ]

    if step_done(step_dir, required, force):
        print("[SKIP] 08_us_selected_vs_base")
        return

    print("[RUN ] 08_us_selected_vs_base")
    ensure_dir(step_dir)

    hedge_cfg = cfg.get("hedges", {}).get("us", {})
    if not isinstance(hedge_cfg, dict):
        hedge_cfg = {}

    selected = get_selected_hedge_cfg(cfg)

    hedge_assets = [selected["hedge_asset"]] if selected.get("hedge_asset") else cfg_list(hedge_cfg, "hedge_assets", [])
    hedge_weights = [selected["hedge_weight"]] if selected.get("hedge_weight") is not None else cfg_list(hedge_cfg, "hedge_weights", [0.20])

    if not hedge_assets:
        raise ValueError("Brak selected_hedge_variant.hedge_asset albo hedges.us.hedge_assets.")

    a_strategy = resolve_strategy_name(
        hedge_cfg.get("a_strategy", "AUTO"),
        daily_equity_all,
        "hedges.us.a_strategy",
    )

    baseline_strategy = resolve_strategy_name(
        hedge_cfg.get("baseline_strategy", "AUTO"),
        daily_equity_all,
        "hedges.us.baseline_strategy",
    )

    cmd = [
        sys.executable,
        str(ENGINE / "compare_hedges_vs_current_baseline.py"),
        "--daily-equity-all",
        str(daily_equity_all),
        "--daily-close",
        str(daily_close),
        "--a-strategy",
        a_strategy,
        "--baseline-strategy",
        baseline_strategy,
        "--hedges",
        *list_arg(hedge_assets),
        "--hedge-weights",
        *list_arg(hedge_weights),
        "--output-dir",
        str(step_dir),
    ]

    run_cmd(cmd, cwd=ROOT, log_file=step_dir / "run.log")
    mark_done(step_dir, {"step": "us_selected_vs_base"})


def run_uup_deep_dive_if_enabled(
    step_dir: Path,
    daily_equity_all: Path,
    daily_close: Path,
    cfg: Dict[str, Any],
    force: bool,
) -> None:
    marker = step_dir / "uup_deep_dive_done.marker"

    if step_done(step_dir, [marker], force):
        print("[SKIP] 07_us_uup_deep_dive")
        return

    hedge_cfg = cfg.get("hedges", {}).get("us", {})
    if not isinstance(hedge_cfg, dict):
        hedge_cfg = {}

    if not bool(hedge_cfg.get("run_uup_deep_dive", False)):
        print("[SKIP] 07_us_uup_deep_dive disabled")
        ensure_dir(step_dir)
        marker.write_text("disabled\n", encoding="utf-8")
        mark_done(step_dir, {"step": "us_uup_deep_dive", "disabled": True})
        return

    print("[RUN ] 07_us_uup_deep_dive")
    ensure_dir(step_dir)

    a_strategy = resolve_strategy_name(
        hedge_cfg.get("a_strategy", "AUTO"),
        daily_equity_all,
        "hedges.us.a_strategy",
    )

    baseline_strategy = resolve_strategy_name(
        hedge_cfg.get("baseline_strategy", "AUTO"),
        daily_equity_all,
        "hedges.us.baseline_strategy",
    )

    cmd = [
        sys.executable,
        str(ENGINE / "deep_dive_active_uup20.py"),
        "--daily-equity-all",
        str(daily_equity_all),
        "--daily-close",
        str(daily_close),
        "--a-strategy",
        a_strategy,
        "--baseline-strategy",
        baseline_strategy,
        "--uup-ticker",
        str(hedge_cfg.get("uup_ticker", "uup.us")),
        "--thresholds",
        *list_arg(cfg_list(hedge_cfg, "uup_thresholds", [0.0, 0.0025, 0.005, 0.01])),
        "--weights",
        *list_arg(cfg_list(hedge_cfg, "uup_weights", [0.05, 0.10, 0.15, 0.20, 0.25, 0.30])),
        "--cost-bps",
        *list_arg(cfg_list(hedge_cfg, "uup_cost_bps", [0.0, 5.0, 10.0, 20.0])),
        "--rolling-day-windows",
        *list_arg(cfg_list(hedge_cfg, "rolling_day_windows", [21, 63, 126, 252])),
        "--rolling-month-windows",
        *list_arg(cfg_list(hedge_cfg, "deep_dive_rolling_month_windows", [3, 6, 12, 24, 36, 48, 60, 84, 120, 180])),
        "--group-assets",
        *list_arg(cfg_list(hedge_cfg, "group_assets", ["xlk.us", "ivv.us", "dbc.us", "iau.us"])),
        "--output-dir",
        str(step_dir),
    ]

    run_cmd(cmd, cwd=ROOT, log_file=step_dir / "run.log")
    marker.write_text("done\n", encoding="utf-8")
    mark_done(step_dir, {"step": "us_uup_deep_dive"})


# =========================
# PIPELINE
# =========================

def run_pipeline(
    idea_name: str,
    force: bool,
    requested_run: Optional[str],
) -> None:
    idea_dir, cfg = load_idea(idea_name)
    run_dir = make_run_dir(idea_name, requested_run)

    idea_out = IDEAS_OUT / idea_name
    ensure_dir(idea_out)

    print(f"IDEA: {idea_name}")
    print(f"RUN:  {rel(run_dir)}")

    frequency = str(cfg.get("frequency", "monthly"))

    us_data_dir = resolve_idea_path(idea_dir, cfg.get("us_data_dir", "data/us"))
    uk_data_dir = resolve_idea_path(idea_dir, cfg.get("uk_data_dir", "data/uk"))

    us_tickers = resolve_idea_path(idea_dir, cfg.get("us_tickers_file", "tickers_us.txt"))
    uk_tickers = resolve_idea_path(idea_dir, cfg.get("uk_tickers_file", "tickers_uk.txt"))

    hybrid_config = resolve_idea_path(idea_dir, cfg.get("hybrid_config_file", "hybrid_config.json"))
    mapping_file = resolve_idea_path(idea_dir, cfg.get("ticker_mapping_file", "ticker_mapping.json"))

    us_benchmark = str(cfg.get("us_benchmark", "vt.us"))
    uk_benchmark = str(cfg.get("uk_benchmark", "vwra.uk"))

    transaction_cost = float(cfg.get("transaction_cost_bps_one_way", 40.0))
    annual_tax = float(cfg.get("annual_tax_rate", 0.19))

    s01 = run_dir / "01_check_us_data"
    s02 = run_dir / "02_build_us_data"
    s03 = run_dir / "03_us_backtest"
    s04 = run_dir / "04_us_daily_base"

    s05 = run_dir / "05_us_hedge_overlay_all"
    s06 = run_dir / "06_us_selected_hedge_export"
    s07 = run_dir / "07_us_uup_deep_dive"
    s08 = run_dir / "08_us_selected_vs_base"

    s09 = run_dir / "09_check_uk_data"
    s10 = run_dir / "10_build_uk_data"
    s11 = run_dir / "11_uk_replay_selected_hedge"
    s12 = run_dir / "12_uk_selected_daily_maxdd"

    s13 = run_dir / "13_global_summary"

    us_check_csv = s01 / "us_data_check.csv"
    uk_check_csv = s09 / "uk_data_check.csv"

    us_build_out = s02 / "output"
    uk_build_out = s10 / "output"

    us_daily_close = us_build_out / "daily_close.csv"
    uk_daily_close = uk_build_out / "daily_close.csv"

    returns_name = (
        "month_start_to_month_start_returns.csv"
        if frequency == "monthly"
        else "week_start_to_week_start_returns.csv"
    )

    us_returns = us_build_out / returns_name
    uk_returns = uk_build_out / returns_name

    patched_hybrid_config = s03 / "hybrid_config_patched.json"

    us_daily_summary = s04 / "summary_daily_maxdd.csv"
    us_daily_equity_all = s04 / "daily_equity_drawdown.csv"

    selected_us_monthly = s06 / "selected_us_monthly.csv"

    us_selected_daily_summary = s12 / "__placeholder_not_used__.csv"

    uk_replayed_monthly = s11 / "replayed_monthly.csv"
    uk_daily_summary = s12 / "summary_daily_maxdd.csv"
    uk_daily_equity_all = s12 / "daily_equity_drawdown.csv"

    global_summary_run = s13 / "GLOBAL_SUMMARY.txt"
    global_summary_final = idea_out / "GLOBAL_SUMMARY.txt"

    # ---------- 01 check US data
    if step_done(s01, [us_check_csv], force):
        print("[SKIP] 01_check_us_data")
    else:
        print("[RUN ] 01_check_us_data")
        ensure_dir(s01)
        run_cmd(
            [
                sys.executable,
                str(ENGINE / "check_ranges.py"),
                "--base-dir",
                str(us_data_dir),
                "--tickers-file",
                str(us_tickers),
                "--output-csv",
                str(us_check_csv),
            ],
            cwd=ROOT,
            log_file=s01 / "run.log",
        )
        mark_done(s01, {"step": "check_us_data"})

    # ---------- 02 build US data
    required_us_build = [
        us_daily_close,
        us_returns,
        us_build_out / "resolved_files.csv",
    ]

    if step_done(s02, required_us_build, force):
        print("[SKIP] 02_build_us_data")
    else:
        print("[RUN ] 02_build_us_data")
        ensure_dir(s02)
        run_cmd(
            [
                sys.executable,
                str(ENGINE / "build_data.py"),
                "--base-dir",
                str(us_data_dir),
                "--tickers-file",
                str(us_tickers),
                "--output-dir",
                str(us_build_out),
                "--frequency",
                frequency,
            ],
            cwd=ROOT,
            log_file=s02 / "run.log",
        )
        mark_done(s02, {"step": "build_us_data"})

    # ---------- 03 US base backtest
    required_us_backtest = [
        patched_hybrid_config,
        s03 / "summary_full_period.csv",
    ]

    if step_done(s03, required_us_backtest, force):
        print("[SKIP] 03_us_backtest")
    else:
        print("[RUN ] 03_us_backtest")
        ensure_dir(s03)

        patch_hybrid_config(
            source_config=hybrid_config,
            target_config=patched_hybrid_config,
            us_build_output=us_build_out,
        )

        run_cmd(
            [
                sys.executable,
                str(ENGINE / "backtest_hybrid_search.py"),
                "--config",
                str(patched_hybrid_config),
                "--out-dir",
                str(s03),
            ],
            cwd=ROOT,
            log_file=s03 / "run.log",
        )
        mark_done(s03, {"step": "us_backtest"})

    source_monthly_base = select_source_monthly(cfg, s03)
    print(f"US base monthly source: {rel(source_monthly_base)}")

    # ---------- 04 US daily base
    if step_done(s04, [us_daily_summary, us_daily_equity_all], force):
        print("[SKIP] 04_us_daily_base")
    else:
        print("[RUN ] 04_us_daily_base")
        ensure_dir(s04)
        run_cmd(
            [
                sys.executable,
                str(ENGINE / "daily_maxdd_from_monthly_weights.py"),
                "--monthly-replay",
                str(source_monthly_base),
                "--daily-close",
                str(us_daily_close),
                "--benchmark-ticker",
                us_benchmark,
                "--output-dir",
                str(s04),
            ],
            cwd=ROOT,
            log_file=s04 / "run.log",
        )
        mark_done(s04, {"step": "us_daily_base"})

    # ---------- 05 US hedge all variants
    if selected_hedge_enabled(cfg):
        run_us_hedge_overlay_all(
            step_dir=s05,
            daily_equity_all=us_daily_equity_all,
            daily_close=us_daily_close,
            cfg=cfg,
            force=force,
        )
    else:
        print("[SKIP] 05_us_hedge_overlay_all selected_hedge_variant disabled")
        ensure_dir(s05)
        mark_done(s05, {"step": "us_hedge_overlay_all", "disabled": True})

    # ---------- 06 export selected US hedge variant
    selected_us_monthly = export_selected_hedge_variant(
        step_dir=s06,
        source_monthly=source_monthly_base,
        hedge_overlay_dir=s05,
        daily_equity_all=us_daily_equity_all,
        cfg=cfg,
        force=force,
    )

    # ---------- 07 optional UUP deep dive
    run_uup_deep_dive_if_enabled(
        step_dir=s07,
        daily_equity_all=us_daily_equity_all,
        daily_close=us_daily_close,
        cfg=cfg,
        force=force,
    )

    # ---------- 08 selected vs base
    if selected_hedge_enabled(cfg):
        run_hedge_vs_baseline(
            step_dir=s08,
            daily_equity_all=us_daily_equity_all,
            daily_close=us_daily_close,
            cfg=cfg,
            force=force,
        )
    else:
        print("[SKIP] 08_us_selected_vs_base selected_hedge_variant disabled")
        ensure_dir(s08)
        mark_done(s08, {"step": "us_selected_vs_base", "disabled": True})

    # ---------- 09 check UK data
    if step_done(s09, [uk_check_csv], force):
        print("[SKIP] 09_check_uk_data")
    else:
        print("[RUN ] 09_check_uk_data")
        ensure_dir(s09)
        run_cmd(
            [
                sys.executable,
                str(ENGINE / "check_ranges.py"),
                "--base-dir",
                str(uk_data_dir),
                "--tickers-file",
                str(uk_tickers),
                "--output-csv",
                str(uk_check_csv),
            ],
            cwd=ROOT,
            log_file=s09 / "run.log",
        )
        mark_done(s09, {"step": "check_uk_data"})

    # ---------- 10 build UK data
    required_uk_build = [
        uk_daily_close,
        uk_returns,
        uk_build_out / "resolved_files.csv",
    ]

    if step_done(s10, required_uk_build, force):
        print("[SKIP] 10_build_uk_data")
    else:
        print("[RUN ] 10_build_uk_data")
        ensure_dir(s10)
        run_cmd(
            [
                sys.executable,
                str(ENGINE / "build_data.py"),
                "--base-dir",
                str(uk_data_dir),
                "--tickers-file",
                str(uk_tickers),
                "--output-dir",
                str(uk_build_out),
                "--frequency",
                frequency,
            ],
            cwd=ROOT,
            log_file=s10 / "run.log",
        )
        mark_done(s10, {"step": "build_uk_data"})

    # ---------- 11 UK replay selected US variant
    if step_done(s11, [uk_replayed_monthly], force):
        print("[SKIP] 11_uk_replay_selected_hedge")
    else:
        print("[RUN ] 11_uk_replay_selected_hedge")
        ensure_dir(s11)

        cmd = [
            sys.executable,
            str(ENGINE / "replay_mapped_monthly.py"),
            "--monthly",
            str(selected_us_monthly),
            "--returns",
            str(uk_returns),
            "--mapping",
            str(mapping_file),
            "--benchmark",
            uk_benchmark,
            "--out-dir",
            str(s11),
            "--config",
            str(patched_hybrid_config),
            "--transaction-cost-bps-one-way",
            str(transaction_cost),
            "--annual-tax-rate",
            str(annual_tax),
            "--unmapped",
            str(cfg.get("unmapped", "cash")),
        ]

        if cfg.get("uk_strategy_name"):
            cmd += ["--strategy-name", str(cfg["uk_strategy_name"])]

        if cfg.get("execution_mode"):
            cmd += ["--execution-mode", str(cfg["execution_mode"])]

        run_cmd(cmd, cwd=ROOT, log_file=s11 / "run.log")
        mark_done(s11, {"step": "uk_replay_selected_hedge"})

    # ---------- 12 UK selected daily maxdd
    if step_done(s12, [uk_daily_summary, uk_daily_equity_all], force):
        print("[SKIP] 12_uk_selected_daily_maxdd")
    else:
        print("[RUN ] 12_uk_selected_daily_maxdd")
        ensure_dir(s12)
        run_cmd(
            [
                sys.executable,
                str(ENGINE / "daily_maxdd_from_monthly_weights.py"),
                "--monthly-replay",
                str(uk_replayed_monthly),
                "--daily-close",
                str(uk_daily_close),
                "--benchmark-ticker",
                uk_benchmark,
                "--output-dir",
                str(s12),
            ],
            cwd=ROOT,
            log_file=s12 / "run.log",
        )
        mark_done(s12, {"step": "uk_selected_daily_maxdd"})

    # ---------- 13 global summary TXT
    if step_done(s13, [global_summary_run], force):
        print("[SKIP] 13_global_summary")
    else:
        print("[RUN ] 13_global_summary")
        ensure_dir(s13)

        run_cmd(
            [
                sys.executable,
                str(ENGINE / "build_global_summary.py"),
                "--run-dir",
                str(run_dir),
                "--output",
                str(global_summary_run),
            ],
            cwd=ROOT,
            log_file=s13 / "run.log",
        )

        mark_done(s13, {"step": "global_summary"})

    copy_if_exists(global_summary_run, global_summary_final)

    manifest = {
        "idea": idea_name,
        "run_dir": str(run_dir),
        "global_summary": str(global_summary_final),
        "frequency": frequency,
        "us_benchmark": us_benchmark,
        "uk_benchmark": uk_benchmark,
        "us_base_monthly": str(source_monthly_base),
        "us_selected_monthly": str(selected_us_monthly),
        "selected_hedge_variant": get_selected_hedge_cfg(cfg),
    }

    write_json(run_dir / "RUN_MANIFEST.json", manifest)

    print()
    print("[OK] Pipeline finished")
    print(f"Raport: {rel(global_summary_final)}")
    print(f"Run:    {rel(run_dir)}")


# =========================
# CLI
# =========================

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Globalny pipeline: US base -> US selected hedge -> UK replay selected hedge -> GLOBAL_SUMMARY.txt"
        )
    )

    parser.add_argument(
        "--idea",
        required=True,
        help="Nazwa folderu z ideas/, np. best17_3m",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Wymusza ponowne uruchomienie etapów.",
    )

    parser.add_argument(
        "--run",
        default=None,
        help="Opcjonalnie istniejący folder run do wznowienia.",
    )

    args = parser.parse_args()

    run_pipeline(
        idea_name=args.idea,
        force=args.force,
        requested_run=args.run,
    )


if __name__ == "__main__":
    main()