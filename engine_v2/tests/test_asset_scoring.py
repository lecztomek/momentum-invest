"""
Testy regresyjne ASSET SCORING ("weighted_sum") - w tym dopasowanie eligibility_mask o innej
czestotliwosci (daily) do indeksu score (monthly), oraz walidacja spojnosci indeksow wazonych
wskaznikow.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_asset_scoring.py -v
"""

import numpy as np
import pandas as pd
import pytest

from engine_v2.blocks.asset_filters import REGISTRY as ASSET_FILTERS_REGISTRY
from engine_v2.blocks.asset_scoring import REGISTRY as ASSET_SCORING_REGISTRY
from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY
from engine_v2.blocks.indicators import REGISTRY as INDICATORS_REGISTRY
from engine_v2.types import MarketData

weighted_sum = ASSET_SCORING_REGISTRY["weighted_sum"]


def _monthly_market_data():
    idx = pd.date_range("2021-01-01", periods=4, freq="MS")
    prices = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0], "b": [1.0, 1.0, 1.0, 1.0]}, index=idx)
    return MarketData(prices=prices, returns=prices.pct_change())


def test_requires_weights():
    md = _monthly_market_data()
    with pytest.raises(ValueError, match="weights"):
        weighted_sum(md, {}, pd.DataFrame(), {})


def test_missing_indicator_key_raises():
    md = _monthly_market_data()
    indicator_set = {"mom_3": md.prices}
    eligibility = pd.DataFrame(True, index=md.prices.index, columns=md.prices.columns)
    with pytest.raises(ValueError, match="brak wskaznikow"):
        weighted_sum(md, indicator_set, eligibility, {"weights": {"mom_3": 0.5, "mom_6": 0.5}})


def test_mismatched_indicator_index_raises():
    md = _monthly_market_data()
    other_index_frame = md.prices.copy()
    other_index_frame.index = other_index_frame.index + pd.Timedelta(days=1)
    indicator_set = {"a1": md.prices, "a2": other_index_frame}
    eligibility = pd.DataFrame(True, index=md.prices.index, columns=md.prices.columns)
    with pytest.raises(ValueError, match="inny index"):
        weighted_sum(md, indicator_set, eligibility, {"weights": {"a1": 0.5, "a2": 0.5}})


def test_weighted_sum_arithmetic_and_eligibility_masking_same_frequency():
    md = _monthly_market_data()
    indicator_set = {"a1": md.prices, "a2": md.prices * 2}
    # "b" nieeligibilne caly czas
    eligibility = pd.DataFrame(
        {"a": [True] * 4, "b": [False] * 4}, index=md.prices.index
    )

    score = weighted_sum(md, indicator_set, eligibility, {"weights": {"a1": 1.0, "a2": 0.5}})

    # score = a1*1.0 + a2*0.5 = prices*1.0 + prices*2*0.5 = prices*2.0
    expected_a = md.prices["a"] * 2.0
    pd.testing.assert_series_equal(score["a"], expected_a, check_names=False)
    assert score["b"].isna().all()


def test_daily_eligibility_aligned_to_monthly_score_via_ffill():
    md = _monthly_market_data()
    indicator_set = {"mom_3": md.prices}

    # eligibility w DZIENNEJ czestotliwosci, "a" staje sie eligibilne dopiero od 2021-02-15
    daily_idx = pd.date_range("2021-01-01", "2021-04-01", freq="D")
    eligibility_daily = pd.DataFrame(
        {"a": False, "b": True}, index=daily_idx
    )
    eligibility_daily.loc[eligibility_daily.index >= "2021-02-15", "a"] = True

    score = weighted_sum(md, indicator_set, eligibility_daily, {"weights": {"mom_3": 1.0}})

    # 2021-01-01, 2021-02-01: "a" jeszcze nieeligibilne (ostatni znany stan sprzed 15 lutego)
    assert pd.isna(score.loc["2021-01-01", "a"])
    assert pd.isna(score.loc["2021-02-01", "a"])
    # 2021-03-01, 2021-04-01: "a" juz eligibilne (stan z 15 lutego utrzymany do przodu)
    assert not pd.isna(score.loc["2021-03-01", "a"])
    assert not pd.isna(score.loc["2021-04-01", "a"])
    assert score["b"].notna().all()


def test_full_chain_on_real_data(us_data_dir, us_universe):
    stooq_csv = LOADER_REGISTRY["stooq_csv"]
    sma_daily = INDICATORS_REGISTRY["sma_daily"]
    momentum_monthly = INDICATORS_REGISTRY["momentum_monthly"]
    price_above_indicator = ASSET_FILTERS_REGISTRY["price_above_indicator"]

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

    assert list(score.columns) == us_universe
    assert score.index.equals(indicator_set["mom_3"].index)  # score na siatce wskaznikow (monthly)
    assert score.dropna(how="all").shape[0] > 0
