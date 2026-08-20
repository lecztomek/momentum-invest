"""
SIGNALS - sygnaly cenowe dla `value_engine`.

User: "Sygnal cenowy: spolka jest mocno przeceniona, np. >=25% ponizej 52W high."

Ceny dzienne PL sa w DOKLADNIE tym samym formacie stooq co dane US/UK, wiec czytamy je
istniejacym, przetestowanym loaderem `engine_v2.blocks.data_loader["stooq_csv"]` - zero nowego
kodu do wczytywania cen (zweryfikowane: `data/pl` wczytuje sie poprawnie, dnp/cdr/kgh/pkn).

52W high jest liczone jako maksimum kroczace po DNIACH HANDLOWYCH (`min_periods` = pelne okno) -
dopoki spolka nie ma pelnego roku historii, sygnal jest NaN, a nie liczony z krotszego okna.
Inaczej swiezo notowana spolka mialaby sztucznie male "obsuniecie od szczytu" (bo szczyt bylby
z kilku tygodni, nie z roku) i wchodzila do portfela na falszywym sygnale.
"""

from __future__ import annotations

from typing import List

import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def drawdown_from_rolling_high(
    daily_prices: pd.DataFrame, lookback_trading_days: int = TRADING_DAYS_PER_YEAR
) -> pd.DataFrame:
    """Obsuniecie od maksimum kroczacego, jako liczba UJEMNA: -0.25 = 25% ponizej 52W high.

    Maksimum obejmuje biezacy dzien, wiec na nowym szczycie wynik jest dokladnie 0.0."""
    if lookback_trading_days < 2:
        raise ValueError(f"lookback_trading_days musi byc >= 2, dostalem {lookback_trading_days}.")

    rolling_high = daily_prices.rolling(window=lookback_trading_days, min_periods=lookback_trading_days).max()
    return daily_prices / rolling_high - 1.0


def month_start_decision_dates(daily_prices: pd.DataFrame) -> List[pd.Timestamp]:
    """Pierwszy dzien handlowy kazdego miesiaca - te same daty decyzyjne co w `engine_v2`
    (`nth_trading_day_prices(day_of_month=1)`), zeby wyniki byly porownywalne konwencja."""
    index = daily_prices.sort_index().index
    frame = pd.DataFrame(index=index)
    frame["month"] = index.to_period("M")
    return [group.index[0] for _, group in frame.groupby("month", sort=True)]


def quarter_start_decision_dates(daily_prices: pd.DataFrame) -> List[pd.Timestamp]:
    """Pierwszy dzien handlowy kazdego kwartalu (styczen, kwiecien, lipiec, pazdziernik) - dla
    koncepcji v6, ktora rebalansuje KWARTALNIE.

    Liczone z kalendarza, a nie jako "co trzecia data miesieczna" - inaczej faza siatki zalezalaby
    od tego, w ktorym miesiacu zaczyna sie historia cen, i dwa uruchomienia na roznych podzbiorach
    tickerow rebalansowalyby w innych miesiacach. To wprost psuloby test leave-one-out."""
    monthly = month_start_decision_dates(daily_prices)
    return [date for date in monthly if date.month in (1, 4, 7, 10)]
