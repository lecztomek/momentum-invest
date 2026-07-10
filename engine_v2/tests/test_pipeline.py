"""
Testy regresyjne PIPELINE (orchestrator) - w tym porownanie z rowno-wazna reczna petla (ten sam
wynik, dowod ze `run_strategy_pipeline` nie zgubil zadnego kroku).

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_pipeline.py -v
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from engine_v2.pipeline import resolve_blocks, run_strategy_pipeline
from engine_v2.spec import StrategySpec

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_SPEC_PATH = REPO_ROOT / "strategies_v2" / "example_strategy" / "strategy_spec.json"


def _load_example_spec() -> StrategySpec:
    return StrategySpec.load(EXAMPLE_SPEC_PATH)


def test_example_spec_resolves_all_blocks(us_data_dir):
    spec = _load_example_spec()
    resolved = resolve_blocks(spec)
    # kazdy pojedynczo-wyborowy blok z `blocks` ma odpowiadajaca implementacje w wyniku
    for block_type, impl_name in spec.blocks.items():
        assert block_type in resolved


def test_missing_required_block_raises():
    spec = _load_example_spec()
    del spec.blocks["execution"]
    del spec.base_params["execution"]
    del spec.allowed_param_families["execution"]

    assert spec.validate() == []  # spec sam w sobie spojny - brakuje tylko wyboru execution

    with pytest.raises(ValueError, match="nie deklaruje wymaganych blokow"):
        run_strategy_pipeline(spec)


def test_invalid_spec_raises_before_running():
    spec = _load_example_spec()
    spec.hypothesis = ""  # validate() wymaga niepustej hipotezy

    with pytest.raises(ValueError, match="niepoprawny"):
        run_strategy_pipeline(spec)


def test_run_strategy_pipeline_end_to_end(us_data_dir, us_universe):
    spec = _load_example_spec()
    spec.universe = us_universe
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)

    final_portfolio = run_strategy_pipeline(spec)

    assert final_portfolio["date"].is_monotonic_increasing
    assert (final_portfolio["strategy"] == spec.name).all()
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)
    assert final_portfolio["signal_changed"].any()


def test_pipeline_matches_manual_wiring(us_data_dir, us_universe):
    """Ten sam efekt co reczna petla w test_final_portfolio.py::test_full_engine_chain_on_real_data
    - dowod ze orchestrator nie zmienia wynikow, tylko automatyzuje okablowanie."""
    from engine_v2.blocks.alpha_weighting import REGISTRY as ALPHA_WEIGHTING_REGISTRY
    from engine_v2.blocks.asset_filters import REGISTRY as ASSET_FILTERS_REGISTRY
    from engine_v2.blocks.asset_scoring import REGISTRY as ASSET_SCORING_REGISTRY
    from engine_v2.blocks.data_cleaner import REGISTRY as DATA_CLEANER_REGISTRY
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
    from engine_v2.blocks.execution import REGISTRY as EXECUTION_REGISTRY
    from engine_v2.blocks.indicators import REGISTRY as INDICATORS_REGISTRY
    from engine_v2.blocks.overlays import REGISTRY as OVERLAYS_REGISTRY
    from engine_v2.blocks.portfolio_risk_engine import REGISTRY as PORTFOLIO_RISK_ENGINE_REGISTRY
    from engine_v2.blocks.selector import REGISTRY as SELECTOR_REGISTRY
    from engine_v2.final_portfolio import build_final_portfolio
    from engine_v2.types import ExecutionContext, OverlayContext, PortfolioState

    raw_md = LOADER_REGISTRY["stooq_csv"](us_universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})
    # wskazniki licza sie na pelnej, wlasnej historii kazdego tickera (skip_common_range_trim) -
    # dopiero potem przycinamy do wspolnego zakresu wykonania i odcinamy rozgrzewke z wynikow
    warmup_md = DATA_CLEANER_REGISTRY["trim_and_interpolate"](raw_md, {"skip_common_range_trim": True})
    indicator_set = {
        "sma_200": INDICATORS_REGISTRY["sma_daily"](warmup_md, {"window": 200}),
        "mom_3": INDICATORS_REGISTRY["momentum_monthly"](warmup_md, {"window": 3}),
        "mom_6": INDICATORS_REGISTRY["momentum_monthly"](warmup_md, {"window": 6}),
        "mom_12": INDICATORS_REGISTRY["momentum_monthly"](warmup_md, {"window": 12}),
    }
    md = DATA_CLEANER_REGISTRY["trim_and_interpolate"](raw_md, {})
    warmup_cutoff = md.prices.index.min()
    indicator_set = {key: df.loc[df.index >= warmup_cutoff] for key, df in indicator_set.items()}
    eligibility = ASSET_FILTERS_REGISTRY["price_above_indicator"](md, indicator_set, {"indicator_key": "sma_200"})
    score = ASSET_SCORING_REGISTRY["weighted_sum"](
        md, indicator_set, eligibility, {"weights": {"mom_3": 0.5, "mom_6": 0.3, "mom_12": 0.2}}
    )
    selection = SELECTOR_REGISTRY["top_n"](score, {"top_n": 2})
    target_weights = ALPHA_WEIGHTING_REGISTRY["rank_weights"](selection, score, indicator_set, {"weights": [0.8, 0.2]})
    target_weights = PORTFOLIO_RISK_ENGINE_REGISTRY["none"](target_weights, md, indicator_set, score, {})

    non_nan_dates = score.index[score.notna().any(axis=1)]
    first_usable_date = non_nan_dates.min()
    target_weights = target_weights.loc[target_weights.index >= first_usable_date]

    state = PortfolioState()
    results = []
    for date in target_weights.index:
        row = target_weights.loc[date]
        row = OVERLAYS_REGISTRY["none"](row, OverlayContext(date=date, state=state, market_data=md), {})
        returns_row = md.returns.loc[date] if date in md.returns.index else pd.Series(dtype=float)
        result = EXECUTION_REGISTRY["hysteresis"](
            row, ExecutionContext(date=date, state=state, returns_row=returns_row), {"hysteresis_pct": 0.05}
        )
        results.append(result)
        state.current_weights = result.weights_used

    manual_final_portfolio = build_final_portfolio(results, "example_v0")

    spec = _load_example_spec()
    spec.universe = us_universe
    spec.base_params["data_loader"]["data_dir"] = str(us_data_dir)
    pipeline_final_portfolio = run_strategy_pipeline(spec)

    pd.testing.assert_frame_equal(
        manual_final_portfolio.reset_index(drop=True), pipeline_final_portfolio.reset_index(drop=True)
    )
