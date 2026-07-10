"""
DATA CLEANER - implementacja "trim_and_interpolate".

Czysci MarketData wyprodukowane przez DATA LOADER:
  1. Rowna poczatek i koniec - przycina panel do wspolnego zakresu dat, w ktorym KAZDY ticker
     ma dane (usuwa "ogony" na poczatku/koncu, gdzie ktorys ticker jeszcze/juz nie ma cen).
  2. Uzupelnia pojedyncze luki w srodku zakresu - interpolacja liniowa miedzy sasiednimi
     znanymi wartosciami ("usrednianie" luki).

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (market_data: MarketData, params: dict) -> MarketData. Dziala na dowolnym MarketData
(dowolna liczba tickerow, dowolna czestotliwosc) - nie jest dostosowana do jednej strategii.

params:
    max_gap (int, opcjonalnie, domyslnie brak limitu) - maksymalna dlugosc luki (w wierszach),
                                                         ktora zostanie wypelniona interpolacja;
                                                         dluzsze luki zostaja NaN (nie zgadujemy
                                                         na sile, gdy dziura jest zbyt duza)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from engine_v2.blocks.data_cleaner import REGISTRY
from engine_v2.registry import register
from engine_v2.types import MarketData


def _trim_to_common_range(df: pd.DataFrame) -> pd.DataFrame:
    valid_mask = df.notna().all(axis=1)
    if not valid_mask.any():
        raise ValueError(
            "Brak choc jednego wiersza, w ktorym wszystkie tickery maja dane jednoczesnie - "
            "nie da sie ustalic wspolnego zakresu dat."
        )
    valid_idx = df.index[valid_mask]
    return df.loc[valid_idx.min():valid_idx.max()]


def _fill_internal_gaps(df: pd.DataFrame, max_gap: Optional[int]) -> pd.DataFrame:
    # limit_area="inside" pilnuje, zeby interpolacja nie wypelniala poczatku/konca serii
    # (te sa juz obciete przez _trim_to_common_range, ale poszczegolne kolumny moga wciaz miec
    # krotsze wewnetrzne odcinki wazne).
    return df.interpolate(method="linear", limit=max_gap, limit_area="inside")


@register(REGISTRY, "trim_and_interpolate")
def trim_and_interpolate(market_data: MarketData, params: Dict[str, Any]) -> MarketData:
    max_gap = params.get("max_gap")

    prices = _fill_internal_gaps(_trim_to_common_range(market_data.prices), max_gap)
    returns = _fill_internal_gaps(_trim_to_common_range(market_data.returns), max_gap)

    return MarketData(prices=prices, returns=returns)
