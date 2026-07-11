"""
Testy dla strategies_v2/best17_a_tlt_hedge/ (best17_a core + tlt_hedge, combiner
"momentum_hedge_overlay", hedge_weight=0.40) - dotad BRAKUJACY test: cala weryfikacja tej
kombinacji byla robiona ad-hoc skryptami w trakcie sesji, zero trwalego testu regresyjnego
lapiacego przyszle zmiany w momentum_hedge_overlay.py/tlt_hedge/best17_a.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_best17_a_tlt_hedge.py -v
"""

import json
from pathlib import Path

import pytest

from engine_v2.combined_pipeline import run_combined_pipeline
from engine_v2.combined_spec import CombinedSpec

REPO_ROOT = Path(__file__).resolve().parents[2]
COMBINED_SPEC_PATH = REPO_ROOT / "strategies_v2" / "best17_a_tlt_hedge" / "combined_spec.json"


def _load_spec() -> CombinedSpec:
    return CombinedSpec.load(COMBINED_SPEC_PATH)


def test_best17_a_tlt_hedge_spec_is_valid():
    spec = _load_spec()
    assert spec.validate() == []
    assert spec.combiner == "momentum_hedge_overlay"
    assert spec.combiner_params["hedge_weight"] == pytest.approx(0.40)
    assert spec.combiner_params["core_strategy"] == "best17_a_v0"
    assert spec.combiner_params["hedge_strategy"] == "tlt_hedge_v0"


def test_best17_a_tlt_hedge_end_to_end_on_real_data(us_data_dir):
    combined_spec = _load_spec()

    final_portfolio = run_combined_pipeline(combined_spec, COMBINED_SPEC_PATH.parent)

    assert final_portfolio["date"].is_monotonic_increasing
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)

    # hedge musial sie kiedys wlaczyc (tlt.us > 0 poza tym co core sam trzyma) - inaczej test
    # nic by nie sprawdzal ponad zwykle fixed_capital_weights
    saw_hedge_active = any(
        json.loads(w).get("tlt.us", 0.0) > 1e-9 for w in final_portfolio["weights_used_json"]
    )
    assert saw_hedge_active


def test_best17_a_tlt_hedge_never_activates_before_core_start(us_data_dir):
    """Regresja dla bugfixu 2026-07-11 (momentum_hedge_overlay wlaczal sie przed startem core) -
    hedge nie moze byc aktywny na datach sprzed pierwszego miesiaca best17_a (2008-07, best17_a
    nie ma danych XLK/IVV/DBC/IAU sprzed tego)."""
    from engine_v2.pipeline import run_strategy_pipeline
    from engine_v2.spec import StrategySpec

    combined_spec = _load_spec()
    core_spec = StrategySpec.load(COMBINED_SPEC_PATH.parent / "../best17_a/strategy_spec.json")
    core_final_portfolio = run_strategy_pipeline(core_spec)
    core_start = core_final_portfolio["date"].min()

    final_portfolio = run_combined_pipeline(combined_spec, COMBINED_SPEC_PATH.parent)
    before_core = final_portfolio[final_portfolio["date"] < core_start]

    for weights_json in before_core["weights_used_json"]:
        weights = json.loads(weights_json)
        assert weights.get("_CASH", 0.0) == pytest.approx(1.0)


def test_best17_a_tlt_hedge_metrics_regression_baseline(us_data_dir):
    """Zamrozony wynik na realnych danych (2026-07-11, po bugfixie 'wlaczal sie przed startem
    core') - lapie regresje w momentum_hedge_overlay/tlt_hedge/best17_a razem."""
    from engine_v2.backtest_engine import daily_equity_curve
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.metrics import compute_metrics

    combined_spec = _load_spec()
    final_portfolio = run_combined_pipeline(combined_spec, COMBINED_SPEC_PATH.parent)

    universe = ["xlk.us", "ivv.us", "dbc.us", "iau.us", "vt.us", "tlt.us"]
    market_data = LOADER_REGISTRY["stooq_csv"](universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})
    equity_curve = daily_equity_curve(final_portfolio, market_data.prices, {})
    metrics = compute_metrics(equity_curve, final_portfolio, {})

    assert metrics["cagr"] == pytest.approx(0.1410, abs=0.01)
    assert metrics["max_drawdown"] == pytest.approx(-0.2370, abs=0.01)
    assert metrics["sharpe"] == pytest.approx(0.97, abs=0.05)
