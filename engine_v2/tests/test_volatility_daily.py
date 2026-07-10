"""
Testy regresyjne INDICATORS ("volatility_daily").

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_volatility_daily.py -v
"""

import numpy as np
import pandas as pd
import pytest

from engine_v2.blocks.indicators import REGISTRY as INDICATORS_REGISTRY
from engine_v2.types import MarketData

volatility_daily = INDICATORS_REGISTRY["volatility_daily"]


def test_requires_window():
    idx = pd.date_range("2021-01-01", periods=10, freq="D")
    md = MarketData(prices=pd.DataFrame({"a": range(10)}, index=idx, dtype=float), returns=pd.DataFrame())
    with pytest.raises(ValueError, match="window"):
        volatility_daily(md, {})


def test_rejects_window_below_two():
    idx = pd.date_range("2021-01-01", periods=10, freq="D")
    md = MarketData(prices=pd.DataFrame({"a": range(10)}, index=idx, dtype=float), returns=pd.DataFrame())
    with pytest.raises(ValueError, match="window"):
        volatility_daily(md, {"window": 1})


def test_matches_manual_std_unannualized():
    idx = pd.date_range("2021-01-01", periods=6, freq="D")
    prices = pd.DataFrame({"a": [100.0, 101.0, 99.0, 102.0, 98.0, 103.0]}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())

    out = volatility_daily(md, {"window": 3, "annualize": False})

    manual_returns = prices["a"].pct_change()
    expected = manual_returns.rolling(window=3, min_periods=3).std()
    pd.testing.assert_series_equal(out["a"], expected, check_names=False)


def test_annualize_scales_by_sqrt_252():
    idx = pd.date_range("2021-01-01", periods=6, freq="D")
    prices = pd.DataFrame({"a": [100.0, 101.0, 99.0, 102.0, 98.0, 103.0]}, index=idx)
    md = MarketData(prices=prices, returns=pd.DataFrame())

    raw = volatility_daily(md, {"window": 3, "annualize": False})
    annualized = volatility_daily(md, {"window": 3, "annualize": True})

    pd.testing.assert_series_equal(
        annualized["a"].dropna(), (raw["a"] * (252 ** 0.5)).dropna(), check_names=False
    )


def test_uses_daily_prices_not_period_returns():
    idx = pd.date_range("2021-01-01", periods=6, freq="D")
    prices = pd.DataFrame({"a": [100.0, 101.0, 99.0, 102.0, 98.0, 103.0]}, index=idx)
    # returns pole (inna czestotliwosc) celowo wypelnione czyms zupelnie innym - nie powinno miec wplywu
    md = MarketData(prices=prices, returns=pd.DataFrame({"a": [999.0]}, index=[idx[0]]))

    out = volatility_daily(md, {"window": 3})
    assert not out["a"].dropna().empty


def test_real_data_shape(us_data_dir, us_universe):
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY

    md = LOADER_REGISTRY["stooq_csv"](us_universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})
    out = volatility_daily(md, {"window": 60})

    assert list(out.columns) == us_universe
    assert out.index.equals(md.prices.index)
    assert (out.dropna() >= 0).all().all()
