"""
Testy dla strategies_v2/synergy_v1/ i strategies_v2/synergy_v2/ - eksperymentalna proba zlozenia
JEDNEGO nowego pipeline'u z pomyslow best17_a (kanarek+rebound+gates+histereza) i the_one/GEM
(absolutny momentum na obligacji jako warunek eligibilnosci), zamiast combinera dwoch gotowych
strategii. Patrz "hypothesis" w kazdym strategy_spec.json i CHANGELOG.md.

synergy_v1: TLT.us konkuruje w TYM SAMYM rankingu co XLK/IVV/DBC/IAU (eligibilny zawsze, gdy ma
dodatni 12m momentum) - wynik: GORZEJ niz best17_a solo na kazdej metryce (crowding-out).
synergy_v2: TLT.us i 4 aktywa ofensywne sa wzajemnie WYKLUCZAJACE SIE (nowy param
`invert` w canary_regime_gate) - mechanizm dziala (TLT wchodzi realnie w kryzysie 2008-09), ale
CAGR/Sharpe/MaxDD nadal NIE biją best17_a solo (najgorszy rok kalendarzowy identyczny jak solo -
2022, gdzie TLT rowniez mial ujemny momentum, wiec bramka nie uratowala akurat tam, gdzie
bylaby najbardziej potrzebna).

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_synergy_strategy_specs.py -v
"""

import json
from pathlib import Path

import pytest

from engine_v2.pipeline import resolve_blocks, run_strategy_pipeline
from engine_v2.spec import StrategySpec

REPO_ROOT = Path(__file__).resolve().parents[2]
STRATS = REPO_ROOT / "strategies_v2"

NAMES = ["synergy_v1", "synergy_v2"]


def _load_spec(name: str) -> StrategySpec:
    return StrategySpec.load(STRATS / name / "strategy_spec.json")


@pytest.mark.parametrize("name", NAMES)
def test_synergy_spec_is_valid(name):
    spec = _load_spec(name)
    assert spec.validate() == []


@pytest.mark.parametrize("name", NAMES)
def test_synergy_spec_resolves_all_blocks(name):
    spec = _load_spec(name)
    resolved = resolve_blocks(spec)
    for block_type in spec.blocks:
        assert block_type in resolved


@pytest.mark.parametrize("name", NAMES)
def test_synergy_full_chain_on_real_data(name, us_data_dir):
    spec = _load_spec(name)
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)

    assert final_portfolio["date"].is_monotonic_increasing
    assert len(final_portfolio) > 12
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)


def test_synergy_v2_tlt_and_offensive_assets_never_held_together(us_data_dir):
    """Rdzen hipotezy synergy_v2 - TLT.us wzajemnie wykluczajacy sie z XLK/IVV/DBC/IAU w KAZDYM
    miesiacu (invert=True na tym samym kanarku), w odroznieniu od synergy_v1."""
    spec = _load_spec("synergy_v2")
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)
    final_portfolio = run_strategy_pipeline(spec)

    offensive = {"xlk.us", "ivv.us", "dbc.us", "iau.us"}
    saw_tlt = False
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        holds_tlt = weights.get("tlt.us", 0.0) > 1e-9
        holds_offensive = any(weights.get(t, 0.0) > 1e-9 for t in offensive)
        assert not (holds_tlt and holds_offensive)
        saw_tlt = saw_tlt or holds_tlt
    assert saw_tlt  # mechanizm faktycznie sie aktywuje (np. kryzys 2008-09), nie martwy kod


def test_synergy_v1_metrics_regression_baseline(us_data_dir):
    """Zamrozony wynik (2026-07-15, PRZED podatkiem, PO poprawce progu best17_a's
    iau_gate/dbc_gate -1%->+1%, patrz CHANGELOG) - crowding-out: gorzej niz best17_a solo.
    Poprzednia baseline (prog -1%): cagr=0.1445, maxdd=-0.2819, sharpe=0.86."""
    from engine_v2.backtest_engine import daily_equity_curve
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.metrics import compute_metrics

    spec = _load_spec("synergy_v1")
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)
    market_data = LOADER_REGISTRY["stooq_csv"](spec.universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})
    equity_curve = daily_equity_curve(final_portfolio, market_data.prices, {})
    metrics = compute_metrics(equity_curve, final_portfolio, {})

    assert metrics["cagr"] == pytest.approx(0.1298, abs=0.01)
    assert metrics["max_drawdown"] == pytest.approx(-0.2819, abs=0.01)
    assert metrics["sharpe"] == pytest.approx(0.788, abs=0.05)


def test_synergy_v2_metrics_regression_baseline(us_data_dir):
    """Zamrozony wynik (2026-07-15, PRZED podatkiem, PO poprawce progu best17_a's
    iau_gate/dbc_gate -1%->+1%, patrz CHANGELOG) - blisko, ale wciaz ponizej best17_a solo.
    Poprzednia baseline (prog -1%): cagr=0.1626, maxdd=-0.3119, sharpe=0.92."""
    from engine_v2.backtest_engine import daily_equity_curve
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.metrics import compute_metrics

    spec = _load_spec("synergy_v2")
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)
    market_data = LOADER_REGISTRY["stooq_csv"](spec.universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})
    equity_curve = daily_equity_curve(final_portfolio, market_data.prices, {})
    metrics = compute_metrics(equity_curve, final_portfolio, {})

    assert metrics["cagr"] == pytest.approx(0.1464, abs=0.01)
    assert metrics["max_drawdown"] == pytest.approx(-0.3119, abs=0.01)
    assert metrics["sharpe"] == pytest.approx(0.844, abs=0.05)
