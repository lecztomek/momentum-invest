"""
Wspolne pomocnicze dla wskaznikow liczonych na cenach KONCA miesiaca (nie startu, jak reszta
silnika) - NIE jest to zarejestrowana implementacja, tylko funkcje uzywane przez pliki w tym
folderze, ktore odtwarzaja logike ze starego systemu (best17_3m: `build_data.py`).

Stary system liczy sygnal z cen na koniec miesiaca M, ale "wykonuje" go dopiero na starcie
miesiaca M+1 (`align_scores_to_execution_month`) - stad `_shift_to_next_month_start`: przesuwa
index tak, zeby wartosc policzona z danych do konca miesiaca M byla zaetykietowana data startu
miesiaca M+1 - to jest DOKLADNIE ta sama etykieta (MS) co reszta silnika uzywa dla execution
prices/returns, wiec wynik jest w pelni kompatybilny z pipeline'm bez dodatkowego dopasowywania.

`anchored_prices`/`label_to_execution_month` daja DRUGI tryb: gdy wskaznik dostanie
`execution_day_of_month`, liczy sie on na cenie z DNIA WYKONANIA tego samego miesiaca (ten sam
`nth_trading_day_prices`, co data_loader i `momentum_monthly`), bez przesuwania etykiety - bo
`nth_trading_day_prices` etykietuje juz startem miesiaca. Sygnal uzywa wtedy ceny, ktora jest
znana w chwili transakcji, zamiast ceny sprzed kilkunastu/kilkudziesieciu dni. Brak parametru =
zachowanie dotychczasowe (koniec poprzedniego miesiaca), wiec istniejace spece nie zmieniaja sie.
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from engine_v2.period_anchor import nth_trading_day_prices


def month_end_prices(daily_prices: pd.DataFrame) -> pd.DataFrame:
    out = daily_prices.resample("ME").last()
    out.index.name = "date"
    return out


def shift_to_next_month_start(month_end_indexed: pd.DataFrame) -> pd.DataFrame:
    out = month_end_indexed.copy()
    out.index = (out.index.to_period("M") + 1).to_timestamp(how="start")
    out.index.name = "date"
    return out


def anchored_prices(daily_prices: pd.DataFrame, params: Mapping[str, Any]) -> pd.DataFrame:
    day = params.get("execution_day_of_month")
    if day is None:
        return month_end_prices(daily_prices)
    day = int(day)
    if day < 1:
        raise ValueError(f"execution_day_of_month musi byc >= 1, dostalem {day}.")
    return nth_trading_day_prices(daily_prices, day)


def label_to_execution_month(frame: pd.DataFrame, params: Mapping[str, Any]) -> pd.DataFrame:
    if params.get("execution_day_of_month") is None:
        return shift_to_next_month_start(frame)
    return frame
