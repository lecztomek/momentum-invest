"""
Testy dla strategies_v2/best17_a/ (realna strategia uzytkownika 'best17_3m', BEZ hedge overlay) -
w odroznieniu od test_best17_a_components.py (bloki na SYNTETYCZNYCH danych), tu ladujemy
FAKTYCZNY strategy_spec.json i sprawdzamy wiring + end-to-end na realnych danych - dotad
brakujacy test (nikt nie wywolywal `run_strategy_pipeline` na PRAWDZIWYM pliku tej strategii).

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_best17_a_strategy_spec.py -v
"""

import json
from pathlib import Path

import pytest

from engine_v2.pipeline import resolve_blocks, run_strategy_pipeline
from engine_v2.spec import StrategySpec

REPO_ROOT = Path(__file__).resolve().parents[2]
BEST17_A_SPEC_PATH = REPO_ROOT / "strategies_v2" / "best17_a" / "strategy_spec.json"


def _load_spec() -> StrategySpec:
    return StrategySpec.load(BEST17_A_SPEC_PATH)


def test_best17_a_spec_is_valid():
    spec = _load_spec()
    assert spec.validate() == []


def test_best17_a_spec_resolves_all_blocks():
    spec = _load_spec()
    resolved = resolve_blocks(spec)
    for block_type in spec.blocks:
        assert block_type in resolved


def test_best17_a_canary_uses_vt_and_xlk():
    spec = _load_spec()
    canary = spec.base_params["asset_filters"]["canary"]
    assert set(canary["canary_assets"]) == {"vt.us", "xlk.us"}
    assert canary["max_bad_count"] == 0


def test_best17_a_hysteresis_matches_own_top_n():
    spec = _load_spec()
    assert spec.base_params["execution"]["full_position_size"] == spec.base_params["selector"]["top_n"]


def test_best17_a_asset_gates_use_month_start_momentum_not_month_end():
    """POPRAWKA 2026-07-11 (patrz CHANGELOG) - iau_gate/dbc_gate MUSZA uzywac execution-price
    (momentum_monthly), NIE momentum_month_end (ta bazuje na cenach konca miesiaca - bledna
    podstawa dla `min_return_3m` w starym silniku, zweryfikowane na 428 parach z prawdziwego
    CSV). `mom_r3` (momentum_month_end) zostaje bez zmian dla rebound_starter - INNY mechanizm
    w starym silniku, poprawnie oparty na cenach konca miesiaca."""
    spec = _load_spec()
    indicators = spec.base_params["indicators"]
    assert indicators["mom_r3_gate"]["impl"] == "momentum_monthly"
    assert indicators["mom_r3"]["impl"] == "momentum_month_end"

    iau_gate = spec.base_params["asset_filters"]["iau_gate"]
    dbc_gate = spec.base_params["asset_filters"]["dbc_gate"]
    assert iau_gate["indicator_key"] == "mom_r3_gate"
    assert dbc_gate["indicator_key"] == "mom_r3_gate"

    rebound = spec.base_params["portfolio_risk_engine"]
    assert rebound["indicator_key"] == "mom_r3"


def test_best17_a_iau_gate_matches_new_plus_1pct_threshold(us_data_dir):
    """POPRAWKA 2026-07-15 (user: "Mamy bledny prog gate powinien byc plus 1 procent") -
    `iau_gate`/`dbc_gate` threshold zmieniony z -1% na +1%, SWIADOMIE ODCHODZAC od
    zweryfikowanego zachowania starego silnika (ideas_out/best17_3m_tlt_dtla_40, ktory uzywal
    -1% - IAU byl eligibilny w maju 2026 przy mom_r3_gate ~-0.97%, bo to bylo > -1%; teraz przy
    +1% ten sam maj 2026 jest JUZ ZABLOKOWANY, -0.97% < +1%). Ten test weryfikuje mechanike
    NOWEGO progu na realnym przejsciu: styczen 2025 (mom_r3_gate ~-0.04%, ponizej +1% ->
    zablokowany) -> luty 2025 (mom_r3_gate ~+3.00%, powyzej +1% -> eligibilny)."""
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.blocks.indicators import REGISTRY as INDICATORS_REGISTRY

    spec = _load_spec()
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)
    market_data = LOADER_REGISTRY["stooq_csv"](spec.universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})

    mom_r3_gate = INDICATORS_REGISTRY["momentum_monthly"](market_data, {"window": 3})

    threshold = spec.base_params["asset_filters"]["iau_gate"]["threshold"]
    assert threshold == pytest.approx(0.01)
    assert mom_r3_gate.loc["2025-01-01", "iau.us"] <= threshold  # zablokowany
    assert mom_r3_gate.loc["2025-02-01", "iau.us"] > threshold  # eligibilny
    # maj 2026 - PRZED poprawka byl eligibilny (proba -1%), TERAZ zablokowany (+1%)
    assert mom_r3_gate.loc["2026-05-01", "iau.us"] <= threshold


