"""
Testy dla strategies_v2/bh_vt/ i strategies_v2/bh_spy/ - proste benchmarki "buy & hold" (zawsze
100% jednego aktywa, zero timingu/rotacji). User: "Czy zapisujemy wyniki benchmarku przy naszych
wyliczeniach? Powinnismy miec prosta strategie buy hold vt z mappingiem vwra oraz druga z sp500 i
mapping uk" - punkt odniesienia w `results/SUMMARY.md` do oceny, czy dodatkowa zlozonosc strategii
momentum w tym repo faktycznie place. Ten sam wzorzec co juz istniejacy `tlt_hedge` (jednoaktywowa
"cegielka", top_n=1 na jednoaktywowym uniwersum, portfolio_risk_engine="none").

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_bh_benchmarks.py -v
"""

from pathlib import Path

import pytest

from engine_v2.pipeline import resolve_blocks, run_strategy_pipeline
from engine_v2.spec import StrategySpec

REPO_ROOT = Path(__file__).resolve().parents[2]

BENCHMARKS = [
    ("bh_vt", "vt.us"),
    ("bh_spy", "spy.us"),
]


def _load_spec(name: str) -> StrategySpec:
    return StrategySpec.load(REPO_ROOT / "strategies_v2" / name / "strategy_spec.json")


@pytest.mark.parametrize("name,ticker", BENCHMARKS, ids=[b[0] for b in BENCHMARKS])
def test_benchmark_spec_is_valid(name, ticker):
    spec = _load_spec(name)
    assert spec.validate() == []
    assert spec.universe == [ticker]


@pytest.mark.parametrize("name,ticker", BENCHMARKS, ids=[b[0] for b in BENCHMARKS])
def test_benchmark_spec_resolves_all_blocks(name, ticker):
    spec = _load_spec(name)
    resolved = resolve_blocks(spec)
    for block_type in spec.blocks:
        assert block_type in resolved


@pytest.mark.parametrize("name,ticker", BENCHMARKS, ids=[b[0] for b in BENCHMARKS])
def test_benchmark_always_holds_100pct_single_asset(name, ticker, us_data_dir):
    import json

    spec = _load_spec(name)
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)
    assert final_portfolio["date"].is_monotonic_increasing
    assert len(final_portfolio) > 12

    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        assert weights.get(ticker, 0.0) == pytest.approx(1.0, abs=1e-6)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)


@pytest.mark.parametrize("name,ticker", BENCHMARKS, ids=[b[0] for b in BENCHMARKS])
def test_benchmark_uk_mapping_end_to_end(name, ticker, us_data_dir, uk_data_dir):
    """Mismatch 0% oczekiwane zawsze - jeden ticker, zawsze zmapowany, nigdy nie wpada w cash."""
    from engine_v2.run_spec import RunSpec
    from engine_v2.run_spec_runner import run
    from engine_v2.test_spec import TestSpec

    strategy_dir = REPO_ROOT / "strategies_v2" / name
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
    assert uk_result["comparison"]["monthly_return_correlation"] > 0.95
    assert abs(uk_result["comparison"]["cagr_gap"]) < 0.05
    assert abs(uk_result["comparison"]["max_drawdown_gap"]) < 0.05
