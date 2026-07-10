"""
ASSET FILTERS - implementacja "never_eligible".

Trwale wyklucza podane tickery z normalnego rankingu/selekcji (np. ticker uzywany WYLACZNIE jako
kanarek/gauge, nigdy jako kandydat do wyboru - jak "vt.us" w `best17_3m`, ktory wchodzi do
portfela tylko przez PORTFOLIO_RISK_ENGINE.rebound_starter, nie przez zwykla sciezke
filtry->scoring->selector).

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (market_data: MarketData, indicator_set: IndicatorSet, params: dict) -> EligibilityMask.

WAZNE: maska musi byc indeksowana TAK SAMO jak wskazniki (np. miesiecznie), NIE jak
`market_data.prices` (zawsze DZIENNIE, niezaleznie od `frequency` strategii). Inaczej
`_run_asset_filters` laczac ta maske (`&`) z innymi filtrami dostaje dwa niedopasowane indeksy -
patrz `canary_regime_gate.py` (ten sam bug, tam opisany szerzej) i README, sekcja "Znany,
naprawiony bug (3)". Bierzemy indeks DOWOLNEGO wskaznika z `indicator_set` (wszystkie musza
dzielic ta sama czestotliwosc - wymog `asset_scoring.weighted_sum`); brak wskaznikow w ogole =
fallback na `market_data.prices.index`.

params:
    assets (list[str], wymagane) - tickery zawsze nieeligibilne
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.asset_filters import REGISTRY
from engine_v2.registry import register
from engine_v2.types import EligibilityMask, IndicatorSet, MarketData


@register(REGISTRY, "never_eligible")
def never_eligible(
    market_data: MarketData, indicator_set: IndicatorSet, params: Dict[str, Any]
) -> EligibilityMask:
    assets = params.get("assets")
    if not assets:
        raise ValueError("never_eligible wymaga params['assets'] (niepusta lista tickerow).")

    reference_index = next(iter(indicator_set.values())).index if indicator_set else market_data.prices.index
    mask = pd.DataFrame(True, index=reference_index, columns=market_data.prices.columns)
    for ticker in assets:
        if ticker not in mask.columns:
            raise ValueError(f"never_eligible: nieznany ticker '{ticker}'.")
        mask[ticker] = False

    return mask
