"""
Testy STRUKTURALNE dla strategies_v2/gfm/ ("Global Factor Model", inwestujdlugoterminowo.pl) -
BRAK realnych danych dla wiekszosci tickerow (vtv/mtum/qqq/ijh/ijr/efv/mchi/gsg/vnq) w momencie
tworzenia tej strategii, wiec nie ma tu jeszcze testu end-to-end na prawdziwych cenach (jak np.
`test_gem_dual_momentum_switch.py::test_full_chain_on_real_data`) - tylko sprawdzenie, ze
StrategySpec jest poprawny i wszystkie zadeklarowane bloki (w tym nowy "gfm_risk_switch")
faktycznie rozwiazuja sie w registry. Backtest na realnych danych - po dorzuceniu brakujacych
plikow cenowych.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_gfm_strategy_spec.py -v
"""

from pathlib import Path

from engine_v2.pipeline import resolve_blocks
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
