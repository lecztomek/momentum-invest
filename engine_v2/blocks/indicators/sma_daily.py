"""
INDICATORS - implementacja "sma_daily".

Prosta srednia kroczaca liczona na dziennych cenach (`market_data.prices`). Okno w dniach
handlowych (nie w miesiacach) - `market_data.prices` jest zawsze dzienny, niezaleznie od
`frequency` strategii.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu) ani z innych
blokow engine_v2.

Kontrakt: (market_data: MarketData, params: dict) -> pd.DataFrame (index=data dzienna,
kolumny=tickery, ta sama siatka co `market_data.prices`).

params:
    window (int, wymagane) - dlugosc okna w dniach handlowych
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.indicators import REGISTRY
from engine_v2.registry import register
from engine_v2.types import MarketData


@register(REGISTRY, "sma_daily")
def sma_daily(market_data: MarketData, params: Dict[str, Any]) -> pd.DataFrame:
    if "window" not in params:
        raise ValueError("sma_daily wymaga params['window'].")

    window = int(params["window"])
    if window < 1:
        raise ValueError(f"sma_daily: window musi byc >= 1, dostalem {window}.")

    return market_data.prices.rolling(window=window, min_periods=window).mean()
