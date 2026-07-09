from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_global_summary import fmt_int, fmt_num, fmt_pct, h1, h2, table  # noqa: E402

# Musi zostać w sync z comparison_table_block() w build_global_summary.py:
# ta sama lista Metrics w tej samej kolejności trafia do "COMPACT COMPARISON TABLE"
# w GLOBAL_SUMMARY.txt, którego ten skrypt parsuje.
SERIES_LABELS = [
    ("US selected hedge daily", "us_selected_daily"),
    ("UK selected hedge monthly", "uk_selected_monthly"),
    ("UK selected hedge daily", "uk_selected_daily"),
    ("US base A monthly", "us_base_monthly"),
    ("US base A daily", "us_base_daily"),
    ("UK base A monthly", "uk_base_monthly"),
    ("UK base A daily", "uk_base_daily"),
]
SERIES_LABELS_BY_LENGTH = sorted(SERIES_LABELS, key=lambda x: -len(x[0]))

TABLE_COLUMNS = [
    "final_equity", "cagr", "maxdd", "calmar",
    "benchmark_cagr", "benchmark_maxdd", "cagr_vs_benchmark", "maxdd_vs_benchmark",
]

PCT_FIELDS = {"cagr", "maxdd", "benchmark_cagr", "benchmark_maxdd", "cagr_vs_benchmark", "maxdd_vs_benchmark"}

TABLE_MARKER = "COMPACT COMPARISON TABLE FOR FUTURE STRATEGY SELECTION"


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def parse_value(token: str) -> Optional[float]:
    if token == "n/a":
        return None
    if token.endswith("%"):
        return float(token[:-1]) / 100.0
    return float(token)


def parse_compact_comparison_table(text: str) -> Dict[str, Dict[str, Optional[float]]]:
    idx = text.find(TABLE_MARKER)
    if idx == -1:
        return {}

    result: Dict[str, Dict[str, Optional[float]]] = {}

    for line in text[idx:].splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        for label, key in SERIES_LABELS_BY_LENGTH:
            if not stripped.startswith(label):
                continue

            tokens = stripped[len(label):].split()
            if len(tokens) != len(TABLE_COLUMNS):
                continue

            try:
                result[key] = {col: parse_value(tok) for col, tok in zip(TABLE_COLUMNS, tokens)}
            except ValueError:
                continue

            break

    return result


def read_hedge_asset_from_idea_config(ideas_dir: Path, idea_name: str) -> str:
    config_path = ideas_dir / idea_name / "idea_config.json"

    if not config_path.exists():
        return "n/a"

    try:
        cfg = read_json(config_path)
    except Exception:
        return "n/a"

    selected = cfg.get("selected_hedge_variant", {})
    if not isinstance(selected, dict) or not selected.get("enabled"):
        return "n/a"

    return str(selected.get("hedge_asset", "n/a"))


def collect_idea_row(idea_name: str, summary_path: Path, ideas_dir: Path, series_key: str) -> Dict[str, Any]:
    text = summary_path.read_text(encoding="utf-8", errors="replace")
    parsed = parse_compact_comparison_table(text)

    if not parsed:
        raise ValueError(f"Nie znalazłem sekcji '{TABLE_MARKER}' w {summary_path}")

    if series_key not in parsed:
        raise ValueError(
            f"Seria '{series_key}' nie istnieje w tabeli. Dostępne: {sorted(parsed.keys())}"
        )

    row: Dict[str, Any] = {
        "idea": idea_name,
        "summary_path": str(summary_path),
        "selected_hedge_variant": read_hedge_asset_from_idea_config(ideas_dir, idea_name),
    }
    row.update(parsed[series_key])

    return row


def compute_leaderboard(rows: pd.DataFrame, metrics_cfg: Dict[str, Dict[str, Any]]) -> Tuple[pd.DataFrame, List[str]]:
    d = rows.copy()

    score = pd.Series(0.0, index=d.index)
    weight_used = pd.Series(0.0, index=d.index)
    metric_warnings: List[str] = []

    for metric, cfg in metrics_cfg.items():
        weight = float(cfg.get("weight", 0.0))

        if weight <= 0:
            continue

        if metric not in d.columns:
            metric_warnings.append(
                f"'{metric}' (waga {weight}): nie jest kolumną tabeli porównawczej. "
                f"Dostępne: {TABLE_COLUMNS}."
            )
            continue

        higher_is_better = bool(cfg.get("higher_is_better", True))
        values = pd.to_numeric(d[metric], errors="coerce")
        valid = values.notna()

        if valid.sum() == 0:
            metric_warnings.append(
                f"'{metric}' (waga {weight}): 0/{len(d)} idei ma tę metrykę dla wybranej serii - "
                "cała waga jest ignorowana. Metryki cagr/benchmark_cagr/cagr_vs_benchmark istnieją tylko "
                "dla serii *_monthly (nie *_daily), a 'calmar' praktycznie nigdzie nie jest liczone - "
                "wybierz inną serię albo inną metrykę."
            )
            continue

        pct_rank = values.loc[valid].rank(pct=True, ascending=higher_is_better)
        score.loc[valid] += weight * pct_rank
        weight_used.loc[valid] += weight

    d["composite_score"] = score.where(weight_used > 0, other=pd.NA) / weight_used.replace(0, pd.NA)
    d = d.sort_values("composite_score", ascending=False, na_position="last").reset_index(drop=True)
    d.insert(0, "rank", range(1, len(d) + 1))

    return d, metric_warnings


