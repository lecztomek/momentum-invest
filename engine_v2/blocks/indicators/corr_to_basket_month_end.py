"""
INDICATORS - implementacja "corr_to_basket_month_end".

Roczaca sie korelacja miesiecznych zwrotow (ceny konca miesiaca) kazdego tickera w uniwersum do
ROWNOWAZONEGO koszyka wskazanych tickerow (`basket_assets` - STALY zestaw, taki sam przy ocenie
KAZDEGO tickera, WLACZNIE z tickerami spoza koszyka i z samym koszykiem - kazdy jego czlonek
jest tez czescia sredniej, do ktorej sie go porownuje. To ZAMIERZONE, wierne odtworzenie
metodologii "Generalized Protective Momentum" (`strategies_v2/gpm/`), nie blad). Zwrot koszyka w
danym miesiacu = SREDNIA (rownowazona) zwrotow jego skladnikow w tym miesiacu.

Etykieta przesunieta o jeden miesiac do przodu (ten sam schemat co `momentum_month_end` - patrz
`_month_end_common.py`).

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (market_data: MarketData, params: dict) -> pd.DataFrame (index=poczatki miesiecy,
kolumny=tickery).

params:
    basket_assets (list[str], wymagane) - tickery skladajace sie na rownowazony koszyk odniesienia
    window (int, wymagane)              - dlugosc rocacego okna korelacji, w miesiacach
"""

from __future__ import annotations

from typing import Any, Dict

from engine_v2.blocks.indicators import REGISTRY
from engine_v2.blocks.indicators._month_end_common import month_end_prices, shift_to_next_month_start
from engine_v2.registry import register
from engine_v2.types import MarketData


@register(REGISTRY, "corr_to_basket_month_end")
def corr_to_basket_month_end(market_data: MarketData, params: Dict[str, Any]):
    basket_assets = params.get("basket_assets")
    window = params.get("window")
    if not basket_assets or window is None:
        raise ValueError(
            "corr_to_basket_month_end wymaga params['basket_assets'] i params['window']."
        )
    window = int(window)
    if window < 2:
        raise ValueError(f"corr_to_basket_month_end: window musi byc >= 2, dostalem {window}.")

    missing = sorted(set(basket_assets) - set(market_data.prices.columns))
    if missing:
        raise ValueError(f"corr_to_basket_month_end: brak tickerow koszyka {missing} w market_data.")

    month_end = month_end_prices(market_data.prices)
    monthly_returns = month_end.pct_change()
    basket_return = monthly_returns[basket_assets].mean(axis=1)

    corr = monthly_returns.rolling(window).corr(basket_return)

    return shift_to_next_month_start(corr)
