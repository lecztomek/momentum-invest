"""
ASSET FILTERS - implementacja "price_above_indicator".

Filtr trendu: aktywo przechodzi (True), jesli jego cena jest POWYZEJ podanego wskaznika
(np. SMA200) w danym dniu.

Kazdy filtr moze byc ograniczony do podzbioru uniwersum przez param "assets": domyslnie
(brak albo "all") dotyczy wszystkich tickerow; jesli podana lista tickerow, filtr liczy sie
TYLKO dla nich - pozostale tickery automatycznie przechodza (patrz `_common.apply_asset_scope`).

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (market_data: MarketData, indicator_set: IndicatorSet, params: dict) -> EligibilityMask
(bool DataFrame, index=data, kolumny=tickery z market_data.prices).

params:
    indicator_key (str, wymagane)          - klucz w indicator_set do porownania z cena
    assets (list[str] | "all", opcjonalnie, domyslnie "all") - do jakich tickerow filtr sie stosuje
"""

from __future__ import annotations

from typing import Any, Dict

from engine_v2.blocks.asset_filters import REGISTRY
from engine_v2.blocks.asset_filters._common import apply_asset_scope
from engine_v2.registry import register
from engine_v2.types import EligibilityMask, IndicatorSet, MarketData


@register(REGISTRY, "price_above_indicator")
def price_above_indicator(
    market_data: MarketData, indicator_set: IndicatorSet, params: Dict[str, Any]
) -> EligibilityMask:
    if "indicator_key" not in params:
        raise ValueError("price_above_indicator wymaga params['indicator_key'].")

    indicator_key = params["indicator_key"]
    if indicator_key not in indicator_set:
        raise ValueError(
            f"Brak wskaznika '{indicator_key}' w indicator_set (dostepne: {sorted(indicator_set)})."
        )

    raw_mask = market_data.prices > indicator_set[indicator_key]

    universe = list(market_data.prices.columns)
    return apply_asset_scope(raw_mask, universe, params.get("assets"))
