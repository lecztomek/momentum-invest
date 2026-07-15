"""
Testy dla strategies_v2/gpm_uk/ - user: "Nie mozemy sobie tak wesolo ekstrapolowac danych us
dist nie podoba mi sie to - moze sprobujmy zrobic gpm na tickerach uk ale bez mappingu jako
zrodlowa strategie". W odroznieniu od `gpm_mid_10` (US Dist ceny + `stooq_csv_dividend_adjusted`,
ktory dla historii SPRZED startu danego UK ETF-u EKSTRAPOLUJE zmierzona stala stope), ta
strategia jest zbudowana WPROST na tickerach UK (Acc, prawdziwy total return z NAV, zero
ekstrapolacji) jako WLASNYM, zrodlowym uniwersum - `stooq_csv` (zwykly loader) na `data/uk`.

Cena: krotsza historia (~2018-2026, nie ~2007-2026) - user wybral wprost 10-aktywowe uniwersum
(jak gpm_mid_10, nie gpm_mid_13, zeby uniknac jeszcze krotszego okna przez SPEQ/RSP).

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_gpm_uk_strategy_spec.py -v
"""

import json
from pathlib import Path

import pytest

from engine_v2.pipeline import resolve_blocks, run_strategy_pipeline
from engine_v2.spec import StrategySpec

REPO_ROOT = Path(__file__).resolve().parents[2]
GPM_UK_SPEC_PATH = REPO_ROOT / "strategies_v2" / "gpm_uk" / "strategy_spec.json"

_RISKY_UK = {
    "cspx.uk", "cndx.uk", "eimi.uk", "xres.uk", "icom.uk", "igln.uk", "ihya.uk", "lqda.uk",
    "dtla.uk", "iues.uk",
}


def _load_spec() -> StrategySpec:
    return StrategySpec.load(GPM_UK_SPEC_PATH)


def test_gpm_uk_spec_is_valid():
    spec = _load_spec()
    assert spec.validate() == []


def test_gpm_uk_spec_resolves_all_blocks():
    spec = _load_spec()
    resolved = resolve_blocks(spec)
    for block_type in spec.blocks:
        assert block_type in resolved


def test_gpm_uk_uses_plain_loader_on_uk_data_no_mapping():
    """Kluczowa roznica wzgledem gpm_mid_10: `stooq_csv` (nie `stooq_csv_dividend_adjusted`) na
    `data/uk` (nie `data/us`) - zero ekstrapolacji, UK tickery sa WLASNYM zrodlem, nie korekta."""
    spec = _load_spec()
    assert spec.blocks["data_loader"] == "stooq_csv"
    assert spec.base_params["data_loader"]["data_dir"] == "data/uk"
    assert "dividend_adjustment_mapping" not in spec.base_params["data_loader"]


def test_gpm_uk_risky_universe_has_10_uk_assets_and_2_protective():
    spec = _load_spec()
    risky = spec.base_params["portfolio_risk_engine"]["risky_assets"]
    protective = spec.base_params["portfolio_risk_engine"]["protective_assets"]
    assert len(risky) == 10
    assert set(risky) == _RISKY_UK
    assert set(protective) == {"cbu0.uk", "ibta.uk"}
    assert set(spec.base_params["indicators"]["c"]["basket_assets"]) == set(risky)


def test_gpm_uk_full_chain_on_real_data(uk_data_dir):
    spec = _load_spec()
    spec.base_params["data_loader"]["data_dir"] = str(uk_data_dir)

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
