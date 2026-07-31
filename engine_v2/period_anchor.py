"""
PERIOD ANCHOR - wspolna pomocnicza uzywana przez DATA LOADER (`blocks/data_loader/csv_loader.py`)
i wskazniki liczone NA cenie wykonania, nie na cenie konca miesiaca (`blocks/indicators/
momentum_monthly.py`) - obie strony musza wybierac TEN SAM dzien miesiaca, inaczej pipeline
laczy po dacie wskazniki/ceny wykonania z roznych dni i po cichu dostaje puste/rozjezdzone wiersze
(patrz README/CHANGELOG - poprawka execution_day_of_month, 2026-07-16).

Domyslnie (`day_of_month=1`) zachowanie identyczne jak dotychczasowe `resample("MS").first()` -
pierwszy dzien handlowy miesiaca. Dla `day_of_month > 1` - pierwszy dzien handlowy NA/PO tym
dniu kalendarzowym w danym miesiacu (np. `day_of_month=5` -> "5-ty, albo najblizszy kolejny dzien
handlowy"); jesli miesiac nie ma zadnego dnia handlowego >= `day_of_month` (np. krotki miesiac +
duzy `day_of_month`), uzywamy ostatniego dostepnego dnia handlowego tego miesiaca jako fallback.

WAZNE: wynikowy wiersz jest ZAWSZE etykietowany startem kalendarzowego miesiaca (ta sama etykieta
"MS" niezaleznie od `day_of_month`, tak jak dzis) - `day_of_month` zmienia TYLKO to, JAKA cene/
wartosc bierzemy do tego wiersza, nie sposob w jaki dalszy pipeline laczy/zestawia miesieczne
daty (ktory wymaga IDENTYCZNYCH etykiet wszedzie, patrz `_month_end_common.shift_to_next_month_start`,
ktora dzieki temu NIE musi znac `day_of_month` w ogole).
"""

from __future__ import annotations

import pandas as pd


def nth_trading_day_prices(daily_prices: pd.DataFrame, day_of_month: int = 1) -> pd.DataFrame:
    if day_of_month < 1:
        raise ValueError(f"day_of_month musi byc >= 1, dostalem {day_of_month}.")

    if day_of_month == 1:
        out = daily_prices.resample("MS").first()
        out.index.name = "date"
        return out

    periods = daily_prices.index.to_period("M")

    def _pick(group: pd.DataFrame) -> pd.Series:
        on_or_after = group[group.index.day >= day_of_month]
        return on_or_after.iloc[0] if not on_or_after.empty else group.iloc[-1]

    picked = daily_prices.groupby(periods).apply(_pick)
    picked.index = picked.index.to_timestamp(how="start")
    picked.index.name = "date"
    return picked.sort_index()
