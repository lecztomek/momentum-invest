"""
INDICATORS - implementacja "momentum_month_end".

Odtwarza `momentum_r3` (i podobne) ze starego silnika (`engine/build_data.py`): prosty zwrot
N-miesieczny liczony na cenach KONCA KAZDEGO MIESIACA (nie startu, jak `momentum_monthly`).
Wynik przesuniety o jeden miesiac do przodu (patrz `_month_end_common.shift_to_next_month_start`)
- ta sama zasada "sygnal z konca miesiaca M, uzywany na starcie miesiaca M+1" co w oryginale.

Inaczej niz `momentum_monthly` (ktory liczy na cenach STARTU miesiaca, bez przesuniecia) - te
dwa nie sa zamiennikami, uzyj tego gdy trzeba wiernie odtworzyc logike opartej na cenach konca
miesiaca (np. `best17_3m`).

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu), tylko odtwarza
ten sam wzor.

Kontrakt: (market_data: MarketData, params: dict) -> pd.DataFrame (index=poczatki miesiecy,
kolumny=tickery).

params:
    window (int, wymagane) - dlugosc okna w miesiacach (np. 3 dla momentum_r3)
"""

from __future__ import annotations

from typing import Any, Dict

from engine_v2.blocks.indicators import REGISTRY
from engine_v2.blocks.indicators._month_end_common import month_end_prices, shift_to_next_month_start
from engine_v2.registry import register
from engine_v2.types import MarketData


@register(REGISTRY, "momentum_month_end")
def momentum_month_end(market_data: MarketData, params: Dict[str, Any]):
    if "window" not in params:
        raise ValueError("momentum_month_end wymaga params['window'].")

    window = int(params["window"])
    if window < 1:
        raise ValueError(f"momentum_month_end: window musi byc >= 1, dostalem {window}.")

    month_end = month_end_prices(market_data.prices)
    momentum = month_end / month_end.shift(window) - 1.0

    return shift_to_next_month_start(momentum)
