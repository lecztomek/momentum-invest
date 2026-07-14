"""
Testy dla strategies_v2/daa_g4_keller/ - wierna rekonstrukcja "DAA-G4" (Keller & Keuning 2018),
zweryfikowana wprost wzgledem niezaleznej implementacji referencyjnej (TuringTrader/BooksAndPubs/
Keller_DAA.cs). Rozni sie od istniejacego `strategies_v2/daa_g4/` (przyblizonej wersji) na 2
sposoby: top_n_offensive=2 (nie 1), breadth_denominator=1 (nie 2 = len(canary_assets)) - JEDEN
zly kanarek juz wymusza 100% ochrony (mechanizm BINARNY, nie ciagly 0/50/100%).

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


def test_daa_g4_keller_matches_published_parameters():
    """Zweryfikowane wprost wzgledem niezaleznej implementacji referencyjnej (TuringTrader) -
    T=2 (top-2 ofensywne), B=1 (breadth_denominator), canary = VWO+AGG (podzbior ofensywnych)."""
    spec = _load_spec()
    params = spec.base_params["portfolio_risk_engine"]

    assert params["top_n_offensive"] == 2
    assert params["breadth_denominator"] == 1
    assert set(params["offensive_assets"]) == {"spy.us", "vea.us", "vwo.us", "agg.us"}
    assert set(params["canary_assets"]) == {"vwo.us", "agg.us"}
    assert set(params["defensive_assets"]) == {"shy.us", "ief.us", "lqd.us"}


def test_daa_g4_keller_differs_from_daa_g4_approximation():
    """Dokumentuje DOKLADNIE, czym ten wariant rozni sie od istniejacego `daa_g4`."""
    spec = _load_spec()
    daa_g4_spec = StrategySpec.load(REPO_ROOT / "strategies_v2" / "daa_g4" / "strategy_spec.json")

    params = spec.base_params["portfolio_risk_engine"]
    daa_g4_params = daa_g4_spec.base_params["portfolio_risk_engine"]

    assert params["top_n_offensive"] != daa_g4_params["top_n_offensive"]
    assert params["top_n_offensive"] == 2
    assert daa_g4_params["top_n_offensive"] == 1
    # daa_g4 nie ma breadth_denominator ustawionego -> domyslnie = len(canary_assets) = 2
    assert "breadth_denominator" not in daa_g4_params
    assert params["breadth_denominator"] == 1


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

    saw_full_offensive = saw_full_defensive = False
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        defensive_total = sum(weights.get(t, 0.0) for t in defensive)
        offensive_total = sum(weights.get(t, 0.0) for t in offensive)
        held_offensive = sum(1 for t in offensive if weights.get(t, 0.0) > 1e-9)
        if offensive_total >= 1.0 - 1e-9:
            saw_full_offensive = True
        if defensive_total >= 1.0 - 1e-9:
            saw_full_defensive = True
        # BINARNY mechanizm (B=1) - nigdy "posrednia" mieszanka jak w daa_g4 (B=2)
        assert defensive_total == pytest.approx(0.0) or defensive_total == pytest.approx(1.0)
        assert held_offensive <= top_n_offensive

    assert saw_full_offensive
    assert saw_full_defensive


def test_daa_g4_keller_metrics_regression_baseline(us_data_dir):
    """Zamrozony wynik na realnych danych (2026-07-14, PRZED podatkiem). MaxDD gorszy niz
    istniejacy `daa_g4` w tym konkretnym oknie (2021-2024, wieloletnia bessa obligacji) -
    agresywne B=1 czesto ucieka w SHY/IEF/LQD, ktore SAME mialy wtedy zla passe, wiec ochrona
    nie pomagala tak skutecznie jak w innych okresach - odnotowane uczciwie, nie ukryte."""
    from engine_v2.backtest_engine import daily_equity_curve
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.metrics import compute_metrics

    spec = _load_spec()
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)
    market_data = LOADER_REGISTRY["stooq_csv"](spec.universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})
    equity_curve = daily_equity_curve(final_portfolio, market_data.prices, {})
    metrics = compute_metrics(equity_curve, final_portfolio, {})

    assert metrics["cagr"] == pytest.approx(0.0427, abs=0.01)
    assert metrics["max_drawdown"] == pytest.approx(-0.3758, abs=0.01)
    assert metrics["sharpe"] == pytest.approx(0.416, abs=0.05)
