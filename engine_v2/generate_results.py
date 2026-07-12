"""
GENERATE RESULTS - user: "Dlaczego w repo nie mamy zadnych plikow wynikowych z testow strategii -
powinny byc wrzucone zeby nie trzeba bylo tego odpalac co chwile ponownie". Dotad kazda liczba w
CHANGELOG.md/README.md pochodzila z ad-hoc skryptu uruchamianego recznie i wklejanego jako proza -
brak jednego, wygenerowanego, maszynowo czytelnego zrodla prawdy per strategia (README oznaczal to
jako "FINAL REPORT: reporting ❌").

Generuje:
  - `results/<strategia>.json` - dla KAZDEJ zapisanej strategii (pojedynczej -
    `strategy_spec.json`+`run_spec.json`, oraz laczonej - `combined_spec.json`) podsumowanie
    liczbowe: metrics/metrics_pre_tax/acceptance/named_periods/uk_mapping (BEZ surowych
    equity_curve/final_portfolio - te da sie odtworzyc z kodu w kazdej chwili, tu chodzi o
    zamrozenie WYNIKU, nie duplikowanie danych).
  - `results/SUMMARY.md` - jedna zbiorcza tabela (CAGR/MaxDD/Sharpe/Calmar/turnover, posortowane
    wg Calmar) do przegladania bez odpalania czegokolwiek.

Pomija foldery-szkielety bez wlasnego run_spec/combined_spec (np. `vaa_g4_ema`, uzywane tylko
jako skladnik innej strategii) oraz jawne przyklady demo (`example_strategy`, `example_strategy_b`,
`combined_example` - "nie realny run", patrz ich wlasne notes/hypothesis).

Dla portfeli LACZONYCH stosujemy TA SAMA konwencje podatkowa co uzywana w calej sesji dla ich
headline'owych wynikow (roczny podatek 19%, `annual_tax.apply_annual_tax`) - `combined_spec.json`
nie niesie wlasnego `costs`, wiec to zalozenie tego skryptu, nie czesc specyfikacji.

Nie jest czescia pytest/CI (pelny backtest + UK mapping na ~46 strategiach jest wolny) - nalezy
uruchomic recznie po kazdej zmianie strategii/bloku silnika, ktora wplywa na wyniki, i
zacommitowac nowy wynik.

Uruchomienie (z korzenia repo): .venv/bin/python3 -m engine_v2.generate_results
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from engine_v2.annual_tax import apply_annual_tax
from engine_v2.backtest_engine import daily_equity_curve
from engine_v2.blocks.data_loader import REGISTRY as DATA_LOADER_REGISTRY
from engine_v2.combined_pipeline import run_combined_pipeline
from engine_v2.combined_spec import CombinedSpec
from engine_v2.metrics import compute_metrics
from engine_v2.run_spec import RunSpec
from engine_v2.run_spec_runner import run as run_single
from engine_v2.spec import StrategySpec

REPO_ROOT = Path(__file__).resolve().parents[1]
STRATEGIES_DIR = REPO_ROOT / "strategies_v2"
RESULTS_DIR = REPO_ROOT / "results"

_DEMO_DIRS = {"example_strategy", "example_strategy_b", "combined_example"}
_COMBINED_ANNUAL_TAX_RATE = 0.19


def _jsonable(value: Any) -> Any:
    """Konwertuje numpy/pandas skalary (np.float64, np.bool_...) na natywne typy Pythona,
    rekurencyjnie po dict/list/tuple - reszta bez zmian."""
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "item") and callable(value.item):
        return value.item()
    return value


def _write_result(name: str, payload: Dict[str, Any]) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{name}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(_jsonable(payload), f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def _generate_single(strategy_dir: Path) -> Dict[str, Any]:
    run_spec = RunSpec.load(strategy_dir / "run_spec.json")
    result = run_single(run_spec, strategy_dir)
    return {k: v for k, v in result.items() if k not in ("equity_curve", "final_portfolio")}


def _generate_combined(combined_dir: Path) -> Dict[str, Any]:
    combined_spec = CombinedSpec.load(combined_dir / "combined_spec.json")
    final_portfolio = run_combined_pipeline(combined_spec, combined_dir)

    universe: set[str] = set()
    for rel_path in combined_spec.strategy_spec_paths:
        universe |= set(StrategySpec.load(combined_dir / rel_path).universe)

    loader_fn = DATA_LOADER_REGISTRY["stooq_csv"]
    daily_prices = loader_fn(sorted(universe), {"data_dir": "data/us", "frequency": "daily"}).prices

    equity_curve = daily_equity_curve(final_portfolio, daily_prices, {})
    metrics_pre_tax = compute_metrics(equity_curve, final_portfolio, {})
    equity_curve_after_tax = apply_annual_tax(equity_curve, _COMBINED_ANNUAL_TAX_RATE)
    metrics = compute_metrics(equity_curve_after_tax, final_portfolio, {})

    return {
        "mode": "combined_final",
        "annual_tax_rate_assumed": _COMBINED_ANNUAL_TAX_RATE,
        "metrics": metrics,
        "metrics_pre_tax": metrics_pre_tax,
    }


def _summary_row(name: str, payload: Dict[str, Any]) -> Dict[str, Any] | None:
    metrics = payload.get("metrics")
    if not metrics:
        return None
    return {
        "name": name,
        "mode": payload.get("mode"),
        "cagr": metrics["cagr"],
        "max_drawdown": metrics["max_drawdown"],
        "sharpe": metrics["sharpe"],
        "calmar": metrics["calmar"],
        "annual_turnover": metrics["annual_turnover"],
        "uk_mapping_pass": (
            all(payload["uk_mapping"]["acceptance"].values()) if payload.get("uk_mapping") else None
        ),
    }


def _write_summary(rows: list[Dict[str, Any]]) -> None:
    rows = sorted(rows, key=lambda r: r["calmar"], reverse=True)
    lines = [
        "# Wyniki wszystkich strategii (wygenerowane, patrz `engine_v2/generate_results.py`)",
        "",
        "Posortowane wg Calmar. `combined_final` = portfel laczony (podatek 19% zalozony przez "
        "generator, nie czesc specyfikacji). Pelne dane (walk-forward/sensitivity/UK mapping/"
        "named_periods) w odpowiadajacym `results/<nazwa>.json`.",
        "",
        "| Strategia | Tryb | CAGR | MaxDD | Sharpe | Calmar | Turnover/rok | UK mapping |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        uk = "-" if r["uk_mapping_pass"] is None else ("PASS" if r["uk_mapping_pass"] else "fail (patrz JSON)")
        lines.append(
            f"| `{r['name']}` | {r['mode']} | {r['cagr']:.2%} | {r['max_drawdown']:.2%} | "
            f"{r['sharpe']:.3f} | {r['calmar']:.3f} | {r['annual_turnover']:.2f} | {uk} |"
        )
    (RESULTS_DIR / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    summary_rows: list[Dict[str, Any]] = []

    single_dirs = sorted(
        d for d in STRATEGIES_DIR.iterdir()
        if d.is_dir() and (d / "run_spec.json").exists() and d.name not in _DEMO_DIRS
    )
    combined_dirs = sorted(
        d for d in STRATEGIES_DIR.iterdir()
        if d.is_dir() and (d / "combined_spec.json").exists() and d.name not in _DEMO_DIRS
    )

    for d in single_dirs:
        print(f"[single] {d.name} ...")
        payload = _generate_single(d)
        _write_result(d.name, payload)
        row = _summary_row(d.name, payload)
        if row:
            summary_rows.append(row)

    for d in combined_dirs:
        print(f"[combined] {d.name} ...")
        payload = _generate_combined(d)
        _write_result(d.name, payload)
        row = _summary_row(d.name, payload)
        if row:
            summary_rows.append(row)

    _write_summary(summary_rows)
    print(f"\nZapisano {len(single_dirs) + len(combined_dirs)} plikow wynikowych w {RESULTS_DIR}/")


if __name__ == "__main__":
    main()
