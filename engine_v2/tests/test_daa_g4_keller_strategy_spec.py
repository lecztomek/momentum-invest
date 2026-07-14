"""
Testy dla strategies_v2/daa_g4_keller/ - wariant "DAA-G4" (Keller & Keuning 2018) z user-podanymi
parametrami T=4, B=2 (user: "Zrob wersje daa g4 kellera", potem korekta: "Ale zle zrobiles ja
chce t 4 b 2" - poprzednia wersja tego pliku bazowala na T=2/B=1 z niezaleznego, wtornego zrodla
(TuringTrader "Easy Trading" wariant), user jawnie to skorygowal). Jedyna roznica wzgledem
istniejacego `daa_g4`: top_n_offensive=4 (wszystkie 4 aktywa ofensywne rownolegle) zamiast 1
(tylko najlepszy) - breadth_denominator=2 jest TAKI SAM jak domyslny w `daa_g4` (ciagly udzial
ochronny 0/50/100%).

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_daa_g4_keller_strategy_spec.py -v
"""

import json
from pathlib import Path

import pytest

from engine_v2.pipeline import resolve_blocks, run_strategy_pipeline
from engine_v2.spec import StrategySpec

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "strategies_v2" / "daa_g4_keller" / "strategy_spec.json"


def _load_spec() -> StrategySpec:
    return StrategySpec.load(SPEC_PATH)


def test_daa_g4_keller_spec_is_valid():
    spec = _load_spec()
    assert spec.validate() == []


def test_daa_g4_keller_spec_resolves_all_blocks():
    spec = _load_spec()
    resolved = resolve_blocks(spec)
    for block_type in spec.blocks:
        assert block_type in resolved


def test_daa_g4_keller_matches_user_specified_parameters():
    """User: 'ja chce t 4 b 2' - top_n_offensive=4 (wszystkie ofensywne), breadth_denominator=2
    (ciagly udzial ochronny), canary = VWO+AGG (podzbior ofensywnych)."""
    spec = _load_spec()
    params = spec.base_params["portfolio_risk_engine"]

    assert params["top_n_offensive"] == 4
    assert params["breadth_denominator"] == 2
    assert set(params["offensive_assets"]) == {"spy.us", "vea.us", "vwo.us", "agg.us"}
    assert set(params["canary_assets"]) == {"vwo.us", "agg.us"}
    assert set(params["defensive_assets"]) == {"shy.us", "ief.us", "lqd.us"}


def test_daa_g4_keller_differs_from_daa_g4_only_by_top_n_offensive():
    """Dokumentuje DOKLADNIE, czym ten wariant rozni sie od istniejacego `daa_g4` - TYLKO
    top_n_offensive (4 vs 1); breadth_denominator=2 jest identyczny z domyslnym w daa_g4
    (len(canary_assets)=2), wiec mechanizm udzialu ochronnego jest TAKI SAM."""
    spec = _load_spec()
    daa_g4_spec = StrategySpec.load(REPO_ROOT / "strategies_v2" / "daa_g4" / "strategy_spec.json")

    params = spec.base_params["portfolio_risk_engine"]
    daa_g4_params = daa_g4_spec.base_params["portfolio_risk_engine"]

    assert params["top_n_offensive"] != daa_g4_params["top_n_offensive"]
    assert params["top_n_offensive"] == 4
    assert daa_g4_params["top_n_offensive"] == 1
    assert params["breadth_denominator"] == len(params["canary_assets"]) == 2
    assert "breadth_denominator" not in daa_g4_params  # domyslnie = len(canary_assets) = 2, ten sam efekt


def test_daa_g4_keller_full_chain_on_real_data(us_data_dir):
    spec = _load_spec()
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)

    assert final_portfolio["date"].is_monotonic_increasing
    assert len(final_portfolio) > 12
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)

    defensive = set(spec.base_params["portfolio_risk_engine"]["defensive_assets"])
    offensive = set(spec.base_params["portfolio_risk_engine"]["offensive_assets"])
    top_n_offensive = spec.base_params["portfolio_risk_engine"]["top_n_offensive"]

    saw_full_offensive = saw_full_defensive = saw_mixed = False
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        defensive_total = sum(weights.get(t, 0.0) for t in defensive)
        offensive_total = sum(weights.get(t, 0.0) for t in offensive)
        held_offensive = sum(1 for t in offensive if weights.get(t, 0.0) > 1e-9)
        if offensive_total >= 1.0 - 1e-9:
            saw_full_offensive = True
        if defensive_total >= 1.0 - 1e-9:
            saw_full_defensive = True
        if 0.1 < defensive_total < 0.9:
            saw_mixed = True
        assert held_offensive <= top_n_offensive

    # udzial ochronny CIAGLY (breadth_denominator=2, jak daa_g4) - musialy wystapic wszystkie 3
    # poziomy (0%, ~50%, 100%), nie tylko binarne skrajnosci
    assert saw_full_offensive
    assert saw_full_defensive
    assert saw_mixed


def test_daa_g4_keller_holds_all_four_offensive_assets_when_fully_offensive(us_data_dir):
    """top_n_offensive=4 z DOKLADNIE 4 aktywami ofensywnymi - gdy udzial ryzykowny=100% (i wszystkie
    4 maja juz uzywalna historie, poza wczesna rozgrzewka), wszystkie 4 powinny byc trzymane
    rownolegle (rowne wagi 25% kazde), nie tylko najlepsze z nich."""
    spec = _load_spec()
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)
    offensive = set(spec.base_params["portfolio_risk_engine"]["offensive_assets"])
    defensive = set(spec.base_params["portfolio_risk_engine"]["defensive_assets"])

    final_portfolio = run_strategy_pipeline(spec)

    found_full_offensive_period = False
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        defensive_total = sum(weights.get(t, 0.0) for t in defensive)
        held_offensive = sum(1 for t in offensive if weights.get(t, 0.0) > 1e-9)
        if defensive_total < 1e-9 and held_offensive == 4:
            found_full_offensive_period = True
            break
    assert found_full_offensive_period


def test_daa_g4_keller_metrics_regression_baseline(us_data_dir):
    """Zamrozony wynik na realnych danych (2026-07-14, PRZED podatkiem)."""
    from engine_v2.backtest_engine import daily_equity_curve
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.metrics import compute_metrics

    spec = _load_spec()
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)
    market_data = LOADER_REGISTRY["stooq_csv"](spec.universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})
    equity_curve = daily_equity_curve(final_portfolio, market_data.prices, {})
    metrics = compute_metrics(equity_curve, final_portfolio, {})

    assert metrics["cagr"] == pytest.approx(0.0384, abs=0.01)
    assert metrics["max_drawdown"] == pytest.approx(-0.3028, abs=0.01)
    assert metrics["sharpe"] == pytest.approx(0.437, abs=0.05)
