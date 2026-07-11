"""
ASSET SCORING - implementacja "momentum_times_decorrelation".

Docelowo dla GPM ("Generalized Protective Momentum", `strategies_v2/gpm/`):
score = momentum * (1 - korelacja do koszyka). Dwa gotowe wskazniki z indicator_set
(momentum_key, corr_key) sa mnozone element po elemencie - w odroznieniu od `weighted_sum`
(liniowa suma wazona wielu wskaznikow), tu potrzebny jest ILOCZYN dwoch konkretnych wskaznikow,
zeby premiowac aktywa jednoczesnie o wysokim momentum I niskiej korelacji do reszty rynku (niska
korelacja mnozy wynik w gore, wysoka korelacja go tlumi - nawet przy silnym momentum).

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (market_data, indicator_set, eligibility_mask, params) -> ScoreMatrix
(float DataFrame, index=data scoringu, kolumny=tickery, NaN = brak scoru / nieeligibilne).

params:
    momentum_key (str, wymagane) - klucz w indicator_set ze wskaznikiem momentum ("r")
    corr_key (str, wymagane)     - klucz w indicator_set z korelacja do koszyka ("c")
"""

from __future__ import annotations

from typing import Any, Dict

from engine_v2.blocks.asset_scoring import REGISTRY
from engine_v2.registry import register
from engine_v2.types import EligibilityMask, IndicatorSet, MarketData, ScoreMatrix


@register(REGISTRY, "momentum_times_decorrelation")
def momentum_times_decorrelation(
    market_data: MarketData,
    indicator_set: IndicatorSet,
    eligibility_mask: EligibilityMask,
    params: Dict[str, Any],
) -> ScoreMatrix:
    momentum_key = params.get("momentum_key")
    corr_key = params.get("corr_key")
    if not momentum_key or not corr_key:
        raise ValueError(
            "momentum_times_decorrelation wymaga params['momentum_key'] i params['corr_key']."
        )
    missing = sorted({momentum_key, corr_key} - set(indicator_set))
    if missing:
        raise ValueError(
            f"momentum_times_decorrelation: brak wskaznikow {missing} w indicator_set "
            f"(dostepne: {sorted(indicator_set)})."
        )

    momentum = indicator_set[momentum_key]
    corr = indicator_set[corr_key]
    if not momentum.index.equals(corr.index):
        raise ValueError(
            "momentum_times_decorrelation: momentum_key i corr_key musza dzielic ten sam index."
        )

    score = momentum * (1.0 - corr)

    aligned_eligibility = eligibility_mask.reindex(
        index=score.index, columns=score.columns, method="ffill"
    )
    return score.where(aligned_eligibility.fillna(False))
