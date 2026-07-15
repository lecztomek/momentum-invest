"""
Testy dla strategies_v2/gpm_mid_13/ - user: "Chce nowa wersje strategii gpm - dodajmy tickery
rsp xlp xlv". Baza `gpm_mid_10` (10 aktywow ryzykownych, juz w pelni skorygowany o dywidendy) +
RSP (S&P 500 Equal Weight)/XLP (Consumer Staples)/XLV (Health Care) = 13. Korekta dywidend
wlaczona OD RAZU dla wszystkich 15 tickerow uniwersum (RSP/XLP/XLV maja juz realne dane Acc:
speq.uk/iucs.uk/iuhc.uk) - zero szacunkow, w odroznieniu od zablokowanego EFA/VEA w pelnym gpm.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_gpm_mid_13_strategy_spec.py -v
"""

import json
from pathlib import Path

import pytest

from engine_v2.pipeline import resolve_blocks, run_strategy_pipeline
from engine_v2.spec import StrategySpec

REPO_ROOT = Path(__file__).resolve().parents[2]
GPM_MID_13_SPEC_PATH = REPO_ROOT / "strategies_v2" / "gpm_mid_13" / "strategy_spec.json"

_RISKY = {
    "spy.us", "qqq.us", "vwo.us", "vnq.us", "dbc.us", "gld.us", "hyg.us", "lqd.us", "tlt.us",
    "xle.us", "rsp.us", "xlp.us", "xlv.us",
}


def _load_spec() -> StrategySpec:
    return StrategySpec.load(GPM_MID_13_SPEC_PATH)


def test_gpm_mid_13_spec_is_valid():
    spec = _load_spec()
    assert spec.validate() == []


def test_gpm_mid_13_spec_resolves_all_blocks():
    spec = _load_spec()
    resolved = resolve_blocks(spec)
    for block_type in spec.blocks:
        assert block_type in resolved


def test_gpm_mid_13_risky_universe_has_13_assets_and_2_protective():
    spec = _load_spec()
    risky = spec.base_params["portfolio_risk_engine"]["risky_assets"]
    protective = spec.base_params["portfolio_risk_engine"]["protective_assets"]
    assert len(risky) == 13
    assert set(risky) == _RISKY
    assert set(protective) == {"ief.us", "shy.us"}
    # koszyk korelacji musi byc DOKLADNIE ten sam zestaw co risky_assets (staly koszyk odniesienia)
    assert set(spec.base_params["indicators"]["c"]["basket_assets"]) == set(risky)


def test_gpm_mid_13_matches_gpm_mid_10_plus_three_new_tickers():
    """Dokumentuje DOKLADNIE, czym gpm_mid_13 rozni sie od gpm_mid_10: dokladnie 3 nowe aktywa
    ryzykowne (RSP/XLP/XLV), reszta (10 starych ryzykownych + 2 ochronne) bez zmian."""
    spec = _load_spec()
    gpm_mid_10_spec = StrategySpec.load(REPO_ROOT / "strategies_v2" / "gpm_mid_10" / "strategy_spec.json")

    risky = set(spec.base_params["portfolio_risk_engine"]["risky_assets"])
    old_risky = set(gpm_mid_10_spec.base_params["portfolio_risk_engine"]["risky_assets"])

    assert risky - old_risky == {"rsp.us", "xlp.us", "xlv.us"}
    assert old_risky - risky == set()
    assert spec.base_params["portfolio_risk_engine"]["protective_assets"] == (
        gpm_mid_10_spec.base_params["portfolio_risk_engine"]["protective_assets"]
    )


def test_gpm_mid_13_full_dividend_adjustment_coverage():
    """Wszystkie 15 tickerow uniwersum (13 ryzykownych + 2 ochronne) musza miec wpis w
    dividend_adjustment_mapping - pelne pokrycie, zero surowych/niescierowanych tickerow."""
    spec = _load_spec()
    mapping = spec.base_params["data_loader"]["dividend_adjustment_mapping"]
    assert set(mapping.keys()) == set(spec.universe)
    assert mapping["rsp.us"] == "speq"
    assert mapping["xlp.us"] == "iucs"
    assert mapping["xlv.us"] == "iuhc"


def test_gpm_mid_13_full_chain_on_real_data(us_data_dir):
    spec = _load_spec()
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)

    assert final_portfolio["date"].is_monotonic_increasing
    assert len(final_portfolio) > 12
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)

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

    top_n_risky = spec.base_params["portfolio_risk_engine"]["top_n_risky"]
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        held_risky = sum(1 for t in risky if weights.get(t, 0.0) > 1e-9)
        assert held_risky <= top_n_risky

    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        assert sum(weights.values()) <= 1.0 + 1e-6


def test_gpm_mid_13_metrics_regression_baseline(us_data_dir):
    """Zamrozony wynik na realnych danych (2026-07-15, PRZED podatkiem, PO korekcie dywidend
    od razu wlaczonej)."""
    from engine_v2.backtest_engine import daily_equity_curve
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.metrics import compute_metrics

    spec = _load_spec()
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)
    loader_name = spec.blocks["data_loader"]
    market_data = LOADER_REGISTRY[loader_name](spec.universe, spec.base_params["data_loader"])
    equity_curve = daily_equity_curve(final_portfolio, market_data.prices, {})
    metrics = compute_metrics(equity_curve, final_portfolio, {})

    assert metrics["cagr"] == pytest.approx(0.0602, abs=0.01)
    assert metrics["max_drawdown"] == pytest.approx(-0.1207, abs=0.01)
    assert metrics["sharpe"] == pytest.approx(0.746, abs=0.05)


def test_gpm_mid_13_uk_mapping_end_to_end(us_data_dir, uk_data_dir):
    """"Ostateczny test" (user) - realny `run_spec.json` (uk_mapping.enabled=true) na
    PRAWDZIWYCH danych US i UK. `gpm_mid_13` ma PELNE pokrycie (15/15 tickerow zmapowanych)."""
    from engine_v2.run_spec import RunSpec
    from engine_v2.run_spec_runner import run
    from engine_v2.test_spec import TestSpec

    strategy_dir = REPO_ROOT / "strategies_v2" / "gpm_mid_13"
    test_spec = TestSpec.load(strategy_dir / "test_spec.json")
    test_spec.uk_mapping.uk_data_dir = str(uk_data_dir)

    original_text = (strategy_dir / "test_spec.json").read_text(encoding="utf-8-sig")
    test_spec.save(strategy_dir / "test_spec.json")
    try:
        run_spec = RunSpec.load(strategy_dir / "run_spec.json")
        run_spec.mode = "final"
        result = run(run_spec, strategy_dir)
    finally:
        (strategy_dir / "test_spec.json").write_text(original_text, encoding="utf-8")

    uk_result = result["uk_mapping"]
    assert uk_result["diagnostics"]["mismatch_pct"] == 0.0
    assert uk_result["comparison"]["monthly_return_correlation"] > 0.9
    assert abs(uk_result["comparison"]["cagr_gap"]) < 0.05
    assert abs(uk_result["comparison"]["max_drawdown_gap"]) < 0.05