def test_best17_a_full_chain_on_real_data(us_data_dir):
    spec = _load_spec()
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)

    assert final_portfolio["date"].is_monotonic_increasing
    assert len(final_portfolio) > 12
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)

    # w historii musialy wystapic oba rezymy: risk-on (co najmniej 1 aktywo trzymane) i
    # risk-off/cash (kanarek zly, VT wykluczony z selekcji wiec caly portfel w _CASH albo rebound)
    universe = set(spec.universe) - {"vt.us"}  # vt.us to tylko kanarek, never_eligible do selekcji
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

    # nigdy wiecej niz top_n aktywow naraz (poza vt.us, ktory nigdy nie jest selekcjonowany)
    top_n = spec.base_params["selector"]["top_n"]
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        held = sum(1 for t in universe if weights.get(t, 0.0) > 1e-9)
        assert held <= top_n


def test_best17_a_metrics_regression_baseline(us_data_dir):
    """Zamrozony wynik na realnych danych (2026-07-15, PO poprawce progu iau_gate/dbc_gate
    -1%->+1%, patrz CHANGELOG) - lapie regresje w blokach uzywanych przez best17_a
    (canary_regime_gate, rebound_starter, score_gap_hysteresis, rank_weights) bez potrzeby
    przechowywania calej tabeli FINAL PORTFOLIO. Poprzednia baseline (prog -1%, przed poprawka):
    cagr=0.1674, max_drawdown=-0.3119, sharpe=0.961."""
    from engine_v2.backtest_engine import daily_equity_curve
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.metrics import compute_metrics

    spec = _load_spec()
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)
    market_data = LOADER_REGISTRY["stooq_csv"](spec.universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})
    equity_curve = daily_equity_curve(final_portfolio, market_data.prices, {})
    metrics = compute_metrics(equity_curve, final_portfolio, {})

    assert metrics["cagr"] == pytest.approx(0.1512, abs=0.01)
    assert metrics["max_drawdown"] == pytest.approx(-0.3119, abs=0.01)
    assert metrics["sharpe"] == pytest.approx(0.883, abs=0.05)


def test_best17_a_uk_mapping_end_to_end(us_data_dir, uk_data_dir):
    """"Ostateczny test" (user) - realny `run_spec.json` (uk_mapping.enabled=true) na
    PRAWDZIWYCH danych US i UK. Zamrozony baseline (2026-07-12): VT->`vwra.uk` teraz zmapowane
    (user: "dlaczego celowo bez mapowania, skoro vwra istnieje?" - VT to nie tylko sygnal kanarka,
    `rebound_starter` REALNIE go trzyma, brak mapowania oznaczal cash zamiast ekspozycji w tych
    miesiacach). Okno UK jest KROTSZE niz US (`vwra.uk` debiutuje najpozniej ze wszystkich
    uzywanych tickerow, 2019-07-26) - zero mismatch oczekiwane (pelne pokrycie 5/5 tickerow)."""
    from engine_v2.run_spec import RunSpec
    from engine_v2.run_spec_runner import run
    from engine_v2.test_spec import TestSpec

    strategy_dir = REPO_ROOT / "strategies_v2" / "best17_a"
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
    assert abs(uk_result["comparison"]["cagr_gap"]) < 0.05
    assert abs(uk_result["comparison"]["max_drawdown_gap"]) < 0.05
