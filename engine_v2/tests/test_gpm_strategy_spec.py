"""
Testy dla strategies_v2/gpm/ (odtworzenie "Generalized Protective Momentum" wg opisu
dostarczonego przez usera) - w odroznieniu od test_gpm_components.py (nowe bloki na
SYNTETYCZNYCH danych), tu ladujemy FAKTYCZNY strategy_spec.json i sprawdzamy wiring + end-to-end
na realnych danych.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_gpm_strategy_spec.py -v
"""

import json
from pathlib import Path

import pytest

from engine_v2.pipeline import resolve_blocks, run_strategy_pipeline
from engine_v2.spec import StrategySpec

REPO_ROOT = Path(__file__).resolve().parents[2]
GPM_SPEC_PATH = REPO_ROOT / "strategies_v2" / "gpm" / "strategy_spec.json"


def _load_spec() -> StrategySpec:
    return StrategySpec.load(GPM_SPEC_PATH)


def test_gpm_spec_is_valid():
    spec = _load_spec()
    assert spec.validate() == []


def test_gpm_spec_resolves_all_blocks():
    spec = _load_spec()
    resolved = resolve_blocks(spec)
    for block_type in spec.blocks:
        assert block_type in resolved


def test_gpm_risky_universe_has_12_assets_and_2_protective():
    spec = _load_spec()
    risky = spec.base_params["portfolio_risk_engine"]["risky_assets"]
    protective = spec.base_params["portfolio_risk_engine"]["protective_assets"]
    assert len(risky) == 12
    assert len(protective) == 2
    # koszyk korelacji musi byc DOKLADNIE ten sam zestaw co risky_assets (staly koszyk odniesienia)
    assert set(spec.base_params["indicators"]["c"]["basket_assets"]) == set(risky)


def test_gpm_full_chain_on_real_data(us_data_dir):
    spec = _load_spec()
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)

    assert final_portfolio["date"].is_monotonic_increasing
    assert len(final_portfolio) > 12
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)

    # w historii musialy wystapic oba rezymy: pelna ochrona (100% w IEF/SHY, np. 2008/2020) i
    # czesciowa ekspozycja ryzykowna (co najmniej jedno z 12 aktywow ryzykownych > 0)
    risky = set(spec.base_params["portfolio_risk_engine"]["risky_assets"])
    protective = set(spec.base_params["portfolio_risk_engine"]["protective_assets"])
    saw_full_protective = saw_risky_exposure = False
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        protective_total = sum(weights.get(t, 0.0) for t in protective)
        risky_total = sum(weights.get(t, 0.0) for t in risky)
        if protective_total >= 1.0 - 1e-9:
            saw_full_protective = True
        if risky_total > 1e-9:
            saw_risky_exposure = True
    assert saw_full_protective
    assert saw_risky_exposure

    # nigdy wiecej niz top_n_risky aktywow ryzykownych naraz
    top_n_risky = spec.base_params["portfolio_risk_engine"]["top_n_risky"]
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        held_risky = sum(1 for t in risky if weights.get(t, 0.0) > 1e-9)
        assert held_risky <= top_n_risky


def test_gpm_metrics_regression_baseline(us_data_dir):
    """Zamrozony wynik na realnych danych (2026-07-11, PRZED podatkiem) - lapie regresje w nowych
    blokach (momentum_avg_month_end, corr_to_basket_month_end, momentum_times_decorrelation,
    gpm_breadth_protective_split). Najnizszy MaxDD z calej sesji."""
    from engine_v2.backtest_engine import daily_equity_curve
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.metrics import compute_metrics

    spec = _load_spec()
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)
    market_data = LOADER_REGISTRY["stooq_csv"](spec.universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})
    equity_curve = daily_equity_curve(final_portfolio, market_data.prices, {})
    metrics = compute_metrics(equity_curve, final_portfolio, {})

    assert metrics["cagr"] == pytest.approx(0.0532, abs=0.01)
    assert metrics["max_drawdown"] == pytest.approx(-0.1520, abs=0.01)
    assert metrics["sharpe"] == pytest.approx(0.668, abs=0.05)
