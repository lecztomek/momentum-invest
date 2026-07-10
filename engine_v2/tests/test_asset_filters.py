"""
Testy regresyjne ASSET FILTERS ("price_above_indicator") - w tym mechanizm "assets" (filtr
ograniczony do podzbioru uniwersum, reszta automatycznie przechodzi).

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_asset_filters.py -v
"""

import numpy as np
import pandas as pd
import pytest

from engine_v2.blocks.asset_filters import REGISTRY as ASSET_FILTERS_REGISTRY
from engine_v2.types import MarketData

price_above_indicator = ASSET_FILTERS_REGISTRY["price_above_indicator"]


def _market_data_and_indicator():
    idx = pd.date_range("2020-01-01", periods=5, freq="D")
    prices = pd.DataFrame(
        {
            "a": [10, 10, 10, 10, 10],
            "b": [10, 10, 10, 10, 10],
            "c": [10, 10, 10, 10, 10],
        },
        index=idx,
        dtype=float,
    )
    indicator = pd.DataFrame(
        {
            # "a": zawsze powyzej indykatora, "b": zawsze ponizej, "c": mieszane
            "a": [5, 5, 5, 5, 5],
            "b": [15, 15, 15, 15, 15],
            "c": [5, 15, 5, 15, 5],
        },
        index=idx,
        dtype=float,
    )
    md = MarketData(prices=prices, returns=prices.pct_change())
    return md, {"sma_200": indicator}


def test_requires_indicator_key():
    md, indicator_set = _market_data_and_indicator()
    with pytest.raises(ValueError, match="indicator_key"):
        price_above_indicator(md, indicator_set, {})


def test_unknown_indicator_key_raises():
    md, indicator_set = _market_data_and_indicator()
    with pytest.raises(ValueError, match="Brak wskaznika"):
        price_above_indicator(md, indicator_set, {"indicator_key": "nieistniejacy"})


def test_basic_mask_without_asset_scope():
    md, indicator_set = _market_data_and_indicator()
    mask = price_above_indicator(md, indicator_set, {"indicator_key": "sma_200"})

    assert mask["a"].all()
    assert not mask["b"].any()
    assert mask["c"].tolist() == [True, False, True, False, True]


def test_assets_scope_only_affects_listed_tickers():
    md, indicator_set = _market_data_and_indicator()
    # bez scope "b" nigdy nie przechodzi; ze scope ograniczonym do "a" i "c", "b" ma byc zawsze True
    mask = price_above_indicator(
        md, indicator_set, {"indicator_key": "sma_200", "assets": ["a", "c"]}
    )

    assert mask["a"].all()
    assert mask["b"].all()  # poza zakresem filtra -> automatycznie przechodzi
    assert mask["c"].tolist() == [True, False, True, False, True]


def test_assets_all_is_equivalent_to_default():
    md, indicator_set = _market_data_and_indicator()
    default_mask = price_above_indicator(md, indicator_set, {"indicator_key": "sma_200"})
    explicit_all_mask = price_above_indicator(
        md, indicator_set, {"indicator_key": "sma_200", "assets": "all"}
    )
    pd.testing.assert_frame_equal(default_mask, explicit_all_mask)


def test_unknown_ticker_in_assets_raises():
    md, indicator_set = _market_data_and_indicator()
    with pytest.raises(ValueError, match="nieznane tickery"):
        price_above_indicator(
            md, indicator_set, {"indicator_key": "sma_200", "assets": ["a", "zzz"]}
        )
