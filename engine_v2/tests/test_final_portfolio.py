"""
Testy regresyjne FINAL PORTFOLIO - w tym jeden PELNY test end-to-end calego silnika (wszystkie
bloki FAZY A + petla FAZY B) na prawdziwych danych, pierwszy raz spiete razem.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_final_portfolio.py -v
"""

import json

import pandas as pd
import pytest

from engine_v2.blocks.alpha_weighting import REGISTRY as ALPHA_WEIGHTING_REGISTRY
from engine_v2.blocks.asset_filters import REGISTRY as ASSET_FILTERS_REGISTRY
from engine_v2.blocks.asset_scoring import REGISTRY as ASSET_SCORING_REGISTRY
from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
from engine_v2.blocks.execution import REGISTRY as EXECUTION_REGISTRY
from engine_v2.blocks.indicators import REGISTRY as INDICATORS_REGISTRY
from engine_v2.blocks.overlays import REGISTRY as OVERLAYS_REGISTRY
from engine_v2.blocks.portfolio_risk_engine import REGISTRY as PORTFOLIO_RISK_ENGINE_REGISTRY
from engine_v2.blocks.selector import REGISTRY as SELECTOR_REGISTRY
from engine_v2.final_portfolio import build_final_portfolio
from engine_v2.types import ExecutionContext, OverlayContext, PeriodExecutionResult, PortfolioState


def _fake_result(date, weights_used, turnover=0.0):
    return PeriodExecutionResult(
        date=date,
        weights_used=weights_used,
        signal_changed=turnover > 0,
        turnover=turnover,
        operations=len(weights_used),
        trade_cost=0.0,
        gross_return=0.01,
        net_return=0.01,
    )


def test_raises_on_empty_results():
    with pytest.raises(ValueError, match="pusta lista"):
        build_final_portfolio([], "strat")


def test_basic_shape_and_json_roundtrip():
    results = [
        _fake_result(pd.Timestamp("2021-02-01"), {"a": 1.0}, turnover=0.5),
        _fake_result(pd.Timestamp("2021-01-01"), {"_CASH": 1.0}, turnover=0.0),
    ]

    df = build_final_portfolio(results, "example_v0")

    assert list(df.columns) == [
        "date", "strategy", "weights_used_json", "signal_changed", "turnover",
        "operations", "gross_return", "net_return", "trade_cost",
    ]
    # posortowane po dacie, mimo ze w wejsciu byly odwrotnie
    assert df["date"].tolist() == [pd.Timestamp("2021-01-01"), pd.Timestamp("2021-02-01")]
    assert (df["strategy"] == "example_v0").all()
    assert json.loads(df.iloc[1]["weights_used_json"]) == {"a": 1.0}


def test_full_engine_chain_on_real_data(us_data_dir, us_universe):
    stooq_csv = LOADER_REGISTRY["stooq_csv"]
    sma_daily = INDICATORS_REGISTRY["sma_daily"]
    momentum_monthly = INDICATORS_REGISTRY["momentum_monthly"]
    price_above_indicator = ASSET_FILTERS_REGISTRY["price_above_indicator"]
    weighted_sum = ASSET_SCORING_REGISTRY["weighted_sum"]
    top_n = SELECTOR_REGISTRY["top_n"]
    rank_weights = ALPHA_WEIGHTING_REGISTRY["rank_weights"]
    risk_none = PORTFOLIO_RISK_ENGINE_REGISTRY["none"]
    overlay_none = OVERLAYS_REGISTRY["none"]
    hysteresis = EXECUTION_REGISTRY["hysteresis"]

    # ---- FAZA A (cala historia naraz) ----
    md = stooq_csv(us_universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})
    indicator_set = {
        "sma_200": sma_daily(md, {"window": 200}),
        "mom_3": momentum_monthly(md, {"window": 3}),
        "mom_6": momentum_monthly(md, {"window": 6}),
        "mom_12": momentum_monthly(md, {"window": 12}),
    }
    eligibility = price_above_indicator(md, indicator_set, {"indicator_key": "sma_200"})
    score = weighted_sum(
        md, indicator_set, eligibility, {"weights": {"mom_3": 0.5, "mom_6": 0.3, "mom_12": 0.2}}
    )
    selection = top_n(score, {"top_n": 2})
    target_weights = rank_weights(selection, score, indicator_set, {"weights": [0.8, 0.2]})
    target_weights = risk_none(target_weights, md, indicator_set, score, {})

    # tylko okresy z pelnym scorem (bez rozgrzewki na poczatku historii)
    usable_dates = score.dropna(how="all").index
    target_weights = target_weights.loc[usable_dates]

    # ---- FAZA B (okres po okresie) ----
    state = PortfolioState()
    results = []
    for date in target_weights.index:
        row = target_weights.loc[date]

        overlay_ctx = OverlayContext(date=date, state=state, market_data=md)
        row = overlay_none(row, overlay_ctx, {})

        returns_row = md.returns.loc[date] if date in md.returns.index else pd.Series(dtype=float)
        exec_ctx = ExecutionContext(date=date, state=state, returns_row=returns_row)
        result = hysteresis(row, exec_ctx, {"hysteresis_pct": 0.05})

        results.append(result)
        state.current_weights = result.weights_used

    final_portfolio = build_final_portfolio(results, "example_v0")

    assert len(final_portfolio) == len(usable_dates)
    assert final_portfolio["date"].is_monotonic_increasing
    # kazdy wiersz wag (po zdekodowaniu json) sumuje sie do ~1
    for weights_json in final_portfolio["weights_used_json"]:
        weights = json.loads(weights_json)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)
    # co najmniej jeden rebalans musial sie zdarzyc w calej historii
    assert final_portfolio["signal_changed"].any()
