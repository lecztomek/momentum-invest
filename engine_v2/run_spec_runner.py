"""
RUN SPEC RUNNER - "run(run_spec, base_dir)".

Wiaze `RunSpec.mode` z odpowiednim mechanizmem (patrz README, sekcja "Tryby uzycia pipeline'u"):

  - "final"      -> SINGLE BACKTEST na calej dostepnej historii, METRICS, sprawdzenie wzgledem
                     AcceptanceSpec.global_. ("ladny raport historyczny, finalista bez dalszego
                     poprawiania")
  - "validation" -> SINGLE BACKTEST na calej historii, ale METRICS liczone TYLKO na wycinku
                     odpowiadajacym TestSpec.test_window (OOS) - jedna, czysta ocena, BEZ dalszego
                     ciecia na okna (test_window jest "swiete", nie szukamy w nim wielu prob).

`TestSpec.costs.annual_tax_rate` (jesli > 0) jest aplikowany w "final"/"validation" przez
`annual_tax.apply_annual_tax` - PRZED slice'owaniem do test_window w "validation" (podatek "high
water mark" musi widziec CALA historie, zeby poprawnie zbudowac baze podatkowa az do momentu
test_window, inaczej slice zresetowalby ja blednie do 1.0 na starcie okna). Metryki PRZED
podatkiem sa zachowane w wyniku jako `metrics_pre_tax` (nie ukryte, do porownania).
  - "search"     -> GRID SWEEP (StrategySpec.allowed_param_families) x WALK-FORWARD
                     (TestSpec.train_window) per wariant - zwraca zbiorcze statystyki
                     (srednia/min CAGR, najgorszy drawdown, srednia Sharpe) po oknach, dla kazdej
                     kombinacji parametrow, PLUS `param_stability` (patrz `param_stability.py`) -
                     wzgledny spadek `wf_mean_cagr` miedzy najlepszym a najgorszym wariantem w
                     calej rodzinie (male = stabilne plateau, duze = krucha, podatna na
                     overfitting kombinacja parametrow), sprawdzony wzgledem
                     `AcceptanceSpec.param_stability.max_relative_metric_drop_within_family`.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pandas as pd

from engine_v2.acceptance_check import check_criteria
from engine_v2.acceptance_spec import AcceptanceSpec
from engine_v2.annual_tax import apply_annual_tax
from engine_v2.backtest_engine import daily_equity_curve
from engine_v2.blocks.data_loader import REGISTRY as DATA_LOADER_REGISTRY
from engine_v2.grid_sweep import run_param_sweep
from engine_v2.metrics import compute_metrics
from engine_v2.param_stability import check_param_stability, compute_param_stability
from engine_v2.pipeline import run_strategy_pipeline
from engine_v2.run_spec import RunSpec
from engine_v2.spec import StrategySpec
from engine_v2.test_spec import TestSpec
from engine_v2.validation import run_walk_forward


def _load_daily_prices(strategy_spec: StrategySpec) -> pd.DataFrame:
    loader_fn = DATA_LOADER_REGISTRY[strategy_spec.blocks["data_loader"]]
    daily_params = dict(strategy_spec.base_params.get("data_loader", {}))
    daily_params["frequency"] = "daily"
    return loader_fn(strategy_spec.universe, daily_params).prices


def _tax_adjusted_equity_curve(equity_curve: pd.DataFrame, final_portfolio: pd.DataFrame, test_spec: TestSpec):
    """Zwraca (equity_curve_do_metryk, metrics_pre_tax) - jesli `test_spec.costs.annual_tax_rate`
    > 0, equity_curve_do_metryk jest PO podatku (patrz `annual_tax.py`) i `metrics_pre_tax` niesie
    metryki liczone na oryginalnej (przed-podatkowej) krzywej, do jawnego porownania. Inaczej
    equity_curve bez zmian, `metrics_pre_tax=None`."""
    annual_tax_rate = test_spec.costs.annual_tax_rate
    if annual_tax_rate <= 0.0:
        return equity_curve, None

    metrics_pre_tax = compute_metrics(equity_curve, final_portfolio, {})
    equity_curve_after_tax = apply_annual_tax(equity_curve, annual_tax_rate)
    return equity_curve_after_tax, metrics_pre_tax


def _run_final(
    strategy_spec: StrategySpec, test_spec: TestSpec, acceptance_spec: AcceptanceSpec
) -> Dict[str, Any]:
    final_portfolio = run_strategy_pipeline(strategy_spec)
    equity_curve = daily_equity_curve(final_portfolio, _load_daily_prices(strategy_spec), {})
    equity_curve, metrics_pre_tax = _tax_adjusted_equity_curve(equity_curve, final_portfolio, test_spec)
    metrics = compute_metrics(equity_curve, final_portfolio, {})

    result = {
        "mode": "final",
        "metrics": metrics,
        "acceptance": check_criteria(metrics, acceptance_spec.global_),
        "equity_curve": equity_curve,
        "final_portfolio": final_portfolio,
    }
    if metrics_pre_tax is not None:
        result["metrics_pre_tax"] = metrics_pre_tax
    return result


def _run_validation(
    strategy_spec: StrategySpec, test_spec: TestSpec, acceptance_spec: AcceptanceSpec
) -> Dict[str, Any]:
    final_portfolio = run_strategy_pipeline(strategy_spec)
    equity_curve = daily_equity_curve(final_portfolio, _load_daily_prices(strategy_spec), {})
    # podatek liczony na CALEJ historii PRZED wycieciem test_window - "high water mark" musi
    # widziec lata sprzed okna OOS, zeby poprawnie zbudowac baze podatkowa (patrz docstring modulu)
    equity_curve, _metrics_pre_tax_full_history = _tax_adjusted_equity_curve(equity_curve, final_portfolio, test_spec)

    start = pd.Timestamp(test_spec.test_window.start)
    end = pd.Timestamp(test_spec.test_window.end)
    ec_slice = equity_curve[(equity_curve["date"] >= start) & (equity_curve["date"] <= end)]
    fp_slice = final_portfolio[(final_portfolio["date"] >= start) & (final_portfolio["date"] <= end)]

    if ec_slice.empty or fp_slice.empty:
        raise ValueError(
            f"run_spec_runner: brak danych w test_window ({test_spec.test_window.start} - "
            f"{test_spec.test_window.end}) - sprawdz zakres dostepnych danych."
        )

    metrics = compute_metrics(ec_slice, fp_slice, {})

    return {
        "mode": "validation",
        "metrics": metrics,
        "acceptance": check_criteria(metrics, acceptance_spec.global_),
    }


def _run_search(
    strategy_spec: StrategySpec, test_spec: TestSpec, acceptance_spec: AcceptanceSpec
) -> Dict[str, Any]:
    daily_prices = _load_daily_prices(strategy_spec)

    def evaluate(variant_spec: StrategySpec) -> Dict[str, Any]:
        final_portfolio = run_strategy_pipeline(variant_spec)
        equity_curve = daily_equity_curve(final_portfolio, daily_prices, {})
        wf_result = run_walk_forward(equity_curve, final_portfolio, test_spec, {})

        if wf_result.empty:
            return {"wf_windows": 0}

        return {
            "wf_windows": len(wf_result),
            "wf_mean_cagr": wf_result["cagr"].mean(),
            "wf_min_cagr": wf_result["cagr"].min(),
            "wf_worst_drawdown": wf_result["max_drawdown"].min(),
            "wf_mean_sharpe": wf_result["sharpe"].mean(),
        }

    sweep = run_param_sweep(strategy_spec, evaluate)

    # rodzina stabilna? liczone TYLKO na wariantach z >=1 oknem walk-forward (bez tego
    # "wf_mean_cagr" jest NaN - nie ma czego porownywac) i tylko gdy zostalo >=2 takie warianty
    # (relative_drop miedzy jednym wariantem a samym soba nie mowi nic o stabilnosci rodziny).
    valid_sweep = sweep[sweep["wf_windows"] > 0]
    param_stability = None
    param_stability_check: Dict[str, bool] = {}
    if len(valid_sweep) >= 2:
        param_stability = compute_param_stability(valid_sweep, "wf_mean_cagr")
        param_stability_check = check_param_stability(param_stability, acceptance_spec.param_stability)

    return {
        "mode": "search",
        "sweep": sweep,
        "param_stability": param_stability,
        "param_stability_check": param_stability_check,
    }


def run(run_spec: RunSpec, base_dir: Path) -> Dict[str, Any]:
    problems = run_spec.validate()
    if problems:
        raise ValueError(f"RunSpec niepoprawny: {problems}")

    paths = run_spec.resolve_paths(base_dir)
    strategy_spec = StrategySpec.load(paths["strategy_spec"])
    test_spec = TestSpec.load(paths["test_spec"])
    acceptance_spec = AcceptanceSpec.load(paths["acceptance_spec"])

    for spec_name, spec in (
        ("StrategySpec", strategy_spec),
        ("TestSpec", test_spec),
        ("AcceptanceSpec", acceptance_spec),
    ):
        spec_problems = spec.validate()
        if spec_problems:
            raise ValueError(f"{spec_name} niepoprawny: {spec_problems}")

    if run_spec.mode == "final":
        return _run_final(strategy_spec, test_spec, acceptance_spec)
    if run_spec.mode == "validation":
        return _run_validation(strategy_spec, test_spec, acceptance_spec)
    if run_spec.mode == "search":
        return _run_search(strategy_spec, test_spec, acceptance_spec)

    raise NotImplementedError(f"run_spec_runner: nieobslugiwany mode '{run_spec.mode}'.")
