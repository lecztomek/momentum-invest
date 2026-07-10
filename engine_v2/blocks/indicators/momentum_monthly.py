"""
INDICATORS - implementacja "momentum_monthly".

Momentum liczone na miesiecznych cenach: najpierw resampluje dzienne `market_data.prices` do
ceny na poczatek kazdego miesiaca (ten sam schemat co DATA LOADER dla frequency="monthly"),
potem liczy price[t] / price[t-window] - 1. Okno w miesiacach kalendarzowych, nie w dniach
handlowych - to klasyczna definicja momentum (np. "12-miesieczny momentum").

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu) ani z innych
blokow engine_v2. Resamplowanie do miesiecznych cen jest tu WLASNA, mala kopia tej samej idei
co w DATA LOADER (`_period_start_execution_prices`) - swiadoma duplikacja, zeby ten blok byl
w pelni samodzielny i wymienny.

Kontrakt: (market_data: MarketData, params: dict) -> pd.DataFrame (index=poczatki miesiecy,
kolumny=tickery).

params:
    window (int, wymagane) - dlugosc okna w miesiacach
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.indicators import REGISTRY
from engine_v2.registry import register
from engine_v2.types import MarketData


def _monthly_start_prices(daily_prices: pd.DataFrame) -> pd.DataFrame:
    out = daily_prices.resample("MS").first()
    out.index.name = "date"
    return out


@register(REGISTRY, "momentum_monthly")
def momentum_monthly(market_data: MarketData, params: Dict[str, Any]) -> pd.DataFrame:
    if "window" not in params:
        raise ValueError("momentum_monthly wymaga params['window'].")

    window = int(params["window"])
    if window < 1:
        raise ValueError(f"momentum_monthly: window musi byc >= 1, dostalem {window}.")

    monthly_prices = _monthly_start_prices(market_data.prices)
    return monthly_prices / monthly_prices.shift(window) - 1.0
