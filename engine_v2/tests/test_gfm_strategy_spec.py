"""
Testy dla strategies_v2/gfm/ ("Global Factor Model", inwestujdlugoterminowo.pl) - strukturalne
(StrategySpec poprawny, wszystkie bloki w tym "gfm_risk_switch" rozwiazuja sie w registry) +
end-to-end na realnych danych (brakujace tickery vtv/mtum/qqq/ijh/ijr/efv/mchi/gsg/vnq dorzucone
2026-07-11).

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_gfm_strategy_spec.py -v
"""

import json
from pathlib import Path

import pytest

from engine_v2.pipeline import resolve_blocks, run_strategy_pipeline
from engine_v2.spec import StrategySpec

REPO_ROOT = Path(__file__).resolve().parents[2]
GFM_SPEC_PATH = REPO_ROOT / "strategies_v2" / "gfm" / "strategy_spec.json"


def _load_gfm_spec() -> StrategySpec:
    return StrategySpec.load(GFM_SPEC_PATH)


def test_gfm_spec_is_valid():
    spec = _load_gfm_spec()
    assert spec.validate() == []


def test_gfm_spec_resolves_all_blocks():
    spec = _load_gfm_spec()
    resolved = resolve_blocks(spec)
    for block_type, impl_name in spec.blocks.items():
        assert block_type in resolved
    assert spec.blocks["portfolio_risk_engine"] == "gfm_risk_switch"


def test_gfm_universe_covers_risk_on_and_risk_off_assets():
    spec = _load_gfm_spec()
    risk_engine_params = spec.base_params["portfolio_risk_engine"]
    risk_on = set(risk_engine_params["risk_on_assets"])
    risk_off = set(risk_engine_params["risk_off_assets"])

    assert risk_on | risk_off <= set(spec.universe)
    assert risk_on.isdisjoint(risk_off)


def test_gfm_top_n_sweep_family_matches_named_variants():
    # GFM-3 / GFM-4 / GFM-5 z opisu uzytkownika
    spec = _load_gfm_spec()
    assert spec.allowed_param_families["portfolio_risk_engine"]["top_n"] == [3, 4, 5]


def test_gfm_full_chain_on_real_data(us_data_dir):
    spec = _load_gfm_spec()
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)

    assert final_portfolio["date"].is_monotonic_increasing
    assert len(final_portfolio) > 12  # kilka lat historii, nie tylko rozgrzewka
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)

    # w historii musialy wystapic oba rezymy (risk-on w >=1 aktywie naraz, risk-off w dokladnie 1)
    risk_on_assets = set(spec.base_params["portfolio_risk_engine"]["risk_on_assets"])
    risk_off_assets = set(spec.base_params["portfolio_risk_engine"]["risk_off_assets"])
    saw_risk_on = saw_risk_off = False
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        held_on = sum(1 for t in risk_on_assets if weights.get(t, 0.0) > 1e-9)
        held_off = sum(1 for t in risk_off_assets if weights.get(t, 0.0) > 1e-9)
        if held_on > 0:
            saw_risk_on = True
        if held_off > 0:
            saw_risk_off = True
    assert saw_risk_on
    assert saw_risk_off
