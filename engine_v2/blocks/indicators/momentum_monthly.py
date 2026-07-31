"""
INDICATORS - implementacja "momentum_monthly".

Momentum liczone na cenach WYKONANIA (nie konca miesiaca): resampluje dzienne
`market_data.prices` do ceny na dzien wykonania kazdego miesiaca (ten sam schemat i ten sam
domyslny dzien co DATA LOADER dla frequency="monthly" - patrz `engine_v2/period_anchor.py`),
potem liczy price[t] / price[t-window] - 1. Okno w miesiacach kalendarzowych, nie w dniach
handlowych - to klasyczna definicja momentum (np. "12-miesieczny momentum").

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu) ani z innych
blokow engine_v2 (poza wspolnym `period_anchor.py`, patrz jego docstring - uzywany TEZ przez
DATA LOADER, bo oba MUSZA zgadzac sie co do dnia miesiaca).

Kontrakt: (market_data: MarketData, params: dict) -> pd.DataFrame (index=poczatki miesiecy,
kolumny=tickery).

params:
    window (int, wymagane)                    - dlugosc okna w miesiacach
    execution_day_of_month (int, domyslnie 1) - MUSI byc identyczny jak w `data_loader` tej
                                                 samej strategii (patrz `period_anchor.py`)
"""

from __future__ import annotations

from typing import Any, Dict

from engine_v2.blocks.indicators import REGISTRY
from engine_v2.period_anchor import nth_trading_day_prices
from engine_v2.registry import register
from engine_v2.types import MarketData


@register(REGISTRY, "momentum_monthly")
def momentum_monthly(market_data: MarketData, params: Dict[str, Any]):
    if "window" not in params:
        raise ValueError("momentum_monthly wymaga params['window'].")

    window = int(params["window"])
    if window < 1:
        raise ValueError(f"momentum_monthly: window musi byc >= 1, dostalem {window}.")

    day_of_month = int(params.get("execution_day_of_month", 1))
    monthly_prices = nth_trading_day_prices(market_data.prices, day_of_month)
    return monthly_prices / monthly_prices.shift(window) - 1.0
