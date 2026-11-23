"""
INDICATORS - implementacja "momentum_avg_month_end".

Srednia momentum z kilku okien (np. 1/3/6/12 miesiecy), liczona na cenach KONCA miesiaca (ten
sam schemat co `momentum_month_end` - patrz `_month_end_common.py`), z etykieta przesunieta o
jeden miesiac do przodu. Docelowo dla GPM ("Generalized Protective Momentum",
`strategies_v2/gpm/`): r = (zwrot_1M + zwrot_3M + zwrot_6M + zwrot_12M) / 4.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (market_data: MarketData, params: dict) -> pd.DataFrame (index=poczatki miesiecy,
kolumny=tickery).

params:
    windows (list[int], wymagane) - dlugosci okien w miesiacach do usrednienia
    execution_day_of_month (int, opcjonalne) - gdy podany, liczy na cenie z dnia wykonania
                                tego samego miesiaca zamiast z konca poprzedniego (patrz
                                `_month_end_common.py`); MUSI zgadzac sie z `data_loader`
"""

from __future__ import annotations

from typing import Any, Dict

from engine_v2.blocks.indicators import REGISTRY
from engine_v2.blocks.indicators._month_end_common import anchored_prices, label_to_execution_month
from engine_v2.registry import register
from engine_v2.types import MarketData


@register(REGISTRY, "momentum_avg_month_end")
def momentum_avg_month_end(market_data: MarketData, params: Dict[str, Any]):
    windows = params.get("windows")
    if not windows:
        raise ValueError(
            "momentum_avg_month_end wymaga params['windows'] (niepusta lista okien w miesiacach)."
        )

    anchored = anchored_prices(market_data.prices, params)

    total = None
    for window in windows:
        window = int(window)
        if window < 1:
            raise ValueError(f"momentum_avg_month_end: kazde okno musi byc >= 1, dostalem {window}.")
        momentum = anchored / anchored.shift(window) - 1.0
        total = momentum if total is None else total + momentum

    average = total / len(windows)
    return label_to_execution_month(average, params)
