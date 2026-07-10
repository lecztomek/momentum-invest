"""
Testy regresyjne GRID SWEEP ("expand_param_grid" + "run_param_sweep").

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_grid_sweep.py -v
"""

from pathlib import Path

import pytest

from engine_v2.grid_sweep import expand_param_grid, run_param_sweep
from engine_v2.spec import StrategySpec


def _base_spec(allowed_param_families):
    return StrategySpec(
        name="base",
        hypothesis="test",
        universe=["a.us"],
        blocks={"execution": "hysteresis"},
        base_params={"execution": {"hysteresis_pct": 0.05}},
        allowed_param_families=allowed_param_families,
    )


def test_raises_on_empty_allowed_param_families():
    spec = _base_spec({})
    with pytest.raises(ValueError, match="puste"):
        expand_param_grid(spec)


def test_raises_on_multi_instance_block():
    spec = _base_spec({"indicators": {"window": [100, 200]}})
    with pytest.raises(ValueError, match="wielo-instancyjny"):
        expand_param_grid(spec)


def test_raises_on_empty_value_list():
    spec = _base_spec({"execution": {"hysteresis_pct": []}})
    with pytest.raises(ValueError, match="pusta liste"):
        expand_param_grid(spec)


def test_cartesian_product_across_two_blocks():
    spec = StrategySpec(
        name="base",
        hypothesis="test",
        universe=["a.us"],
        blocks={"execution": "hysteresis", "selector": "top_n"},
        base_params={"execution": {"hysteresis_pct": 0.05}, "selector": {"top_n": 2}},
        allowed_param_families={
            "execution": {"hysteresis_pct": [0.0, 0.05]},
            "selector": {"top_n": [1, 2, 3]},
        },
    )

    variants = expand_param_grid(spec)

    assert len(variants) == 2 * 3
    combos = {
        (v.base_params["execution"]["hysteresis_pct"], v.base_params["selector"]["top_n"])
        for v in variants
    }
    assert combos == {(h, n) for h in (0.0, 0.05) for n in (1, 2, 3)}
    # kazdy wariant ma unikalna nazwe
    assert len({v.name for v in variants}) == len(variants)


def test_single_axis_sweep_values():
    spec = _base_spec({"execution": {"hysteresis_pct": [0.0, 0.025, 0.05]}})
    variants = expand_param_grid(spec)

    assert len(variants) == 3
    values = sorted(v.base_params["execution"]["hysteresis_pct"] for v in variants)
    assert values == [0.0, 0.025, 0.05]
    # base spec sam nie jest zmutowany
    assert spec.base_params["execution"]["hysteresis_pct"] == 0.05


def test_run_param_sweep_calls_evaluate_fn_per_variant_and_reports_param_values():
    spec = _base_spec({"execution": {"hysteresis_pct": [0.0, 0.05, 0.10]}})

    def fake_evaluate(variant):
        return {"score": variant.base_params["execution"]["hysteresis_pct"] * 100}

    result = run_param_sweep(spec, fake_evaluate)

    assert len(result) == 3
    assert set(result.columns) == {"variant_name", "execution.hysteresis_pct", "score"}
    assert sorted(result["score"]) == [0.0, 5.0, 10.0]


def test_full_chain_on_real_example_strategy(us_data_dir, us_universe):
    from engine_v2.backtest_engine import daily_equity_curve
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.metrics import compute_metrics
    from engine_v2.pipeline import run_strategy_pipeline

    repo_root = Path(__file__).resolve().parents[2]
    base_spec = StrategySpec.load(repo_root / "strategies_v2" / "example_strategy" / "strategy_spec.json")
    base_spec.universe = us_universe
    base_spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    market_data = LOADER_REGISTRY["stooq_csv"](us_universe, {"data_dir": str(us_data_dir), "frequency": "daily"})

    def evaluate(variant_spec):
        final_portfolio = run_strategy_pipeline(variant_spec)
        equity_curve = daily_equity_curve(final_portfolio, market_data.prices, {})
        return compute_metrics(equity_curve, final_portfolio, {})

    result = run_param_sweep(base_spec, evaluate)

    assert len(result) == 5  # 5 wartosci hysteresis_pct w przykladowej strategii
    assert result["execution.hysteresis_pct"].tolist() == [0.0, 0.025, 0.05, 0.075, 0.10]
    assert result["cagr"].notna().all()
    # wyzszy prog histerezy = mniej rebalansow = na ogol nizszy roczny turnover
    low = result.loc[result["execution.hysteresis_pct"] == 0.0, "annual_turnover"].iloc[0]
    high = result.loc[result["execution.hysteresis_pct"] == 0.10, "annual_turnover"].iloc[0]
    assert high <= low