def build_leaderboard_txt(
    leaderboard: pd.DataFrame,
    series_key: str,
    metrics_cfg: Dict[str, Dict[str, Any]],
    skipped: List[Tuple[str, str]],
    metric_warnings: List[str],
) -> str:
    out = "IDEAS LEADERBOARD\n"
    out += f"Seria porównywana: {series_key}\n"
    out += "\nWagi w compositowym score:\n"
    for metric, cfg in metrics_cfg.items():
        weight = cfg.get("weight", 0.0)
        if weight > 0:
            out += f"- {metric}: waga {weight}, higher_is_better={cfg.get('higher_is_better', True)}\n"

    if metric_warnings:
        out += "\n!! UWAGA - metryki z config, które nie dały żadnych danych:\n"
        for w in metric_warnings:
            out += f"!! {w}\n"

    out += h1("RANKING")

    display = leaderboard.copy()
    for col in display.columns:
        if col in PCT_FIELDS:
            display[col] = display[col].apply(fmt_pct)
        elif col in {"final_equity", "calmar", "composite_score"}:
            display[col] = display[col].apply(lambda v: fmt_num(v, 4))

    cols_order = [
        "rank", "idea", "composite_score", "cagr", "maxdd", "calmar",
        "cagr_vs_benchmark", "maxdd_vs_benchmark", "final_equity",
        "selected_hedge_variant", "summary_path",
    ]
    cols_order = [c for c in cols_order if c in display.columns]

    out += table(display[cols_order], max_rows=100, max_cols=len(cols_order))

    if skipped:
        out += h2("Pominięte idee")
        for name, reason in skipped:
            out += f"- {name}: {reason}\n"

    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Parsuje 'COMPACT COMPARISON TABLE' z już wygenerowanych GLOBAL_SUMMARY.txt dla wielu "
            "idei w ideas_out/ i rankinguje je wg konfigurowalnego composite score. Nie wymaga "
            "ponownego odpalania run_global_pipeline.py - działa na tym, co już jest zacommitowane."
        )
    )
    parser.add_argument("--ideas-out-dir", default="ideas_out")
    parser.add_argument("--ideas-dir", default="ideas", help="Katalog z idea_config.json (do odczytu hedge_asset).")
    parser.add_argument(
        "--ideas",
        nargs="*",
        default=None,
        help="Ograniczenie do wybranych idei (nazwy katalogów). Domyślnie wszystkie znalezione w ideas-out-dir.",
    )
    parser.add_argument("--config", required=True, help="JSON z kluczami: series, metrics (waga + higher_is_better per metryka).")
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--output-txt", default=None)
    args = parser.parse_args()

    cfg = read_json(Path(args.config))
    series_key = str(cfg.get("series", "uk_selected_monthly"))
    metrics_cfg = cfg.get("metrics", {})

    if not metrics_cfg:
        raise SystemExit("Config musi mieć niepustą sekcję 'metrics' z wagami.")

    ideas_out_dir = Path(args.ideas_out_dir)
    ideas_dir = Path(args.ideas_dir)

    if not ideas_out_dir.exists():
        raise SystemExit(f"Nie istnieje: {ideas_out_dir}")

    if args.ideas:
        idea_names = list(args.ideas)
    else:
        idea_names = sorted(p.name for p in ideas_out_dir.iterdir() if p.is_dir())

    rows: List[Dict[str, Any]] = []
    skipped: List[Tuple[str, str]] = []

    for idea_name in idea_names:
        summary_path = ideas_out_dir / idea_name / "GLOBAL_SUMMARY.txt"

        if not summary_path.exists():
            skipped.append((
                idea_name,
                f"brak {summary_path} - odpal run_global_pipeline.py --idea {idea_name} najpierw",
            ))
            continue

        try:
            rows.append(collect_idea_row(idea_name, summary_path, ideas_dir, series_key))
        except Exception as e:
            skipped.append((idea_name, f"błąd parsowania {summary_path}: {e}"))

    if not rows:
        raise SystemExit("Brak żadnych idei z danymi do porównania. Sprawdź --ideas-out-dir.")

    df = pd.DataFrame(rows)
    leaderboard, metric_warnings = compute_leaderboard(df, metrics_cfg)

    out_csv = Path(args.output_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    leaderboard.to_csv(out_csv, index=False, float_format="%.10f")
    print(f"[OK] zapisano: {out_csv}")

    if args.output_txt:
        txt = build_leaderboard_txt(leaderboard, series_key, metrics_cfg, skipped, metric_warnings)
        out_txt = Path(args.output_txt)
        out_txt.parent.mkdir(parents=True, exist_ok=True)
        out_txt.write_text(txt, encoding="utf-8")
        print(f"[OK] zapisano: {out_txt}")

    if metric_warnings:
        print("\n[UWAGA] Metryki z config bez danych (waga ignorowana):")
        for w in metric_warnings:
            print(f"  !! {w}")

    if skipped:
        print("\n[UWAGA] Pominięte idee:")
        for name, reason in skipped:
            print(f"  - {name}: {reason}")

    print("\n=== TOP ===")
    print(leaderboard[["rank", "idea", "composite_score"]].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
