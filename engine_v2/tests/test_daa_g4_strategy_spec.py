"""
Testy dla strategies_v2/daa_g4/ (odtworzenie "DAA-G4", Keller & Keuning 2017) - w odroznieniu
od test_daa_components.py (nowy blok na danych syntetycznych), tu ladujemy FAKTYCZNY
strategy_spec.json i sprawdzamy wiring + end-to-end na realnych danych.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_daa_g4_strategy_spec.py -v
"""

import json
from pathlib import Path

import pytest

from engine_v2.pipeline import resolve_blocks, run_strategy_pipeline
from engine_v2.spec import StrategySpec

REPO_ROOT = Path(__file__).resolve().parents[2]
DAA_G4_SPEC_PATH = REPO_ROOT / "strategies_v2" / "daa_g4" / "strategy_spec.json"


def _load_spec() -> StrategySpec:
    return StrategySpec.load(DAA_G4_SPEC_PATH)


def test_daa_g4_spec_is_valid():
    spec = _load_spec()
    assert spec.validate() == []


def test_daa_g4_spec_resolves_all_blocks():
    spec = _load_spec()
    resolved = resolve_blocks(spec)
    for block_type in spec.blocks:
        assert block_type in resolved


def test_daa_g4_canary_is_subset_of_offensive_not_equal():
    """Rdzen roznicy vs vaa_g4 - kanarek TYLKO CZESCIA ofensywnych, nie wszystkimi 4."""
    spec = _load_spec()
    params = spec.base_params["portfolio_risk_engine"]
    canary = set(params["canary_assets"])
    offensive = set(params["offensive_assets"])
    assert canary < offensive  # podzbior WLASCIWY (mniejszy, nie rowny)
    assert len(canary) == 2
    assert len(offensive) == 4


def test_daa_g4_full_chain_on_real_data(us_data_dir):
    spec = _load_spec()
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)

    assert final_portfolio["date"].is_monotonic_increasing
    assert len(final_portfolio) > 12
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)

    # w historii musialy wystapic wszystkie 3 poziomy udzialu ochronnego (0%, ~50%, 100%)
    defensive = set(spec.base_params["portfolio_risk_engine"]["defensive_assets"])
    offensive = set(spec.base_params["portfolio_risk_engine"]["offensive_assets"])
    saw_full_offensive = saw_full_defensive = saw_mixed = False
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        defensive_total = sum(weights.get(t, 0.0) for t in defensive)
        offensive_total = sum(weights.get(t, 0.0) for t in offensive)
        if offensive_total >= 1.0 - 1e-9:
            saw_full_offensive = True
        if defensive_total >= 1.0 - 1e-9:
            saw_full_defensive = True
        if 0.1 < defensive_total < 0.9:
            saw_mixed = True
    assert saw_full_offensive
    assert saw_full_defensive
    assert saw_mixed


def test_daa_g4_metrics_regression_baseline(us_data_dir):
    """Zamrozony wynik na realnych danych (2026-07-11, PRZED podatkiem)."""
    from engine_v2.backtest_engine import daily_equity_curve
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.metrics import compute_metrics

    spec = _load_spec()
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)
    market_data = LOADER_REGISTRY["stooq_csv"](spec.universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})
    equity_curve = daily_equity_curve(final_portfolio, market_data.prices, {})
    metrics = compute_metrics(equity_curve, final_portfolio, {})

    assert metrics["cagr"] == pytest.approx(0.0662, abs=0.01)
    assert metrics["max_drawdown"] == pytest.approx(-0.2550, abs=0.01)
    assert metrics["sharpe"] == pytest.approx(0.538, abs=0.05)
