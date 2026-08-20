"""
CANARY - filtr rezimu rynkowego: WIG20 powyzej swojej 10-miesiecznej sredniej.

User: "dodajmy kanarek WIG20 > 10M MA".

REGULA (klasyczny timing na 10-miesiecznej SMA):
    risk-on  <=> zamkniecie OSTATNIEGO ZAKONCZONEGO miesiaca > srednia z 10 ostatnich zamkniec
                 miesiecznych (ta srednia zawiera ten ostatni miesiac)
    risk-off <=> w przeciwnym razie

POPRAWNOSC POINT-IN-TIME - to jest jedyna rzecz, ktora tu naprawde trzeba zrobic dokladnie.
Data decyzyjna to PIERWSZY dzien handlowy miesiaca M. W tym momencie zamkniecie miesiaca M jeszcze
NIE ISTNIEJE, wiec sredniа moze siegac najdalej do zamkniecia miesiaca M-1. Uzycie zamkniecia
miesiaca M byloby klasycznym look-ahead: strategia "wiedzialaby" 1 kwietnia, jak skonczy sie
kwiecien. `regime_at` bierze wiec wylacznie miesiace ZAKONCZONE PRZED data decyzyjna.

Dlaczego porownujemy zamkniecie miesiaca, a nie biezaca cene z dnia decyzyjnego: obie wersje sa
poprawne PIT (biezaca cena jest znana dzisiaj), ale wersja "zamkniecie miesiaca vs 10M MA" to
standardowa, opisana w literaturze postac tej reguly i nie miesza dwoch roznych czestotliwosci w
jednym porownaniu. Wersja reagujaca na cene sroddzienna jest dostepna przez `use_decision_day_price`.

BRAK DANYCH: dopoki nie ma pelnych 10 zamkniec miesiecznych, `regime_at` zwraca None. Wolajacy
decyduje, co z tym zrobic - `build_regime` domyslnie traktuje None jako RISK-ON (nie blokujemy
strategii tylko dlatego, ze indeks ma krotka historie), ale to jest jawny parametr.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Sequence

import pandas as pd

from engine_v2.blocks.data_loader import REGISTRY as DATA_LOADER_REGISTRY

DEFAULT_MA_MONTHS = 10


def load_index_prices(ticker: str, data_dir: Path) -> pd.Series:
    """Dzienne zamkniecia indeksu, tym samym loaderem stooq co reszta danych."""
    prices = DATA_LOADER_REGISTRY["stooq_csv"]([ticker], {"data_dir": str(data_dir), "frequency": "daily"}).prices
    return prices[ticker].dropna()


def monthly_closes(daily_prices: pd.Series) -> pd.Series:
    """Zamkniecie kazdego miesiaca kalendarzowego, indeksowane data OSTATNIEJ SESJI tego miesiaca
    (nie etykieta miesiaca) - dzieki temu porownanie `< data_decyzyjna` jest jednoznaczne."""
    series = daily_prices.sort_index()
    frame = pd.DataFrame({"price": series})
    frame["month"] = series.index.to_period("M")
    last = frame.groupby("month").tail(1)
    return pd.Series(last["price"].values, index=last.index, name="monthly_close")


class Canary:
    def __init__(self, daily_prices: pd.Series, ma_months: int = DEFAULT_MA_MONTHS):
        if ma_months < 2:
            raise ValueError(f"ma_months musi byc >= 2, dostalem {ma_months}.")
        self._daily = daily_prices.sort_index()
        self._monthly = monthly_closes(self._daily)
        self._ma_months = ma_months

    @property
    def ma_months(self) -> int:
        return self._ma_months

    def regime_at(self, date: pd.Timestamp, use_decision_day_price: bool = False) -> Optional[bool]:
        """True = risk-on. None = za krotka historia indeksu.

        Uzywa WYLACZNIE miesiecy zakonczonych PRZED `date` (patrz docstring modulu)."""
        completed = self._monthly[self._monthly.index < date]
        if len(completed) < self._ma_months:
            return None

        moving_average = float(completed.iloc[-self._ma_months :].mean())
        if use_decision_day_price:
            available = self._daily[self._daily.index <= date]
            if available.empty:
                return None
            level = float(available.iloc[-1])
        else:
            level = float(completed.iloc[-1])
        return level > moving_average

    def diagnostics(self, date: pd.Timestamp) -> Dict[str, Optional[float]]:
        completed = self._monthly[self._monthly.index < date]
        if len(completed) < self._ma_months:
            return {"level": None, "ma": None, "ratio": None}
        moving_average = float(completed.iloc[-self._ma_months :].mean())
        level = float(completed.iloc[-1])
        return {"level": level, "ma": moving_average, "ratio": level / moving_average - 1.0}


def build_regime(
    canary: Canary,
    decision_dates: Sequence[pd.Timestamp],
    missing_is_risk_on: bool = True,
    use_decision_day_price: bool = False,
) -> Dict[pd.Timestamp, bool]:
    """Slownik data -> czy risk-on, gotowy do przekazania silnikowi."""
    out: Dict[pd.Timestamp, bool] = {}
    for date in decision_dates:
        regime = canary.regime_at(date, use_decision_day_price=use_decision_day_price)
        out[date] = missing_is_risk_on if regime is None else regime
    return out
