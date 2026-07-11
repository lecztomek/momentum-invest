"""
Testy dla strategies_v2/gtaa_agg3/ i strategies_v2/gtaa_agg6/ (odtworzenie "GTAA AGG3"/"AGG6"
wg opisu dostarczonego przez usera) - w odroznieniu od test_gtaa_components.py (nowy blok na
danych syntetycznych), tu ladujemy FAKTYCZNE strategy_spec.json i sprawdzamy wiring + end-to-end
na realnych danych.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_gtaa_strategy_specs.py -v
"""

import json
from pathlib import Path

import pytest

from engine_v2.pipeline import resolve_blocks, run_strategy_pipeline
from engine_v2.spec import StrategySpec

REPO_ROOT = Path(__file__).resolve().parents[2]
STRATS = REPO_ROOT / "strategies_v2"

VARIANTS = {"gtaa_agg3": 3, "gtaa_agg6": 6}


def _load_spec(name: str) -> StrategySpec:
    return StrategySpec.load(STRATS / name / "strategy_spec.json")


@pytest.mark.parametrize("name", VARIANTS)
def test_gtaa_spec_is_valid(name):
    spec = _load_spec(name)
    assert spec.validate() == []


@pytest.mark.parametrize("name", VARIANTS)
def test_gtaa_spec_resolves_all_blocks(name):
    spec = _load_spec(name)
    resolved = resolve_blocks(spec)
    for block_type in spec.blocks:
        assert block_type in resolved


@pytest.mark.parametrize("name, top_n", VARIANTS.items())
def test_gtaa_top_n_matches_number_of_equal_weights(name, top_n):
    spec = _load_spec(name)
    assert spec.base_params["selector"]["top_n"] == top_n
    weights = spec.base_params["alpha_weighting"]["weights"]
    assert len(weights) == top_n
    assert sum(weights) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("name", VARIANTS)
def test_gtaa_bond_fallback_excluded_from_selection(name):
    spec = _load_spec(name)
    bond_fallback = spec.base_params["portfolio_risk_engine"]["bond_fallback_asset"]
    excluded = spec.base_params["asset_filters"]["exclude_bond_from_selection"]["assets"]
    assert bond_fallback in excluded


@pytest.mark.parametrize("name, top_n", VARIANTS.items())
def test_gtaa_full_chain_on_real_data(name, top_n, us_data_dir):
    spec = _load_spec(name)
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)

    assert final_portfolio["date"].is_monotonic_increasing
    assert len(final_portfolio) > 12
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)

    bond_fallback = spec.base_params["portfolio_risk_engine"]["bond_fallback_asset"]
    risky = set(spec.universe) - {bond_fallback}
    saw_full_bond = saw_risky_exposure = saw_mixed_slot = False
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        bond_weight = weights.get(bond_fallback, 0.0)
        risky_weight = sum(weights.get(t, 0.0) for t in risky)
        held_risky = sum(1 for t in risky if weights.get(t, 0.0) > 1e-9)
        if bond_weight >= 1.0 - 1e-9:
            saw_full_bond = True
        if risky_weight > 1e-9:
            saw_risky_exposure = True
        if bond_weight > 1e-9 and risky_weight > 1e-9:
            saw_mixed_slot = True
        assert held_risky <= top_n

    assert saw_full_bond
    assert saw_risky_exposure
    assert saw_mixed_slot  # dowod na PER-SLOT reroute, nie globalny switch jak w gpm/best17_a


def test_gtaa_agg3_metrics_regression_baseline(us_data_dir):
    """Zamrozony wynik na realnych danych (2026-07-11, PRZED podatkiem)."""
    from engine_v2.backtest_engine import daily_equity_curve
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.metrics import compute_metrics

    spec = _load_spec("gtaa_agg3")
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)
    market_data = LOADER_REGISTRY["stooq_csv"](spec.universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})
    equity_curve = daily_equity_curve(final_portfolio, market_data.prices, {})
    metrics = compute_metrics(equity_curve, final_portfolio, {})

    assert metrics["cagr"] == pytest.approx(0.0699, abs=0.01)
    assert metrics["max_drawdown"] == pytest.approx(-0.1969, abs=0.01)
    assert metrics["sharpe"] == pytest.approx(0.581, abs=0.05)


def test_gtaa_agg6_metrics_regression_baseline(us_data_dir):
    """Zamrozony wynik na realnych danych (2026-07-11, PRZED podatkiem)."""
    from engine_v2.backtest_engine import daily_equity_curve
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.metrics import compute_metrics

    spec = _load_spec("gtaa_agg6")
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)
    market_data = LOADER_REGISTRY["stooq_csv"](spec.universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})
    equity_curve = daily_equity_curve(final_portfolio, market_data.prices, {})
    metrics = compute_metrics(equity_curve, final_portfolio, {})

    assert metrics["cagr"] == pytest.approx(0.0630, abs=0.01)
    assert metrics["max_drawdown"] == pytest.approx(-0.1871, abs=0.01)
    assert metrics["sharpe"] == pytest.approx(0.660, abs=0.05)
