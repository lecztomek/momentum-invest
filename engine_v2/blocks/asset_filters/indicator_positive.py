"""
ASSET FILTERS - implementacja "indicator_positive".

Filtr absolutnego momentum (i podobnych): aktywo przechodzi (True), jesli wartosc wskaznika w
`indicator_set` jest POWYZEJ progu (domyslnie 0.0) w danym okresie - np. "wlasny 12-miesieczny
momentum > 0". Inaczej niz `price_above_indicator` (porownuje CENE do wskaznika), tu porownuje
sam wskaznik do STALEJ liczby.

Kazdy filtr moze byc ograniczony do podzbioru uniwersum przez param "assets" - patrz
`_common.apply_asset_scope` (ten sam mechanizm co w `price_above_indicator`).

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (market_data: MarketData, indicator_set: IndicatorSet, params: dict) -> EligibilityMask.

params:
    indicator_key (str, wymagane)                    - klucz w indicator_set do porownania
    threshold (float, opcjonalnie, domyslnie 0.0)     - prog
    assets (list[str] | "all", opcjonalnie, domyslnie "all")
"""

from __future__ import annotations

from typing import Any, Dict

from engine_v2.blocks.asset_filters import REGISTRY
from engine_v2.blocks.asset_filters._common import apply_asset_scope
from engine_v2.registry import register
from engine_v2.types import EligibilityMask, IndicatorSet, MarketData


@register(REGISTRY, "indicator_positive")
def indicator_positive(
    market_data: MarketData, indicator_set: IndicatorSet, params: Dict[str, Any]
) -> EligibilityMask:
    if "indicator_key" not in params:
        raise ValueError("indicator_positive wymaga params['indicator_key'].")

    indicator_key = params["indicator_key"]
    if indicator_key not in indicator_set:
        raise ValueError(
            f"Brak wskaznika '{indicator_key}' w indicator_set (dostepne: {sorted(indicator_set)})."
        )

    threshold = float(params.get("threshold", 0.0))
    raw_mask = indicator_set[indicator_key] > threshold

    universe = list(market_data.prices.columns)
    return apply_asset_scope(raw_mask, universe, params.get("assets"))
