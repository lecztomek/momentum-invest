"""
Testy dla strategies_v2/gfm_breadth/ - wariant `gfm` z ryzykiem skalowanym STOPNIOWO wg
szerokosci rynku (nowy blok `gfm_breadth_risk_step`) zamiast binarnego przelacznika SPY 12M>0
(`gfm_risk_switch`). User: "Zmieniamy w GFM tylko mechanizm risk-off... Czesc ofensywna zostaje
bez zmian: nadal wybor top 4 aktywow wedlug momentum 3/6/12."

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_gfm_breadth_strategy_spec.py -v
"""

import json
from pathlib import Path

import pytest

from engine_v2.pipeline import resolve_blocks, run_strategy_pipeline
from engine_v2.spec import StrategySpec

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "strategies_v2" / "gfm_breadth" / "strategy_spec.json"


def _load_spec() -> StrategySpec:
    return StrategySpec.load(SPEC_PATH)


def test_gfm_breadth_spec_is_valid():
    spec = _load_spec()
    assert spec.validate() == []


def test_gfm_breadth_spec_resolves_all_blocks():
    spec = _load_spec()
    resolved = resolve_blocks(spec)
    for block_type in spec.blocks:
        assert block_type in resolved
    assert spec.blocks["portfolio_risk_engine"] == "gfm_breadth_risk_step"


def test_gfm_breadth_offensive_side_matches_gfm_unchanged():
    """User: 'czesc ofensywna zostaje bez zmian' - ta sama formula (mom_3+mom_6+mom_12)/3,
    top_n_risky=4, ten sam 14-elementowy risk-on universe co `gfm`."""
    spec = _load_spec()
    gfm_spec = StrategySpec.load(REPO_ROOT / "strategies_v2" / "gfm" / "strategy_spec.json")

    params = spec.base_params["portfolio_risk_engine"]
    gfm_params = gfm_spec.base_params["portfolio_risk_engine"]

    assert set(params["risky_assets"]) == set(gfm_params["risk_on_assets"])
    assert params["risky_mom_keys"] == gfm_params["risk_on_mom_keys"]
    assert params["top_n_risky"] == gfm_params["top_n"]


def test_gfm_breadth_protective_candidates_add_shy_to_ief_tlt():
    """User: 'czesc defensywna wybiera najlepszy z SHY, IEF, TLT' - 3 kandydaci, nie 2 jak w
    oryginalnym gfm_risk_switch (tylko IEF/TLT)."""
    spec = _load_spec()
    params = spec.base_params["portfolio_risk_engine"]
    assert set(params["protective_assets"]) == {"shy.us", "ief.us", "tlt.us"}


def test_gfm_breadth_thresholds_give_five_equal_thirds_of_14():
    """breadth_thresholds=[3,6,9,12] + risky_shares=[0,.25,.5,.75,1.0] - 5 koszykow po 3 z 14
    mozliwych wartosci szerokosci (0-14), dajace dokladnie progi z opisu usera (100/75/50/25/0%)."""
    spec = _load_spec()
    params = spec.base_params["portfolio_risk_engine"]
    assert params["breadth_thresholds"] == [3, 6, 9, 12]
    assert params["risky_shares"] == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert len(params["risky_assets"]) == 14


def test_gfm_breadth_full_chain_on_real_data(us_data_dir):
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
    top_n_risky = spec.base_params["portfolio_risk_engine"]["top_n_risky"]

    saw_full_defensive = saw_full_risk = saw_partial = False
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        protective_total = sum(weights.get(t, 0.0) for t in protective)
        risky_total = sum(weights.get(t, 0.0) for t in risky)
        held_risky = sum(1 for t in risky if weights.get(t, 0.0) > 1e-9)
        if protective_total >= 1.0 - 1e-9:
            saw_full_defensive = True
        if risky_total >= 1.0 - 1e-9:
            saw_full_risk = True
        if protective_total > 1e-9 and risky_total > 1e-9:
            saw_partial = True
        assert held_risky <= top_n_risky

    # dowod na SKOKOWE (nie tylko binarne) przejscie - musialy wystapic oba skrajne rezymy ORAZ
    # co najmniej jeden posredni (25%/50%/75%)
    assert saw_full_defensive
    assert saw_full_risk
    assert saw_partial

    # zero niezamierzonej dzwigni
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        assert sum(weights.values()) <= 1.0 + 1e-6
