"""
INDICATORS - implementacja "ema_ratio_monthly".

Odtwarza `ema_over_ema` ze starego silnika (`engine/build_data.py`): EMA(fast_span)/EMA(slow_span)
- 1, liczone na cenach KONCA KAZDEGO MIESIACA (nie startu), spany w miesiacach. Wynik przesuniety
o jeden miesiac do przodu (patrz `_month_end_common.shift_to_next_month_start`) - wartosc
policzona z danych do konca miesiaca M jest "znana"/uzywana dopiero na starcie miesiaca M+1,
dokladnie jak w oryginale.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu), tylko odtwarza
ten sam wzor.

Kontrakt: (market_data: MarketData, params: dict) -> pd.DataFrame (index=poczatki miesiecy,
kolumny=tickery).

params:
    fast_span (int, wymagane) - rozpietosc szybszej EMA w miesiacach
    slow_span (int, wymagane) - rozpietosc wolniejszej EMA w miesiacach
"""

from __future__ import annotations

from typing import Any, Dict

from engine_v2.blocks.indicators import REGISTRY
from engine_v2.blocks.indicators._month_end_common import month_end_prices, shift_to_next_month_start
from engine_v2.registry import register
from engine_v2.types import MarketData


@register(REGISTRY, "ema_ratio_monthly")
def ema_ratio_monthly(market_data: MarketData, params: Dict[str, Any]):
    if "fast_span" not in params or "slow_span" not in params:
        raise ValueError("ema_ratio_monthly wymaga params['fast_span'] i params['slow_span'].")

    fast_span = int(params["fast_span"])
    slow_span = int(params["slow_span"])
    if fast_span < 1 or slow_span < 1:
        raise ValueError("ema_ratio_monthly: fast_span/slow_span musza byc >= 1.")

    month_end = month_end_prices(market_data.prices)
    ema_fast = month_end.ewm(span=fast_span, adjust=False).mean()
    ema_slow = month_end.ewm(span=slow_span, adjust=False).mean()
    ratio = ema_fast / ema_slow - 1.0

    return shift_to_next_month_start(ratio)
