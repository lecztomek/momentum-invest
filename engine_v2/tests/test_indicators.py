"""
Testy regresyjne INDICATORS ("sma_daily", "momentum_monthly"). Kombinacja: syntetyczne dane
(deterministyczne, latwe do recznego wyliczenia oczekiwanej wartosci) + jeden sanity check na
prawdziwych danych z `data/us`.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_indicators.py -v
"""

import numpy as np
import pandas as pd
import pytest

from engine_v2.blocks.indicators import REGISTRY as INDICATORS_REGISTRY
from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
from engine_v2.types import MarketData

sma_daily = INDICATORS_REGISTRY["sma_daily"]
momentum_monthly = INDICATORS_REGISTRY["momentum_monthly"]


def _daily_market_data(rows: int, start: str = "2020-01-01") -> MarketData:
    idx = pd.date_range(start, periods=rows, freq="D")
    prices = pd.DataFrame({"a": np.arange(1.0, rows + 1)}, index=idx)
    return MarketData(prices=prices, returns=prices.pct_change())


def test_sma_daily_requires_window():
    md = _daily_market_data(10)
    with pytest.raises(ValueError, match="window"):
        sma_daily(md, {})


def test_sma_daily_matches_manual_rolling_mean():
    md = _daily_market_data(10)
    out = sma_daily(md, {"window": 3})

    assert out["a"].iloc[:2].isna().all()  # za malo danych na pierwsze 2 wiersze
    assert out["a"].iloc[2] == pytest.approx((1.0 + 2.0 + 3.0) / 3)
    assert out["a"].iloc[-1] == pytest.approx((8.0 + 9.0 + 10.0) / 3)


def test_momentum_monthly_matches_manual_calc():
    # 6 miesiecy, cena podwaja sie co miesiac: 1, 2, 4, 8, 16, 32 (na starcie kazdego miesiaca)
    idx = pd.date_range("2020-01-01", "2020-06-30", freq="D")
    prices = pd.DataFrame(index=idx)
    month_starts = pd.date_range("2020-01-01", periods=6, freq="MS")
    values = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0]
    prices["a"] = np.nan
    for date, value in zip(month_starts, values):
        prices.loc[date, "a"] = value
    prices["a"] = prices["a"].ffill()

    md = MarketData(prices=prices, returns=prices.pct_change())
    out = momentum_monthly(md, {"window": 3})

    # kwiecien (8.0) vs styczen (1.0), 3 miesiace wstecz -> 8.0/1.0 - 1 = 7.0 (700%)
    assert out.loc["2020-04-01", "a"] == pytest.approx(7.0)
    # maj (16.0) vs luty (2.0) -> 7.0
    assert out.loc["2020-05-01", "a"] == pytest.approx(7.0)
    # styczen/luty/marzec: mniej niz 3 miesiace historii -> NaN
    assert out.loc["2020-01-01":"2020-03-01", "a"].isna().all()


def test_momentum_monthly_requires_window():
    md = _daily_market_data(100)
    with pytest.raises(ValueError, match="window"):
        momentum_monthly(md, {})


def test_indicators_on_real_data_produce_expected_shapes(us_data_dir, us_universe):
    md = LOADER_REGISTRY["stooq_csv"](us_universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})

    sma_200 = sma_daily(md, {"window": 200})
    mom_12 = momentum_monthly(md, {"window": 12})

    assert list(sma_200.columns) == us_universe
    assert sma_200.index.equals(md.prices.index)  # sma_daily zostaje na siatce dziennej

    assert list(mom_12.columns) == us_universe
    assert mom_12.index.is_monotonic_increasing
    # po pierwszym roku danych momentum powinno byc juz policzone (nie-NaN) dla kazdego tickera
    assert mom_12.dropna(how="all").shape[0] > 0
