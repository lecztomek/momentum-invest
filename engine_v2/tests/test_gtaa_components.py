"""
Testy jednostkowe (dane syntetyczne) nowego bloku dla GTAA AGG3/AGG6:
gtaa_trend_bond_reroute.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_gtaa_components.py -v
"""

import numpy as np
import pandas as pd
import pytest

from engine_v2.blocks.portfolio_risk_engine import REGISTRY as PORTFOLIO_RISK_ENGINE_REGISTRY
from engine_v2.types import MarketData

gtaa_trend_bond_reroute = PORTFOLIO_RISK_ENGINE_REGISTRY["gtaa_trend_bond_reroute"]


def _month_end_prices_df(monthly_values: dict, start="2020-01-01", periods=8):
    """monthly_values: {ticker: [cena_konca_kazdego_miesiaca, ...]} - buduje dzienny
    market_data.prices z jedna cena na koniec kazdego miesiaca (reszta dni = NaN, wystarczy
    do month_end_prices().resample('ME').last())."""
    month_ends = pd.date_range(start, periods=periods, freq="ME")
    idx = pd.date_range(start, month_ends[-1], freq="D")
    prices = pd.DataFrame(index=idx)
    for ticker, values in monthly_values.items():
        prices[ticker] = np.nan
        for d, v in zip(month_ends, values):
            prices.loc[d, ticker] = v
    return prices, month_ends


def test_reroutes_only_the_slot_below_its_sma_not_the_whole_portfolio():
    # "a" trenduje w gore caly czas (zawsze > SMA3), "b" spada ostatnie 3 miesiace (< SMA3
    # od pewnego momentu) - liczy sie TYLKO slot "b", "a" zostaje nietkniety.
    monthly_a = [100, 105, 110, 115, 120, 125, 130, 135]
    monthly_b = [100, 110, 120, 115, 100, 90, 80, 70]
    prices, month_ends = _month_end_prices_df({"a": monthly_a, "b": monthly_b, "bond": [100] * 8})
    md = MarketData(prices=prices, returns=pd.DataFrame())

    exec_dates = (month_ends.to_period("M") + 1).to_timestamp(how="start")
    target_weights = pd.DataFrame(
        {"a": 0.5, "b": 0.5, "bond": 0.0, "_CASH": 0.0}, index=exec_dates
    )

    out = gtaa_trend_bond_reroute(
        target_weights, md, {}, pd.DataFrame(),
        {"sma_window": 3, "bond_fallback_asset": "bond"},
    )

    last_date = exec_dates[-1]
    assert out.loc[last_date, "a"] == pytest.approx(0.5)   # "a" wciaz w trendzie - bez zmian
    assert out.loc[last_date, "b"] == pytest.approx(0.0)    # "b" ponizej SMA3 - przekierowane
    assert out.loc[last_date, "bond"] == pytest.approx(0.5)  # dokladnie ta 1 przekierowana czesc
    assert out.loc[last_date].sum() == pytest.approx(1.0)


def test_all_slots_below_sma_routes_entire_portfolio_to_bond():
    monthly_a = [100, 110, 120, 115, 100, 90, 80, 70]
    monthly_b = [100, 108, 118, 112, 95, 85, 75, 65]
    prices, month_ends = _month_end_prices_df({"a": monthly_a, "b": monthly_b, "bond": [100] * 8})
    md = MarketData(prices=prices, returns=pd.DataFrame())
    exec_dates = (month_ends.to_period("M") + 1).to_timestamp(how="start")
    target_weights = pd.DataFrame({"a": 0.5, "b": 0.5, "bond": 0.0, "_CASH": 0.0}, index=exec_dates)

    out = gtaa_trend_bond_reroute(
        target_weights, md, {}, pd.DataFrame(), {"sma_window": 3, "bond_fallback_asset": "bond"}
    )

    last_date = exec_dates[-1]
    assert out.loc[last_date, "a"] == pytest.approx(0.0)
    assert out.loc[last_date, "b"] == pytest.approx(0.0)
    assert out.loc[last_date, "bond"] == pytest.approx(1.0)


def test_zero_weight_slot_is_ignored_not_counted_as_reroute():
    monthly_a = [100, 110, 120, 115, 100, 90, 80, 70]  # spada, ale waga=0 - nie powinno nic zrobic
    prices, month_ends = _month_end_prices_df({"a": monthly_a, "bond": [100] * 8})
    md = MarketData(prices=prices, returns=pd.DataFrame())
    exec_dates = (month_ends.to_period("M") + 1).to_timestamp(how="start")
    target_weights = pd.DataFrame({"a": 0.0, "bond": 0.0, "_CASH": 1.0}, index=exec_dates)

    out = gtaa_trend_bond_reroute(
        target_weights, md, {}, pd.DataFrame(), {"sma_window": 3, "bond_fallback_asset": "bond"}
    )

    last_date = exec_dates[-1]
    assert out.loc[last_date, "bond"] == pytest.approx(0.0)
    assert out.loc[last_date, "_CASH"] == pytest.approx(1.0)


def test_requires_params():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    md = MarketData(prices=pd.DataFrame({"a": [1.0]}, index=idx), returns=pd.DataFrame())
    target_weights = pd.DataFrame({"a": [1.0], "_CASH": [0.0]}, index=idx)
    with pytest.raises(ValueError, match="gtaa_trend_bond_reroute"):
        gtaa_trend_bond_reroute(target_weights, md, {}, pd.DataFrame(), {})


def test_unknown_bond_fallback_asset_raises():
    idx = pd.date_range("2021-01-01", periods=1, freq="MS")
    md = MarketData(prices=pd.DataFrame({"a": [1.0]}, index=idx), returns=pd.DataFrame())
    target_weights = pd.DataFrame({"a": [1.0], "_CASH": [0.0]}, index=idx)
    with pytest.raises(ValueError, match="nie jest kolumna"):
        gtaa_trend_bond_reroute(
            target_weights, md, {}, pd.DataFrame(), {"sma_window": 3, "bond_fallback_asset": "nope"}
        )
