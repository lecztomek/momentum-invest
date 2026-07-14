"""
Testy dla `stooq_csv_dividend_adjusted` (engine_v2/blocks/data_loader/dividend_adjusted_csv_loader.py) -
naprawa braku reinwestycji dywidend/kuponow w `data/us` (user: "Mamy wynik 3 procent a keller
podawal 9 to jest ogromny rozjazd wiec gdzies jest konkretny bug trzeba go poszukac").

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_dividend_adjusted_data_loader.py -v
"""

import numpy as np
import pandas as pd
import pytest

from engine_v2.blocks.data_loader import REGISTRY
from engine_v2.blocks.data_loader.dividend_adjusted_csv_loader import _dividend_adjusted_close

stooq_csv = REGISTRY["stooq_csv"]
stooq_csv_dividend_adjusted = REGISTRY["stooq_csv_dividend_adjusted"]


def test_dividend_adjusted_close_extrapolates_measured_rate_before_overlap():
    """US i UK rosna identycznie (0%/dzien) w overlapie, ALE UK ma dodatkowy STALY dzienny
    narost 0,01% (symulacja "brakujacej dywidendy") - regresja powinna to wykryc i poprawnie
    ekstrapolowac WSTECZ (przed overlapem correction < 1, bo mniej czasu na akumulacje)."""
    idx_us = pd.date_range("2010-01-01", periods=200, freq="D")
    us = pd.Series(100.0, index=idx_us)  # plaska cena US (bez dywidend)

    overlap_start = idx_us[100]
    idx_uk = idx_us[100:]
    days = np.arange(len(idx_uk), dtype=float)
    uk = pd.Series(100.0 * np.exp(0.0001 * days), index=idx_uk)  # UK rosnie o 0,01%/dzien

    adjusted = _dividend_adjusted_close(us, uk)

    # W overlapie: adjusted powinno DOKLADNIE odtworzyc realna wartosc UK (przeskalowana przez US=100)
    assert adjusted.loc[overlap_start] == pytest.approx(uk.loc[overlap_start], rel=1e-6)
    assert adjusted.loc[idx_uk[-1]] == pytest.approx(uk.loc[idx_uk[-1]], rel=1e-6)

    # Przed overlapem: correction < correction(overlap_start) - mniej czasu na akumulacje narostu
    assert adjusted.iloc[0] < adjusted.loc[overlap_start]
    # Ale WCIAZ > surowa cena US na starcie (US jest plaskie, correction zawsze >= 0, tu > 0 bo
    # dodatni narost oznacza korekta > 1 nawet na starcie historii dla dodatniego gapu)
    assert adjusted.iloc[0] > 0


def test_dividend_adjusted_close_matches_us_when_uk_identical():
    """Gdy UK ma DOKLADNIE taka sama trajektorie jak US (brak "brakujacej dywidendy") -
    skorygowana seria powinna byc (w granicach numerycznych) identyczna z surowa US."""
    idx = pd.date_range("2015-01-01", periods=300, freq="D")
    days = np.arange(len(idx), dtype=float)
    prices = 100.0 * np.exp(0.0003 * days)
    us = pd.Series(prices, index=idx)
    uk = pd.Series(prices[50:], index=idx[50:])  # ten sam poziom i trend, krotsza historia (od 50. dnia)

    adjusted = _dividend_adjusted_close(us, uk)

    pd.testing.assert_series_equal(adjusted, us, check_exact=False, rtol=1e-6, check_names=False)


def test_dividend_adjusted_close_raises_when_no_overlap():
    idx_us = pd.date_range("2010-01-01", periods=10, freq="D")
    idx_uk = pd.date_range("2020-01-01", periods=10, freq="D")
    us = pd.Series(100.0, index=idx_us)
    uk = pd.Series(100.0, index=idx_uk)
    with pytest.raises(ValueError, match="brak wspolnego okna"):
        _dividend_adjusted_close(us, uk)


def test_unmapped_ticker_identical_to_plain_stooq_csv(us_data_dir):
    """Ticker BEZ wpisu w `dividend_adjustment_mapping` musi dawac IDENTYCZNY wynik jak
    `stooq_csv` (zero regresji na strategiach, ktore jeszcze nie maja korekty dla danego tickera)."""
    universe = ["spy.us", "qqq.us"]
    params_plain = {"data_dir": str(us_data_dir), "frequency": "monthly"}
    params_partial = {
        "data_dir": str(us_data_dir),
        "frequency": "monthly",
        "dividend_adjustment_mapping": {"spy.us": "cspx"},  # tylko spy.us ma mapowanie
    }

    md_plain = stooq_csv(universe, params_plain)
    md_partial = stooq_csv_dividend_adjusted(universe, params_partial)

    pd.testing.assert_series_equal(md_plain.prices["qqq.us"], md_partial.prices["qqq.us"])
    assert not md_plain.prices["spy.us"].equals(md_partial.prices["spy.us"])


def test_empty_mapping_reproduces_plain_stooq_csv_exactly(us_data_dir):
    universe = ["spy.us", "tlt.us"]
    params_plain = {"data_dir": str(us_data_dir), "frequency": "monthly"}
    params_no_mapping = {"data_dir": str(us_data_dir), "frequency": "monthly", "dividend_adjustment_mapping": {}}

    md_plain = stooq_csv(universe, params_plain)
    md_no_mapping = stooq_csv_dividend_adjusted(universe, params_no_mapping)

    pd.testing.assert_frame_equal(md_plain.prices, md_no_mapping.prices)
    pd.testing.assert_frame_equal(md_plain.returns, md_no_mapping.returns)


def test_mapped_ticker_uses_real_uk_data_and_shows_positive_measured_gap(us_data_dir, uk_data_dir):
    """agg.us -> suag.uk: zmierzony gap powinien byc DODATNI i rzedu 1-2%/rok (obligacyjny ETF,
    utracony kupon) - patrz CHANGELOG (56)."""
    universe = ["agg.us"]
    params = {
        "data_dir": str(us_data_dir),
        "uk_data_dir": str(uk_data_dir),
        "frequency": "monthly",
        "dividend_adjustment_mapping": {"agg.us": "suag"},
    }
    md = stooq_csv_dividend_adjusted(universe, params)
    raw = stooq_csv(universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})

    adjusted_close = md.prices["agg.us"].dropna()
    raw_close = raw.prices["agg.us"].dropna()
    years = (adjusted_close.index[-1] - adjusted_close.index[0]).days / 365.25

    adjusted_cagr = (adjusted_close.iloc[-1] / adjusted_close.iloc[0]) ** (1 / years) - 1
    raw_cagr = (raw_close.iloc[-1] / raw_close.iloc[0]) ** (1 / years) - 1

    assert adjusted_cagr > raw_cagr
    assert (adjusted_cagr - raw_cagr) == pytest.approx(0.0156, abs=0.01)


def test_missing_uk_file_raises_clear_error(us_data_dir, uk_data_dir):
    universe = ["spy.us"]
    params = {
        "data_dir": str(us_data_dir),
        "uk_data_dir": str(uk_data_dir),
        "frequency": "monthly",
        "dividend_adjustment_mapping": {"spy.us": "nieistniejacy_ticker_xyz"},
    }
    with pytest.raises(ValueError, match="brak pliku UK"):
        stooq_csv_dividend_adjusted(universe, params)
