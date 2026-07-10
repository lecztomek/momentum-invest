"""
INDICATORS - implementacja "volatility_daily".

Odchylenie standardowe dziennych zwrotow w oknie kroczacym, liczone na `market_data.prices`
(zawsze dzienny panel, niezaleznie od `frequency` strategii) - NIE na `market_data.returns`
(to jest zwrot w czestotliwosci strategii, np. miesieczny - zla podstawa do zmiennosci).

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu) ani z innych
blokow engine_v2.

Kontrakt: (market_data: MarketData, params: dict) -> pd.DataFrame (index=data dzienna,
kolumny=tickery, ta sama siatka co `market_data.prices`).

params:
    window (int, wymagane)                       - dlugosc okna w dniach handlowych
    annualize (bool, opcjonalnie, domyslnie True) - czy przeskalowac przez sqrt(252)
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.indicators import REGISTRY
from engine_v2.registry import register
from engine_v2.types import MarketData

_TRADING_DAYS_PER_YEAR = 252


@register(REGISTRY, "volatility_daily")
def volatility_daily(market_data: MarketData, params: Dict[str, Any]) -> pd.DataFrame:
    if "window" not in params:
        raise ValueError("volatility_daily wymaga params['window'].")

    window = int(params["window"])
    if window < 2:
        raise ValueError(f"volatility_daily: window musi byc >= 2, dostalem {window}.")

    annualize = bool(params.get("annualize", True))

    daily_returns = market_data.prices.pct_change()
    vol = daily_returns.rolling(window=window, min_periods=window).std()

    if annualize:
        vol = vol * (_TRADING_DAYS_PER_YEAR ** 0.5)

    return vol
