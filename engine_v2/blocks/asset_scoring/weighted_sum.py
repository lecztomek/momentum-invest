"""
ASSET SCORING - implementacja "weighted_sum".

Wazona suma wybranych wskaznikow z indicator_set. Uniwersalna - nie jest zaszyta na konkretne
klucze wskaznikow, tylko na to co przyjdzie w params["weights"].

Wszystkie wazone wskazniki musza dzielic ten sam index (ta sama czestotliwosc) - jesli nie,
blok rzuca czytelny blad zamiast po cichu dawac same NaN przez niedopasowanie indeksow.

`eligibility_mask` (z ASSET FILTERS) moze byc w innej czestotliwosci niz wskazniki (np. filtr
liczony na dziennych cenach, scoring na miesiecznym momentum) - dopasowywany do indeksu score
przez reindex+ffill (ostatni znany status eligibility na dana date scoringu; brak wczesniejszej
historii = traktowane jako nieeligibilne). To uproszczenie v0 - moze wymagac dopracowania
pozniej, jak dojdzie realna potrzeba.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (market_data, indicator_set, eligibility_mask, params) -> ScoreMatrix
(float DataFrame, index=data scoringu, kolumny=tickery, NaN = brak scoru / nieeligibilne).

params:
    weights (dict[str, float], wymagane) - klucz w indicator_set -> waga
"""

from __future__ import annotations

from typing import Any, Dict

from engine_v2.blocks.asset_scoring import REGISTRY
from engine_v2.registry import register
from engine_v2.types import EligibilityMask, IndicatorSet, MarketData, ScoreMatrix


@register(REGISTRY, "weighted_sum")
def weighted_sum(
    market_data: MarketData,
    indicator_set: IndicatorSet,
    eligibility_mask: EligibilityMask,
    params: Dict[str, Any],
) -> ScoreMatrix:
    weights = params.get("weights")
    if not weights:
        raise ValueError("weighted_sum wymaga params['weights'] (niepusty slownik klucz->waga).")

    missing = sorted(set(weights) - set(indicator_set))
    if missing:
        raise ValueError(
            f"weighted_sum: brak wskaznikow {missing} w indicator_set "
            f"(dostepne: {sorted(indicator_set)})."
        )

    keys = list(weights)
    reference_index = indicator_set[keys[0]].index
    for key in keys[1:]:
        if not indicator_set[key].index.equals(reference_index):
            raise ValueError(
                f"weighted_sum: wskaznik '{key}' ma inny index niz '{keys[0]}' - wszystkie "
                "wazone wskazniki musza dzielic ta sama czestotliwosc."
            )

    score = sum(indicator_set[key] * weight for key, weight in weights.items())

    aligned_eligibility = eligibility_mask.reindex(
        index=score.index, columns=score.columns, method="ffill"
    )
    return score.where(aligned_eligibility.fillna(False))
