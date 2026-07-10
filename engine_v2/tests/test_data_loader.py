"""
Testy regresyjne DATA LOADER (`stooq_csv`). Odpalane na prawdziwych danych z `data/us` - loader
ma za zadanie poprawnie czytac dokladnie ten format plikow, wiec to celowo integration test,
nie mock.

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_data_loader.py -v
"""

import pandas as pd
import pytest

from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY

stooq_csv = LOADER_REGISTRY["stooq_csv"]


def test_missing_data_dir_param_raises(us_universe):
    with pytest.raises(ValueError, match="data_dir"):
        stooq_csv(us_universe, {})


def test_missing_ticker_raises(us_data_dir, us_universe):
    with pytest.raises(ValueError, match="Brakujace tickery"):
        stooq_csv(us_universe + ["nieistniejacy_ticker.us"], {"data_dir": str(us_data_dir)})


def test_monthly_shape_and_columns(us_data_dir, us_universe):
    md = stooq_csv(us_universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})

    assert list(md.prices.columns) == us_universe
    assert list(md.returns.columns) == us_universe
    assert isinstance(md.prices.index, pd.DatetimeIndex)
    assert isinstance(md.returns.index, pd.DatetimeIndex)
    # monthly prices sa daily (do backtestu), returns sa juz miesieczne
    assert md.prices.index.is_monotonic_increasing
    assert md.returns.index.is_monotonic_increasing
    # jeden wiersz returns na miesiac zapoczatkowany w prices
    assert md.returns.index.equals(md.returns.index.normalize())


def test_frequencies_share_same_daily_prices(us_data_dir, us_universe):
    daily = stooq_csv(us_universe, {"data_dir": str(us_data_dir), "frequency": "daily"})
    weekly = stooq_csv(us_universe, {"data_dir": str(us_data_dir), "frequency": "weekly"})
    monthly = stooq_csv(us_universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})

    # `prices` to zawsze surowe dzienne ceny, niezaleznie od `frequency` - to steruje tylko
    # tym, jak licza sie `returns`.
    pd.testing.assert_frame_equal(daily.prices, weekly.prices)
    pd.testing.assert_frame_equal(daily.prices, monthly.prices)

    assert len(daily.returns) > len(weekly.returns) > len(monthly.returns)


def test_unknown_frequency_raises(us_data_dir, us_universe):
    with pytest.raises(ValueError, match="Nieznana frequency"):
        stooq_csv(us_universe, {"data_dir": str(us_data_dir), "frequency": "yearly"})


def test_loader_does_not_clean_only_reads(us_data_dir, us_universe):
    # LOADER swiadomie NIE czysci danych (rowna zakresy, wypelnia luki) - to jest zadanie
    # DATA CLEANER. Tickery z pozniejszym startem (np. dbc.us, uruchomiony dopiero w 2006) maja
    # NaN na poczatku - to jest oczekiwane i tego dokladnie pilnuje ten test: NaN moze wystapic
    # tylko jako prefiks przed realnym startem tickera (lub ostatni wiersz returns), nigdy jako
    # "dziura" w srodku juz rozpoczetej serii.
    md = stooq_csv(us_universe, {"data_dir": str(us_data_dir), "frequency": "monthly"})

    for col in md.returns.columns:
        series = md.returns[col]
        first_valid = series.first_valid_index()
        assert first_valid is not None
        after_start = series.loc[first_valid:].iloc[:-1]  # bez ostatniego (brak next-period)
        assert after_start.isna().sum() == 0, f"{col} ma luke w srodku serii, nie tylko prefiks"
