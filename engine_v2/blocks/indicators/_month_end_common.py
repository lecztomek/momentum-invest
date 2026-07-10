"""
Wspolne pomocnicze dla wskaznikow liczonych na cenach KONCA miesiaca (nie startu, jak reszta
silnika) - NIE jest to zarejestrowana implementacja, tylko funkcje uzywane przez pliki w tym
folderze, ktore odtwarzaja logike ze starego systemu (best17_3m: `build_data.py`).

Stary system liczy sygnal z cen na koniec miesiaca M, ale "wykonuje" go dopiero na starcie
miesiaca M+1 (`align_scores_to_execution_month`) - stad `_shift_to_next_month_start`: przesuwa
index tak, zeby wartosc policzona z danych do konca miesiaca M byla zaetykietowana data startu
miesiaca M+1 - to jest DOKLADNIE ta sama etykieta (MS) co reszta silnika uzywa dla execution
prices/returns, wiec wynik jest w pelni kompatybilny z pipeline'm bez dodatkowego dopasowywania.
"""

from __future__ import annotations

import pandas as pd


def month_end_prices(daily_prices: pd.DataFrame) -> pd.DataFrame:
    out = daily_prices.resample("ME").last()
    out.index.name = "date"
    return out


def shift_to_next_month_start(month_end_indexed: pd.DataFrame) -> pd.DataFrame:
    out = month_end_indexed.copy()
    out.index = (out.index.to_period("M") + 1).to_timestamp(how="start")
    out.index.name = "date"
    return out
