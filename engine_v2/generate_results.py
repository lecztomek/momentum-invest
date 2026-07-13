"""
GENERATE RESULTS - user: "Dlaczego w repo nie mamy zadnych plikow wynikowych z testow strategii -
powinny byc wrzucone zeby nie trzeba bylo tego odpalac co chwile ponownie". Dotad kazda liczba w
CHANGELOG.md/README.md pochodzila z ad-hoc skryptu uruchamianego recznie i wklejanego jako proza -
brak jednego, wygenerowanego, maszynowo czytelnego zrodla prawdy per strategia (README oznaczal to
jako "FINAL REPORT: reporting ❌").

Generuje:
  - `results/<strategia>.json` - dla KAZDEJ zapisanej strategii (pojedynczej -
    `strategy_spec.json`+`run_spec.json`, oraz laczonej - `combined_spec.json`) podsumowanie
    liczbowe: metrics/metrics_pre_tax/acceptance/uk_mapping (BEZ surowych equity_curve/
    final_portfolio - te da sie odtworzyc z kodu w kazdej chwili, tu chodzi o zamrozenie WYNIKU,
    nie duplikowanie danych), PLUS (user: "brakuje wynikow np named periods danych o
    stabilnosci"):
      - `named_periods_all` - metryki na WSZYSTKICH `KNOWN_PERIODS` (nie tylko tych faktycznie
        wpisanych w `acceptance_spec.json`, ktory dla wiekszosci strategii jest pusty `{}`).
      - `train_oos` - metryki osobno na `train_window`/`test_window` (dla portfeli laczonych -
        TYLKO gdy WSZYSTKIE skladowe maja IDENTYCZNE okna w swoich `test_spec.json`, inaczej
        `null`).
      - `param_stability_full` (TYLKO pojedyncze strategie z `allowed_param_families`) - PELNY
        grid sweep x walk-forward (`run_spec_runner._run_search`), nie tylko pojedynczy
        `relative_drop` - user wczesniej w sesji: "a nie pokazales pelnej tabeli odpornosci".
      - `capital_weight_sensitivity` (TYLKO portfele laczone `fixed_capital_weights` z 2
        skladowymi) - sweep udzialu kapitalu pierwszej skladowej w [0.30..0.70], ten sam wzorzec
        co recznie liczony sweep dla `gpm_best17_a` (CHANGELOG (31)).
      - `uk_mapping` (portfele LACZONE - user: "wiadomo ze musi to sie przeliczyc" (44), po tym
        jak poprawka HYG EUR->USD nie trafila do `results/gpm_mid_10_best17_a.json`, bo ten
        generator w ogole nie liczyl UK mapping dla portfeli laczonych) - TYLKO gdy WSZYSTKIE
        skladowe strategie maja WLASNY `uk_ticker_mapping.json` (inaczej `null`), ten sam
        mechanizm co `run_spec_runner._run_uk_mapping_check` dla pojedynczej strategii, progi
        zalozone przez generator (`_COMBINED_UK_MAPPING_ACCEPTANCE`, ta sama konwencja co
        `annual_tax_rate_assumed`).
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

import dataclasses
import json
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from engine_v2.acceptance_spec import AcceptanceSpec, Criteria, UkMappingAcceptance
from engine_v2.annual_tax import apply_annual_tax
from engine_v2.backtest_engine import daily_equity_curve
from engine_v2.blocks.data_loader import REGISTRY as DATA_LOADER_REGISTRY
from engine_v2.combined_pipeline import run_combined_pipeline
from engine_v2.combined_spec import CombinedSpec
from engine_v2.metrics import compute_metrics
from engine_v2.named_periods import KNOWN_PERIODS, compute_named_period_metrics
from engine_v2.run_spec import RunSpec
from engine_v2.run_spec_runner import _run_search, run as run_single
from engine_v2.spec import StrategySpec
from engine_v2.test_spec import TestSpec
from engine_v2.uk_mapping import (
    check_uk_mapping_criteria,
    compare_us_vs_uk,
    find_uk_window_start,
    load_ticker_mapping,
    remap_final_portfolio,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
STRATEGIES_DIR = REPO_ROOT / "strategies_v2"
RESULTS_DIR = REPO_ROOT / "results"

_DEMO_DIRS = {"example_strategy", "example_strategy_b", "combined_example"}
_COMBINED_ANNUAL_TAX_RATE = 0.19
# user: "sprawdz naszego produkcyjnego kandydata wersja 50/50" (2026-07-12) - ten sam krok co
# wtedy uzyty dla `gpm_best17_a` (sweep wagi best17_a w [0.30..0.70], patrz CHANGELOG (31)),
# zgeneralizowany na KAZDY portfel `fixed_capital_weights` z DOKLADNIE 2 skladowymi (jedyny uklad
# w repo, patrz "Nigdy nie lacz 3 - max 2").
_CAPITAL_WEIGHT_SWEEP = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]
# `CombinedSpec` nie niesie wlasnego `AcceptanceSpec.uk_mapping` (progi sa czescia TestSpec
# pojedynczej strategii) - te same progi co uzywane w calej sesji dla portfeli laczonych
# (gpm_mid_10_best17_a "ostateczny test", CHANGELOG (41)/(43)/(44)), zalozenie generatora.
_COMBINED_UK_MAPPING_ACCEPTANCE = UkMappingAcceptance(
    max_weights_mismatch_months_pct=0.05,
    min_monthly_return_correlation=0.95,
    max_single_month_return_diff=0.03,
    max_cagr_gap_vs_us=0.03,
    max_drawdown_gap_vs_us=0.05,
)


def _named_periods_all(equity_curve: pd.DataFrame, final_portfolio: pd.DataFrame) -> Dict[str, Any]:
    """Metryki na WSZYSTKICH `KNOWN_PERIODS`, niezaleznie od tego, co dana strategia deklaruje w
    swoim (czesto pustym) `AcceptanceSpec.named_periods` - user: "brakuje wynikow np named
    periods" - to ma byc porownywalne 1:1 miedzy strategiami, nie zalezne od tego, czy ktos
    akurat wpisal te okresy do acceptance_spec.json."""
    return compute_named_period_metrics(
        equity_curve, final_portfolio, {name: Criteria() for name in KNOWN_PERIODS}
    )


def _train_oos_from_windows(
    equity_curve: pd.DataFrame, final_portfolio: pd.DataFrame, train_window, test_window
) -> Dict[str, Any]:
    def _slice_metrics(window) -> Dict[str, Any] | None:
        start, end = pd.Timestamp(window.start), pd.Timestamp(window.end)
        ec = equity_curve[(equity_curve["date"] >= start) & (equity_curve["date"] <= end)]
        fp = final_portfolio[(final_portfolio["date"] >= start) & (final_portfolio["date"] <= end)]
        if ec.empty:
            return None
        return compute_metrics(ec, fp, {})

    return {
        "train_window": {"start": train_window.start, "end": train_window.end},
        "test_window": {"start": test_window.start, "end": test_window.end},
        "train": _slice_metrics(train_window),
        "test_oos": _slice_metrics(test_window),
    }


def _param_stability_single(
    strategy_spec: StrategySpec, test_spec: TestSpec, acceptance_spec: AcceptanceSpec
) -> Dict[str, Any] | None:
    """Pelny grid sweep x walk-forward (`run_spec_runner._run_search`) - user wczesniej w tej
    sesji: "a nie pokazales pelnej tabeli odpornosci" - stad tu zapisujemy PELNY sweep (nie tylko
    pojedynczy `relative_drop`), zeby ta tabela byla dostepna bez ponownego odpalania. `None` gdy
    strategia nie ma `allowed_param_families` (nic do sweepowania)."""
    if not strategy_spec.allowed_param_families:
        return None
    search_result = _run_search(strategy_spec, test_spec, acceptance_spec)
    sweep = search_result["sweep"]
    return {
        "sweep": sweep.to_dict(orient="records") if isinstance(sweep, pd.DataFrame) else sweep,
        "param_stability": search_result["param_stability"],
        "param_stability_check": search_result["param_stability_check"],
        "local_param_stability": search_result["local_param_stability"],
        "fold_rank_stability": search_result["fold_rank_stability"],
    }


def _load_component_test_specs(combined_dir: Path, combined_spec: CombinedSpec) -> list[TestSpec] | None:
    specs = []
    for rel_path in combined_spec.strategy_spec_paths:
        test_spec_path = (combined_dir / rel_path).parent / "test_spec.json"
        if not test_spec_path.exists():
            return None
        specs.append(TestSpec.load(test_spec_path))
    return specs


def _train_oos_combined(
    combined_dir: Path, combined_spec: CombinedSpec, equity_curve: pd.DataFrame, final_portfolio: pd.DataFrame
) -> Dict[str, Any] | None:
    """`CombinedSpec` nie niesie wlasnego `TestSpec` - uzywamy okien train/test skladowych
    strategii TYLKO gdy WSZYSTKIE sa dostepne i IDENTYCZNE (inaczej porownanie train/oos nie
    mialoby jednoznacznego znaczenia dla polaczonego portfela)."""
    component_specs = _load_component_test_specs(combined_dir, combined_spec)
    if not component_specs:
        return None
    windows = {(s.train_window.start, s.train_window.end, s.test_window.start, s.test_window.end) for s in component_specs}
    if len(windows) != 1:
        return None
    return _train_oos_from_windows(
        equity_curve, final_portfolio, component_specs[0].train_window, component_specs[0].test_window
    )


def _uk_mapping_combined(
    combined_dir: Path,
    combined_spec: CombinedSpec,
    us_final_portfolio: pd.DataFrame,
    us_daily_prices: pd.DataFrame,
    annual_tax_rate: float,
) -> Dict[str, Any] | None:
    """Ten sam mechanizm co `run_spec_runner._run_uk_mapping_check` (pojedyncza strategia), tylko
    na wyniku `run_combined_pipeline` - `CombinedSpec` nie ma wlasnego `TestSpec.uk_mapping`, wiec
    mapowanie skladamy z uk_ticker_mapping.json KAZDEJ skladowej strategii (sibling jej
    strategy_spec.json). `None` gdy KTORAKOLWIEK skladowa nie ma wlasnego pliku mapowania -
    inaczej wynik bylby czesciowy/mylacy (user: "wszystkie tickery powinny byc w USD" - to samo
    dotyczy kompletnosci mapowania, nie tylko waluty)."""
    ticker_mapping: Dict[str, str] = {}
    for rel_path in combined_spec.strategy_spec_paths:
        mapping_path = (combined_dir / rel_path).parent / "uk_ticker_mapping.json"
        if not mapping_path.exists():
            return None
        ticker_mapping.update(load_ticker_mapping(mapping_path))

    uk_final_portfolio_full, _ = remap_final_portfolio(us_final_portfolio, ticker_mapping)
    uk_tickers = sorted(set(ticker_mapping.values()))
    loader_fn = DATA_LOADER_REGISTRY["stooq_csv"]
    uk_daily_prices = loader_fn(uk_tickers, {"data_dir": "data/uk", "frequency": "daily"}).prices
    uk_window_start = find_uk_window_start(uk_final_portfolio_full, uk_daily_prices)

    us_slice = us_final_portfolio[us_final_portfolio["date"] >= uk_window_start].reset_index(drop=True)
    uk_slice, diagnostics = remap_final_portfolio(us_slice, ticker_mapping)

    us_equity_curve = daily_equity_curve(us_slice, us_daily_prices, {})
    uk_equity_curve = daily_equity_curve(uk_slice, uk_daily_prices, {})
    if annual_tax_rate > 0.0:
        us_equity_curve = apply_annual_tax(us_equity_curve, annual_tax_rate)
        uk_equity_curve = apply_annual_tax(uk_equity_curve, annual_tax_rate)

    comparison = compare_us_vs_uk(us_slice, us_equity_curve, uk_slice, uk_equity_curve)
    return {
        "uk_window_start": uk_window_start.isoformat(),
        "n_periods_in_window": len(us_slice),
        "diagnostics": diagnostics,
        "comparison": comparison,
        "acceptance": check_uk_mapping_criteria(
            comparison, diagnostics["mismatch_pct"], _COMBINED_UK_MAPPING_ACCEPTANCE
        ),
    }


def _capital_weight_sensitivity(combined_dir: Path, combined_spec: CombinedSpec) -> Dict[str, Any] | None:
    """Analogon `param_stability` dla portfeli LACZONYCH (nie maja wlasnego
    `allowed_param_families`) - sweep udzialu kapitalu pierwszej skladowej strategii, ten sam
    wzorzec co recznie zrobiony sweep dla `gpm_best17_a` (CHANGELOG (31)). Tylko dla
    `fixed_capital_weights` z DOKLADNIE 2 skladowymi - inne combinery (`dynamic_capital_weights`,
    `signal_tilted_capital_weights`, `momentum_hedge_overlay`) nie maja jednego, ciaglego
    parametru wagi do sweepowania w ten sam sposob."""
    if combined_spec.combiner != "fixed_capital_weights":
        return None
    names = sorted(combined_spec.combiner_params.get("capital_weights", {}).keys())
    if len(names) != 2:
        return None
    name_a, name_b = names
    current_weight_a = combined_spec.combiner_params["capital_weights"][name_a]

    universe: set[str] = set()
    for rel_path in combined_spec.strategy_spec_paths:
        universe |= set(StrategySpec.load(combined_dir / rel_path).universe)
    loader_fn = DATA_LOADER_REGISTRY["stooq_csv"]
    daily_prices = loader_fn(sorted(universe), {"data_dir": "data/us", "frequency": "daily"}).prices

    records = []
    for weight_a in _CAPITAL_WEIGHT_SWEEP:
        variant = dataclasses.replace(
            combined_spec,
            combiner_params={"capital_weights": {name_a: weight_a, name_b: round(1.0 - weight_a, 10)}},
        )
        final_portfolio = run_combined_pipeline(variant, combined_dir)
        equity_curve = daily_equity_curve(final_portfolio, daily_prices, {})
        equity_curve = apply_annual_tax(equity_curve, _COMBINED_ANNUAL_TAX_RATE)
        metrics = compute_metrics(equity_curve, final_portfolio, {})
        records.append({f"weight_{name_a}": weight_a, **metrics})

    return {
        "weight_axis": f"weight_{name_a}",
        "current_weight": current_weight_a,
        "sweep": records,
    }


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
    strategy_spec = StrategySpec.load(strategy_dir / "strategy_spec.json")
    test_spec = TestSpec.load(strategy_dir / "test_spec.json")
    acceptance_spec = AcceptanceSpec.load(strategy_dir / "acceptance_spec.json")

    result = run_single(run_spec, strategy_dir)
    equity_curve = result["equity_curve"]
    final_portfolio = result["final_portfolio"]

    payload = {k: v for k, v in result.items() if k not in ("equity_curve", "final_portfolio")}
    payload["named_periods_all"] = _named_periods_all(equity_curve, final_portfolio)
    payload["train_oos"] = _train_oos_from_windows(
        equity_curve, final_portfolio, test_spec.train_window, test_spec.test_window
    )
    payload["param_stability_full"] = _param_stability_single(strategy_spec, test_spec, acceptance_spec)
    return payload


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
        "named_periods_all": _named_periods_all(equity_curve_after_tax, final_portfolio),
        "train_oos": _train_oos_combined(combined_dir, combined_spec, equity_curve_after_tax, final_portfolio),
        "capital_weight_sensitivity": _capital_weight_sensitivity(combined_dir, combined_spec),
        "uk_mapping": _uk_mapping_combined(
            combined_dir, combined_spec, final_portfolio, daily_prices, _COMBINED_ANNUAL_TAX_RATE
        ),
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
