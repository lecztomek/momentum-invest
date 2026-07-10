"""
Testy regresyjne ALPHA WEIGHTING ("rank_weights").

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_alpha_weighting.py -v
"""

import numpy as np
import pandas as pd
import pytest

from engine_v2.blocks.alpha_weighting import REGISTRY as ALPHA_WEIGHTING_REGISTRY
from engine_v2.blocks.asset_filters import REGISTRY as ASSET_FILTERS_REGISTRY
from engine_v2.blocks.asset_scoring import REGISTRY as ASSET_SCORING_REGISTRY
from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
from engine_v2.blocks.indicators import REGISTRY as INDICATORS_REGISTRY
from engine_v2.blocks.selector import REGISTRY as SELECTOR_REGISTRY

rank_weights = ALPHA_WEIGHTING_REGISTRY["rank_weights"]


def _score_and_selection():
    idx = pd.date_range("2021-01-01", periods=3, freq="MS")
    score = pd.DataFrame(
        {
            "a": [3.0, np.nan, 1.0],
            "b": [1.0, 2.0, 2.0],
            "c": [2.0, 1.0, np.nan],
        },
        index=idx,
    )
    selection = pd.DataFrame(
        {
            "a": [True, False, False],
            "b": [False, True, True],
            "c": [True, True, False],
        },
        index=idx,
    )
    return score, selection


def test_requires_weights():
    score, selection = _score_and_selection()
    with pytest.raises(ValueError, match="weights"):
        rank_weights(selection, score, {}, {})


def test_assigns_by_rank_and_fills_cash():
    score, selection = _score_and_selection()
    out = rank_weights(selection, score, {}, {"weights": [0.8, 0.2]})

    # 2021-01: wybrane a(3.0),c(2.0) -> a=0.8 (lepszy), c=0.2, cash=0
    row = out.loc["2021-01-01"]
    assert row["a"] == pytest.approx(0.8)
    assert row["c"] == pytest.approx(0.2)
    assert row["b"] == 0.0
    assert row["_CASH"] == pytest.approx(0.0)

    # 2021-02: wybrane b(2.0),c(1.0) -> b=0.8, c=0.2
    row = out.loc["2021-02-01"]
    assert row["b"] == pytest.approx(0.8)
    assert row["c"] == pytest.approx(0.2)

    assert (out.sum(axis=1) - 1.0).abs().max() < 1e-9  # kazdy wiersz sumuje sie do 1


def test_fewer_selected_than_weights_fills_remainder_to_cash():
    score, selection = _score_and_selection()
    out = rank_weights(selection, score, {}, {"weights": [0.8, 0.2]})

    # 2021-03: wybrane tylko b -> b=0.8 (najlepszy rangowo), reszta 0.2 do cash (NIE renormalizujemy)
    row = out.loc["2021-03-01"]
    assert row["b"] == pytest.approx(0.8)
    assert row["a"] == 0.0
    assert row["_CASH"] == pytest.approx(0.2)


def test_fewer_selected_than_weights_redistributes_when_flag_set():
    score, selection = _score_and_selection()
    out = rank_weights(selection, score, {}, {"weights": [0.8, 0.2], "redistribute_if_short": True})

    # 2021-03: wybrane tylko b -> renormalizacja weights[:1]=[0.8] do sumy 1.0 -> b=1.0, brak cash
    row = out.loc["2021-03-01"]
    assert row["b"] == pytest.approx(1.0)
    assert row["a"] == 0.0
    assert row["_CASH"] == pytest.approx(0.0)

    # 2021-02: 2 wybrane (pelna liczba wag) - flaga nie zmienia nic
    row = out.loc["2021-02-01"]
    assert row["b"] == pytest.approx(0.8)
    assert row["c"] == pytest.approx(0.2)
    assert row["_CASH"] == pytest.approx(0.0)


def test_no_selection_is_full_cash():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    score = pd.DataFrame({"a": [1.0]}, index=idx)
    selection = pd.DataFrame({"a": [False]}, index=idx)

    out = rank_weights(selection, score, {}, {"weights": [1.0]})
    assert out.loc[idx[0], "_CASH"] == pytest.approx(1.0)
    assert out.loc[idx[0], "a"] == 0.0


def test_more_selected_than_weights_raises():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    score = pd.DataFrame({"a": [1.0], "b": [2.0]}, index=idx)
    selection = pd.DataFrame({"a": [True], "b": [True]}, index=idx)

    with pytest.raises(ValueError, match="wybranych tickerow"):
        rank_weights(selection, score, {}, {"weights": [1.0]})


def test_full_chain_on_real_data(us_data_dir, us_universe):
    stooq_csv = LOADER_REGISTRY["stooq_csv"]
    sma_daily = INDICATORS_REGISTRY["sma_daily"]
    momentum_monthly = INDICATORS_REGISTRY["momentum_monthly"]
    price_above_indicator = ASSET_FILTERS_REGISTRY["price_above_indicator"]
    weighted_sum = ASSET_SCORING_REGISTRY["weighted_sum"]
    top_n = SELECTOR_REGISTRY["top_n"]

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

    weights = rank_weights(selection, score, indicator_set, {"weights": [0.8, 0.2]})

    assert list(weights.columns) == us_universe + ["_CASH"]
    assert (weights.sum(axis=1) - 1.0).abs().max() < 1e-9
    assert (weights.drop(columns="_CASH") >= 0).all().all()
    assert (weights["_CASH"] >= 0).all()
