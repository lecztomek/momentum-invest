"""
RUN SPEC RUNNER - "run(run_spec, base_dir)".

Wiaze `RunSpec.mode` z odpowiednim mechanizmem (patrz README, sekcja "Tryby uzycia pipeline'u"):

  - "final"      -> SINGLE BACKTEST na calej dostepnej historii, METRICS, sprawdzenie wzgledem
                     AcceptanceSpec.global_. ("ladny raport historyczny, finalista bez dalszego
                     poprawiania")
  - "validation" -> SINGLE BACKTEST na calej historii, ale METRICS liczone TYLKO na wycinku
                     odpowiadajacym TestSpec.test_window (OOS) - jedna, czysta ocena, BEZ dalszego
                     ciecia na okna (test_window jest "swiete", nie szukamy w nim wielu prob).
  - "search"     -> GRID SWEEP (StrategySpec.allowed_param_families) x WALK-FORWARD
                     (TestSpec.train_window) per wariant - zwraca zbiorcze statystyki
                     (srednia/min CAGR, najgorszy drawdown, srednia Sharpe) po oknach, dla kazdej
                     kombinacji parametrow.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pandas as pd

from engine_v2.acceptance_check import check_criteria
from engine_v2.acceptance_spec import AcceptanceSpec
from engine_v2.backtest_engine import daily_equity_curve
from engine_v2.blocks.data_loader import REGISTRY as DATA_LOADER_REGISTRY
from engine_v2.grid_sweep import run_param_sweep
from engine_v2.metrics import compute_metrics
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


def _run_final(strategy_spec: StrategySpec, acceptance_spec: AcceptanceSpec) -> Dict[str, Any]:
    final_portfolio = run_strategy_pipeline(strategy_spec)
    equity_curve = daily_equity_curve(final_portfolio, _load_daily_prices(strategy_spec), {})
    metrics = compute_metrics(equity_curve, final_portfolio, {})

    return {
        "mode": "final",
        "metrics": metrics,
        "acceptance": check_criteria(metrics, acceptance_spec.global_),
        "equity_curve": equity_curve,
        "final_portfolio": final_portfolio,
    }


def _run_validation(
    strategy_spec: StrategySpec, test_spec: TestSpec, acceptance_spec: AcceptanceSpec
) -> Dict[str, Any]:
    final_portfolio = run_strategy_pipeline(strategy_spec)
    equity_curve = daily_equity_curve(final_portfolio, _load_daily_prices(strategy_spec), {})

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


def _run_search(strategy_spec: StrategySpec, test_spec: TestSpec) -> Dict[str, Any]:
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

    return {"mode": "search", "sweep": run_param_sweep(strategy_spec, evaluate)}


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
        return _run_final(strategy_spec, acceptance_spec)
    if run_spec.mode == "validation":
        return _run_validation(strategy_spec, test_spec, acceptance_spec)
    if run_spec.mode == "search":
        return _run_search(strategy_spec, test_spec)

    raise NotImplementedError(f"run_spec_runner: nieobslugiwany mode '{run_spec.mode}'.")
