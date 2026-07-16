"""
Testy dla strategies_v2/best17_a_uk/ - user: "to samo dla best17" (analogia do `gpm_uk`).
`best17_a` zbudowany WPROST na tickerach UK (Acc, prawdziwy total return) jako WLASNYM zrodlowym
uniwersum - zero ekstrapolacji US Dist danych. Mechanika DOKLADNIE identyczna jak `best17_a`
(canary_regime_gate, ema_ratio_monthly, rebound_starter) - tylko podmiana nazw tickerow.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_best17_a_uk_strategy_spec.py -v
"""

import json
from pathlib import Path

import pytest

from engine_v2.pipeline import resolve_blocks, run_strategy_pipeline
from engine_v2.spec import StrategySpec

REPO_ROOT = Path(__file__).resolve().parents[2]
BEST17_A_UK_SPEC_PATH = REPO_ROOT / "strategies_v2" / "best17_a_uk" / "strategy_spec.json"


def _load_spec() -> StrategySpec:
    return StrategySpec.load(BEST17_A_UK_SPEC_PATH)


def test_best17_a_uk_spec_is_valid():
    spec = _load_spec()
    assert spec.validate() == []


def test_best17_a_uk_spec_resolves_all_blocks():
    spec = _load_spec()
    resolved = resolve_blocks(spec)
    for block_type in spec.blocks:
        assert block_type in resolved


def test_best17_a_uk_uses_plain_loader_on_uk_data():
    spec = _load_spec()
    assert spec.blocks["data_loader"] == "stooq_csv"
    assert spec.base_params["data_loader"]["data_dir"] == "data/uk"


def test_best17_a_uk_universe_matches_best17_a_ticker_mapping():
    """Uniwersum musi byc DOKLADNIE UK odpowiednikami best17_a's US uniwersum (xlk/ivv/dbc/iau/vt
    -> iuit/cspx/cmod/igln/vwra), wg juz istniejacego uk_ticker_mapping.json."""
    spec = _load_spec()
    best17_a_spec = StrategySpec.load(REPO_ROOT / "strategies_v2" / "best17_a" / "strategy_spec.json")
    mapping = json.loads((REPO_ROOT / "strategies_v2" / "best17_a" / "uk_ticker_mapping.json").read_text())

    expected_uk = {mapping[t] for t in best17_a_spec.universe}
    assert set(spec.universe) == expected_uk


def test_best17_a_uk_rebound_ticker_is_vwra():
    spec = _load_spec()
    assert spec.base_params["portfolio_risk_engine"]["rebound_ticker"] == "vwra.uk"
    assert set(spec.base_params["asset_filters"]["canary"]["canary_assets"]) == {"vwra.uk", "iuit.uk"}


def test_best17_a_uk_full_chain_on_real_data(uk_data_dir):
    spec = _load_spec()
    spec.base_params["data_loader"]["data_dir"] = str(uk_data_dir)

    final_portfolio = run_strategy_pipeline(spec)

    assert final_portfolio["date"].is_monotonic_increasing
    assert len(final_portfolio) > 12
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)
