"""
Testy dla strategies_v2/best18/ - `best17_a` + `xle.us` (energetyka) + `shy.us` (obligacje
krotkoterminowe) jako dodatkowi kandydaci w tym samym rankingu momentum (`ema7_16`) co
xlk/ivv/dbc/iau - top_n/wagi (2, 0.8/0.2) BEZ ZMIAN, patrz hypothesis w strategy_spec.json.

Znaleziony przez serie testow `crash_replay.py` na trzech wzorcach krachu (gfc_crash,
inflation_bear, covid_crash_rebound) - `xle.us` lapie inflation_bear (energetyka rosla w 2022,
gdy reszta spadala), `shy.us` lapie gfc_crash (nisko-zmienny defensywny kandydat, tanszy niz
tlt.us). Odrzucone alternatywy (sh.us, vnq.us, xlp.us, tlt.us, top_n=1/3) - patrz CHANGELOG.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_best18_strategy_spec.py -v
"""

import json
from pathlib import Path

import pytest

from engine_v2.pipeline import resolve_blocks, run_strategy_pipeline
from engine_v2.spec import StrategySpec

REPO_ROOT = Path(__file__).resolve().parents[2]
BEST18_SPEC_PATH = REPO_ROOT / "strategies_v2" / "best18" / "strategy_spec.json"


def _load_spec() -> StrategySpec:
    return StrategySpec.load(BEST18_SPEC_PATH)


def test_best18_spec_is_valid():
    spec = _load_spec()
    assert spec.validate() == []


def test_best18_spec_resolves_all_blocks():
    spec = _load_spec()
    resolved = resolve_blocks(spec)
    for block_type in spec.blocks:
        assert block_type in resolved


def test_best18_adds_xle_and_shy_without_changing_top_n():
    """xle.us/shy.us sa DODATKOWYMI kandydatami - top_n/wagi zostaja identyczne jak best17_a
    (2, 0.8/0.2), zeby poprawa byla przypisywalna WYLACZNIE nowym kandydatom, nie zmianie
    koncentracji (top_n=1/3 sprawdzone i odrzucone, patrz CHANGELOG)."""
    spec = _load_spec()
    assert set(spec.universe) == {"xlk.us", "ivv.us", "dbc.us", "iau.us", "vt.us", "xle.us", "shy.us"}
    assert spec.base_params["selector"]["top_n"] == 2
    assert spec.base_params["alpha_weighting"]["weights"] == [0.8, 0.2]


def test_best18_xle_is_offensive_candidate_gated_like_dbc_iau():
    """xle.us traktowany jak kolejne aktywo OFENSYWNE - w canary.target_assets/
    require_positive_score (wymaga risk-on) + wlasny gate mom_r3_gate > +1% (ten sam wzorzec co
    dbc_gate/iau_gate)."""
    spec = _load_spec()
    canary = spec.base_params["asset_filters"]["canary"]
    assert "xle.us" in canary["target_assets"]
    assert "xle.us" in spec.base_params["asset_filters"]["require_positive_score"]["assets"]

    xle_gate = spec.base_params["asset_filters"]["xle_gate"]
    assert xle_gate["indicator_key"] == "mom_r3_gate"
    assert xle_gate["threshold"] == pytest.approx(0.01)
    assert xle_gate["assets"] == ["xle.us"]


def test_best18_shy_is_defensive_candidate_not_gated_by_canary():
    """shy.us traktowany jak kandydat DEFENSYWNY (wzorzec z synergy_v1/tlt_gate) - eligibilny
    TYLKO gdy wlasny 12m momentum > 0, NIE dolaczony do canary.target_assets/
    require_positive_score (nie ma sensu wymagac risk-on od aktywa defensywnego)."""
    spec = _load_spec()
    canary = spec.base_params["asset_filters"]["canary"]
    assert "shy.us" not in canary["target_assets"]
    assert "shy.us" not in spec.base_params["asset_filters"]["require_positive_score"]["assets"]

    shy_gate = spec.base_params["asset_filters"]["shy_gate"]
    assert shy_gate["indicator_key"] == "mom_12"
    assert shy_gate["threshold"] == pytest.approx(0.0)
    assert shy_gate["assets"] == ["shy.us"]


def test_best18_full_chain_on_real_data(us_data_dir):
    spec = _load_spec()
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)

    assert final_portfolio["date"].is_monotonic_increasing
    assert len(final_portfolio) > 12
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)

    # xle.us i shy.us musialy byc faktycznie trzymane co najmniej raz w historii - inaczej
    # dodanie ich do uniwersum byloby no-opem (nigdy nie przechodza gate'ow)
    held_tickers = set()
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        held_tickers.update(t for t, w in weights.items() if w > 1e-9)
    assert "xle.us" in held_tickers
    assert "shy.us" in held_tickers


def test_best18_metrics_regression_baseline(us_data_dir):
    """Zamrozony wynik na realnych danych (2026-08-13) - lapie regresje w nowych gate'ach
    (xle_gate/shy_gate) i w dziedziczonych z best17_a blokach."""
    from engine_v2.backtest_engine import daily_equity_curve
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.metrics import compute_metrics

    spec = _load_spec()
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)
    market_data = LOADER_REGISTRY["stooq_csv"](spec.universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})
    equity_curve = daily_equity_curve(final_portfolio, market_data.prices, {})
    metrics = compute_metrics(equity_curve, final_portfolio, {})

    assert metrics["cagr"] == pytest.approx(0.1499, abs=0.01)
    assert metrics["max_drawdown"] == pytest.approx(-0.3119, abs=0.01)
    assert metrics["sharpe"] == pytest.approx(0.873, abs=0.05)


def test_best18_uk_mapping_end_to_end(us_data_dir, uk_data_dir):
    """Ten sam "ostateczny test" wzorzec co best17_a - realny run_spec.json (uk_mapping.enabled=
    true) na PRAWDZIWYCH danych US i UK, teraz z xle.us/shy.us dodanymi do mappingu (te same
    tickery UK co juz uzywane w gpm_mid_10: iues.uk/ibta.uk)."""
    from engine_v2.run_spec import RunSpec
    from engine_v2.run_spec_runner import run
    from engine_v2.test_spec import TestSpec

    strategy_dir = REPO_ROOT / "strategies_v2" / "best18"
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
    assert uk_result["diagnostics"]["unmapped_tickers_used"] == []
    assert uk_result["diagnostics"]["mismatch_pct"] == 0.0
    assert uk_result["comparison"]["monthly_return_correlation"] > 0.9
