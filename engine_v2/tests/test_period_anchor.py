"""
Testy dla `engine_v2/period_anchor.py::nth_trading_day_prices` - user: "co musielibysmy zmienic
zeby sprawdzic wplyw dnia miesiaca w ktorym kupujemy (1/5/10 zamiast zawsze pierwszego dnia
handlowego)". Ta funkcja jest wspolna dla DATA LOADER (`csv_loader.py`) i wskaznikow liczonych
NA cenie wykonania (`momentum_monthly.py`) - obie strony musza wybierac TEN SAM dzien, dlatego
kluczowe jest, zeby `day_of_month=1` bylo BAJT-IDENTYCZNE ze starym `resample("MS").first()`
(zero regresji na wszystkich istniejacych strategiach, ktore nie ustawiaja tego parametru).

Uruchomienie: .venv/bin/pytest engine_v2/tests/test_period_anchor.py -v
"""

import pandas as pd
import pytest

from engine_v2.period_anchor import nth_trading_day_prices


def _daily_prices() -> pd.DataFrame:
    dates = pd.to_datetime([
        "2020-01-02", "2020-01-03", "2020-01-06", "2020-01-31",
        "2020-02-03", "2020-02-04", "2020-02-28",
    ])
    return pd.DataFrame({"a": [1, 2, 3, 4, 5, 6, 7]}, index=dates)


def test_day_of_month_1_matches_plain_resample_ms_first():
    daily = _daily_prices()
    out = nth_trading_day_prices(daily, day_of_month=1)
    expected = daily.resample("MS").first()
    pd.testing.assert_frame_equal(out, expected.rename_axis("date"))


def test_day_of_month_1_is_the_default():
    daily = _daily_prices()
    assert nth_trading_day_prices(daily).equals(nth_trading_day_prices(daily, day_of_month=1))


def test_day_of_month_picks_first_trading_day_on_or_after():
    daily = _daily_prices()
    out = nth_trading_day_prices(daily, day_of_month=5)
    # Jan: pierwszy dzien handlowy >= 5 to 2020-01-06 (wartosc 3)
    assert out.loc["2020-01-01", "a"] == 3
    # Feb: pierwszy dzien handlowy >= 5 to 2020-02-28 (wartosc 7, brak danych 5-27 w tym teście)
    assert out.loc["2020-02-01", "a"] == 7


def test_day_of_month_falls_back_to_last_trading_day_when_none_on_or_after():
    daily = _daily_prices()
    out = nth_trading_day_prices(daily, day_of_month=31)
    # Jan ma dzien 31 (wartosc 4) - dostepny
    assert out.loc["2020-01-01", "a"] == 4
    # Feb nie ma zadnego dnia handlowego >= 31 - fallback do ostatniego w miesiacu (wartosc 7)
    assert out.loc["2020-02-01", "a"] == 7


def test_index_always_labeled_as_month_start_regardless_of_day_of_month():
    daily = _daily_prices()
    for day in [1, 5, 10, 31]:
        out = nth_trading_day_prices(daily, day_of_month=day)
        assert list(out.index) == [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-02-01")]


def test_day_of_month_below_1_raises():
    with pytest.raises(ValueError, match="day_of_month"):
        nth_trading_day_prices(_daily_prices(), day_of_month=0)


def test_higher_day_of_month_uses_later_or_equal_price_than_day_1(us_data_dir):
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY

    market_data = LOADER_REGISTRY["stooq_csv"](["xlk.us"], {"data_dir": str(us_data_dir), "frequency": "monthly"})
    day1 = nth_trading_day_prices(market_data.prices, 1)
    day10 = nth_trading_day_prices(market_data.prices, 10)
    common = day1.index.intersection(day10.index)
    assert len(common) > 12
    # dzien 10 zawsze wypada NA/PO dniu 1 w tym samym miesiacu - dla monotonicznie rosnacych
    # cen w krotkim okresie nie musi byc wiekszy, ale musi pochodzic z INNEJ (albo tej samej,
    # gdy brak notowan miedzy 1 a 10) daty - sprawdzamy, ze przynajmniej w jednym miesiacu wartosc
    # faktycznie sie rozni (inaczej caly mechanizm byłby martwy kod)
    assert not day1.loc[common, "xlk.us"].equals(day10.loc[common, "xlk.us"])
