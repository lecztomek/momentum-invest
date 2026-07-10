"""
PORTFOLIO RISK ENGINE - implementacja "none".

Pass-through: zwraca target_weights bez zmian. Dla strategii, ktore nie potrzebuja zadnego
mechanizmu skalowania ryzyka na poziomie calego portfela.

Kontrakt: (target_weights: TargetWeights, market_data: MarketData, indicator_set: IndicatorSet,
score: ScoreMatrix, params: dict) -> TargetWeights.
"""

from __future__ import annotations

from typing import Any, Dict

from engine_v2.blocks.portfolio_risk_engine import REGISTRY
from engine_v2.registry import register
from engine_v2.types import IndicatorSet, MarketData, ScoreMatrix, TargetWeights


@register(REGISTRY, "none")
def none(
    target_weights: TargetWeights,
    market_data: MarketData,
    indicator_set: IndicatorSet,
    score: ScoreMatrix,
    params: Dict[str, Any],
) -> TargetWeights:
    return target_weights.copy()
