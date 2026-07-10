"""
Testy regresyjne DATA CLEANER (`trim_and_interpolate`). W pelni syntetyczne dane (male,
reczne DataFrame'y) - szybkie, deterministyczne, niezalezne od tego co jest w `data/`.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_data_cleaner.py -v
"""

import numpy as np
import pandas as pd
import pytest

from engine_v2.blocks.data_cleaner import REGISTRY as CLEANER_REGISTRY
from engine_v2.types import MarketData

trim_and_interpolate = CLEANER_REGISTRY["trim_and_interpolate"]


def _panel(rows: int, start: str = "2020-01-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=rows, freq="D")
    return pd.DataFrame(
        {"a": np.arange(1.0, rows + 1), "b": np.arange(1.0, rows + 1) * 10},
        index=idx,
    )


def test_trims_to_common_start_and_end():
    prices = _panel(10)
    prices.loc[prices.index[:3], "a"] = np.nan   # "a" zaczyna sie pozniej
    prices.loc[prices.index[-2:], "b"] = np.nan  # "b" konczy sie wczesniej
    md = MarketData(prices=prices, returns=prices.copy())

    out = trim_and_interpolate(md, {})

    assert out.prices.index.min() == prices.index[3]
    assert out.prices.index.max() == prices.index[-3]
    assert not out.prices.isna().any().any()


def test_fills_small_internal_gap_via_interpolation():
    prices = _panel(10)
    prices.loc[prices.index[4], "a"] = np.nan  # dziura 1 wiersz, w srodku

    md = MarketData(prices=prices, returns=prices.copy())
    out = trim_and_interpolate(md, {})

    expected = (prices["a"].iloc[3] + prices["a"].iloc[5]) / 2
    assert out.prices["a"].iloc[4] == pytest.approx(expected)
    assert not out.prices.isna().any().any()


def test_max_gap_leaves_long_gap_unfilled():
    prices = _panel(20)
    prices.loc[prices.index[5:15], "a"] = np.nan  # dziura 10 wierszy

    md = MarketData(prices=prices, returns=prices.copy())
    out = trim_and_interpolate(md, {"max_gap": 3})

    assert out.prices["a"].isna().sum() > 0  # zbyt duza dziura - nie zgadujemy na sile


def test_no_max_gap_fills_everything_inside_range():
    prices = _panel(20)
    prices.loc[prices.index[5:15], "a"] = np.nan

    md = MarketData(prices=prices, returns=prices.copy())
    out = trim_and_interpolate(md, {})

    assert not out.prices.isna().any().any()


def test_prices_and_returns_cleaned_independently():
    prices = _panel(10)
    returns = _panel(10, start="2021-01-01")
    returns.loc[returns.index[:2], "a"] = np.nan

    md = MarketData(prices=prices, returns=returns)
    out = trim_and_interpolate(md, {})

    assert out.prices.index.min() == prices.index[0]      # prices bez luk na starcie
    assert out.returns.index.min() == returns.index[2]    # returns przyciete niezaleznie


def test_no_common_valid_row_raises():
    prices = _panel(5)
    prices.loc[prices.index[0], "a"] = np.nan
    prices.loc[prices.index[1:], "b"] = np.nan  # zaden wiersz nie ma obu kolumn naraz

    md = MarketData(prices=prices, returns=prices.copy())
    with pytest.raises(ValueError, match="wspolnego zakresu"):
        trim_and_interpolate(md, {})
