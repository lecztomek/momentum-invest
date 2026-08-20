"""
Testy CANARY - filtr rezimu WIG20 > 10M MA.

Najwazniejsza czesc to poprawnosc point-in-time: w dniu decyzyjnym (1. dzien handlowy miesiaca M)
srednia moze siegac najdalej do zamkniecia miesiaca M-1. Uzycie zamkniecia miesiaca M byloby
look-ahead: strategia "wiedzialaby" 1 kwietnia, jak skonczy sie kwiecien.

Uruchomienie: .venv/bin/pytest value_engine/tests/test_canary.py -v
"""

from pathlib import Path

import pandas as pd
import pytest

from value_engine.canary import Canary, build_regime, load_index_prices, monthly_closes

REPO_ROOT = Path(__file__).resolve().parents[2]
PL_DATA_DIR = REPO_ROOT / "data" / "pl"


def _daily(values_per_month: list, start: str = "2019-01-01") -> pd.Series:
    """Buduje dzienna serie, w ktorej kazdy miesiac ma stala cene z `values_per_month` - dzieki
    temu zamkniecie miesiaca jest dokladnie znane i test jest w pelni deterministyczny."""
    pieces = []
    month_start = pd.Timestamp(start)
    for value in values_per_month:
        days = pd.bdate_range(month_start, month_start + pd.offsets.MonthEnd(0))
        pieces.append(pd.Series([float(value)] * len(days), index=days))
        month_start = (month_start + pd.offsets.MonthBegin(1)).normalize()
    return pd.concat(pieces)


def test_monthly_closes_are_indexed_by_last_session_of_month():
    series = _daily([100, 110, 120])
    closes = monthly_closes(series)

    assert list(closes.values) == [100.0, 110.0, 120.0]
    # indeks to data OSTATNIEJ SESJI miesiaca, nie etykieta miesiaca
    assert closes.index[0].month == 1 and closes.index[0].day >= 28


def test_regime_is_none_before_full_ma_window():
    series = _daily([100] * 12)
    canary = Canary(series, ma_months=10)

    # po 9 zakonczonych miesiacach nie ma jeszcze pelnego okna
    assert canary.regime_at(pd.Timestamp("2019-10-01")) is None
    assert canary.regime_at(pd.Timestamp("2019-11-01")) is not None


def test_risk_on_when_last_close_above_moving_average():
    # 10 miesiecy po 100, potem miesiac 200 -> srednia z 10 ostatnich (91..200) < 200
    canary = Canary(_daily([100] * 10 + [200]), ma_months=10)

    assert canary.regime_at(pd.Timestamp("2019-12-02")) is True


def test_risk_off_when_last_close_below_moving_average():
    canary = Canary(_daily([100] * 10 + [50]), ma_months=10)

    assert canary.regime_at(pd.Timestamp("2019-12-02")) is False


def test_uses_only_months_completed_before_decision_date():
    """RDZEN POPRAWNOSCI PIT. Miesiace 1-10 sa na 100, miesiac 11 (listopad) zapada sie do 10.
    Decyzja 1 LISTOPADA nie moze widziec listopadowego zamkniecia - musi widziec rezim risk-neutralny
    z danych do konca pazdziernika (100 vs srednia 100 -> NIE risk-on, bo wymagamy ostro >).
    Decyzja 1 GRUDNIA juz widzi krach listopada."""
    canary = Canary(_daily([100] * 10 + [10] + [10]), ma_months=10)

    november_first = pd.Timestamp("2019-11-01")
    december_first = pd.Timestamp("2019-12-02")

    # 1 listopada: znane sa tylko miesiace I-X, wszystkie po 100 -> 100 > 100 jest FALSE
    assert canary.regime_at(november_first) is False
    diagnostics = canary.diagnostics(november_first)
    assert diagnostics["level"] == pytest.approx(100.0)
    assert diagnostics["ma"] == pytest.approx(100.0)

    # 1 grudnia: listopad (10) jest juz zakonczony i wchodzi do sredniej
    assert canary.regime_at(december_first) is False
    assert canary.diagnostics(december_first)["level"] == pytest.approx(10.0)


def test_decision_day_price_variant_reacts_faster():
    """Wariant `use_decision_day_price` porownuje BIEZACA cene do 10M MA - tez PIT (dzisiejsza cena
    jest znana dzisiaj), ale reaguje szybciej niz zamkniecie poprzedniego miesiaca."""
    # 10 miesiecy po 100, listopad zapada sie do 10 -> 1 listopada biezaca cena to juz 10
    canary = Canary(_daily([100] * 10 + [10]), ma_months=10)
    november_first = pd.Timestamp("2019-11-01")

    assert canary.regime_at(november_first, use_decision_day_price=False) is False  # 100 vs 100
    assert canary.regime_at(november_first, use_decision_day_price=True) is False  # 10 vs 100

    # odwrotnie: rynek odbija w listopadzie po 10 spokojnych miesiacach
    rebound = Canary(_daily([100] * 10 + [500]), ma_months=10)
    assert rebound.regime_at(november_first, use_decision_day_price=False) is False  # nie widzi jeszcze
    assert rebound.regime_at(november_first, use_decision_day_price=True) is True  # widzi odbicie


def test_ma_months_must_be_at_least_two():
    with pytest.raises(ValueError, match="ma_months"):
        Canary(_daily([100] * 12), ma_months=1)


def test_build_regime_treats_missing_history_as_risk_on_by_default():
    canary = Canary(_daily([100] * 12), ma_months=10)
    dates = [pd.Timestamp("2019-03-01"), pd.Timestamp("2019-12-02")]

    permissive = build_regime(canary, dates, missing_is_risk_on=True)
    strict = build_regime(canary, dates, missing_is_risk_on=False)

    assert permissive[dates[0]] is True  # brak historii -> nie blokujemy
    assert strict[dates[0]] is False


# --- na prawdziwych danych ---


def test_real_wig20_loads():
    if not (PL_DATA_DIR / "wig20.txt").exists():
        pytest.skip("Brak data/pl/wig20.txt")

    series = load_index_prices("wig20", PL_DATA_DIR)

    assert len(series) > 5000
    assert series.index.min() < pd.Timestamp("2000-01-01")
    assert (series > 0).all()


def test_real_wig20_regime_matches_known_bear_markets():
    """Kontrola z rzeczywistoscia: kanarek MUSI byc risk-off w znanych bessach (2008 GFC, 2020
    COVID, 2022 bessa inflacyjna) i risk-on w znanych hossach (2006, 2017, 2021). Gdyby te lata
    wyszly odwrotnie, znaczyloby to blad w kierunku porownania albo w resamplingu."""
    if not (PL_DATA_DIR / "wig20.txt").exists():
        pytest.skip("Brak data/pl/wig20.txt")

    canary = Canary(load_index_prices("wig20", PL_DATA_DIR))
    dates = pd.date_range("2006-01-01", "2026-08-01", freq="MS")
    regime = pd.Series(build_regime(canary, list(dates)))

    def share(year: int) -> float:
        segment = regime[regime.index.year == year]
        return float(segment.mean())

    for bear_year in (2008, 2020, 2022):
        assert share(bear_year) < 0.25, f"{bear_year}: risk-on {share(bear_year):.0%}, oczekiwana bessa"
    for bull_year in (2006, 2017, 2021):
        assert share(bull_year) > 0.75, f"{bull_year}: risk-on {share(bull_year):.0%}, oczekiwana hossa"

    # caly okres: filtr nie moze byc ani zawsze wlaczony, ani zawsze wylaczony
    assert 0.3 < float(regime.mean()) < 0.8
