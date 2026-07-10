"""
Testy regresyjne SELECTOR ("top_n").

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_selector.py -v
"""

import numpy as np
import pandas as pd
import pytest

from engine_v2.blocks.asset_filters import REGISTRY as ASSET_FILTERS_REGISTRY
from engine_v2.blocks.asset_scoring import REGISTRY as ASSET_SCORING_REGISTRY
from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
from engine_v2.blocks.indicators import REGISTRY as INDICATORS_REGISTRY
from engine_v2.blocks.selector import REGISTRY as SELECTOR_REGISTRY

top_n = SELECTOR_REGISTRY["top_n"]


def _score():
    idx = pd.date_range("2021-01-01", periods=3, freq="MS")
    return pd.DataFrame(
        {
            "a": [3.0, np.nan, 1.0],
            "b": [1.0, 2.0, 2.0],
            "c": [2.0, 1.0, np.nan],
            "d": [np.nan, np.nan, np.nan],
        },
        index=idx,
    )


def test_requires_top_n():
    with pytest.raises(ValueError, match="top_n"):
        top_n(_score(), {})


def test_rejects_non_positive_top_n():
    with pytest.raises(ValueError, match="top_n"):
        top_n(_score(), {"top_n": 0})


def test_picks_highest_scores_per_row():
    selection = top_n(_score(), {"top_n": 2})

    # 2021-01: a=3, c=2, b=1 -> wybrane a i c
    assert selection.loc["2021-01-01"].tolist() == [True, False, True, False]
    # 2021-02: b=2, c=1, a=NaN -> wybrane b i c (tylko 2 eligibilne, wiec i tak max 2)
    assert selection.loc["2021-02-01"].tolist() == [False, True, True, False]
    # 2021-03: b=2, a=1, c=NaN -> wybrane b i a
    assert selection.loc["2021-03-01"].tolist() == [True, True, False, False]


def test_never_selects_nan():
    selection = top_n(_score(), {"top_n": 10})  # top_n wiekszy niz liczba tickerow
    # "d" jest zawsze NaN - nigdy nie moze zostac wybrany, niezaleznie od top_n
    assert not selection["d"].any()
    # kazdy wiersz wybiera co najwyzej tyle ile jest nie-NaN wartosci
    for date in selection.index:
        assert selection.loc[date].sum() == _score().loc[date].notna().sum()


def test_selection_never_exceeds_top_n():
    selection = top_n(_score(), {"top_n": 1})
    assert (selection.sum(axis=1) <= 1).all()


def test_full_chain_on_real_data(us_data_dir, us_universe):
    stooq_csv = LOADER_REGISTRY["stooq_csv"]
    sma_daily = INDICATORS_REGISTRY["sma_daily"]
    momentum_monthly = INDICATORS_REGISTRY["momentum_monthly"]
    price_above_indicator = ASSET_FILTERS_REGISTRY["price_above_indicator"]
    weighted_sum = ASSET_SCORING_REGISTRY["weighted_sum"]

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

    assert list(selection.columns) == us_universe
    assert (selection.sum(axis=1) <= 2).all()
    # nigdy nie wybiera tam gdzie score jest NaN
    assert not (selection & score.isna()).any().any()
