"""
Testy dla strategies_v2/best17_b/ ("Strategia B" uzytkownika - rotacja sektorowa XLP/XLV/XLF/XLE/
XLI/RSP, kanarek EMA7>EMA16 na XLI+XLP, momentum 9m, top2 50/50, histereza score-gap 3%). Zero
nowego kodu bloku - wylacznie konfiguracja z juz istniejacych blokow, wiec testy sprawdzaja
poprawnosc WIRINGU (StrategySpec, resolve_blocks) + end-to-end na realnych danych.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_best17_b_strategy_spec.py -v
"""

import json
from pathlib import Path

import pytest

from engine_v2.pipeline import resolve_blocks, run_strategy_pipeline
from engine_v2.spec import StrategySpec

REPO_ROOT = Path(__file__).resolve().parents[2]
BEST17_B_SPEC_PATH = REPO_ROOT / "strategies_v2" / "best17_b" / "strategy_spec.json"


def _load_spec() -> StrategySpec:
    return StrategySpec.load(BEST17_B_SPEC_PATH)


def test_best17_b_spec_is_valid():
    spec = _load_spec()
    assert spec.validate() == []


def test_best17_b_spec_resolves_all_blocks():
    spec = _load_spec()
    resolved = resolve_blocks(spec)
    for block_type in spec.blocks:
        assert block_type in resolved


def test_best17_b_canary_uses_xli_and_xlp():
    spec = _load_spec()
    canary = spec.base_params["asset_filters"]["canary"]
    assert set(canary["canary_assets"]) == {"xli.us", "xlp.us"}
    assert canary["max_bad_count"] == 0


def test_best17_b_hysteresis_gap_matches_3_percent():
    spec = _load_spec()
    assert spec.base_params["execution"]["min_score_gap"] == pytest.approx(0.03)
    assert spec.base_params["execution"]["full_position_size"] == 2


def test_best17_b_full_chain_on_real_data(us_data_dir):
    spec = _load_spec()
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)

    assert final_portfolio["date"].is_monotonic_increasing
    assert len(final_portfolio) > 12
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)

    # w historii musialy wystapic oba rezymy: risk-on (co najmniej 1 sektor trzymany) i
    # risk-off/cash (kanarek zly - caly portfel w _CASH)
    universe = set(spec.universe)
    saw_risk_on = saw_full_cash = False
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        held = sum(1 for t in universe if weights.get(t, 0.0) > 1e-9)
        if held > 0:
            saw_risk_on = True
        if weights.get("_CASH", 0.0) >= 1.0 - 1e-9:
            saw_full_cash = True
    assert saw_risk_on
    assert saw_full_cash

    # nigdy wiecej niz top_n=2 aktywow naraz
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        held = sum(1 for t in universe if weights.get(t, 0.0) > 1e-9)
        assert held <= 2
