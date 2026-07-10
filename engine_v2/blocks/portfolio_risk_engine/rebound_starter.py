"""
PORTFOLIO RISK ENGINE - implementacja "rebound_starter".

Odtwarza "rebound starter" ze starego silnika (`best17_3m`): jesli docelowe wagi na dana date sa
w calosci "_CASH" (portfel byl w calosci cash, np. przez canary_regime_gate), a WSKAZANY ticker
(zwykle szeroki benchmark, np. vt.us) ma wlasny wskaznik momentum POWYZEJ progu - zamiast cash
wchodzimy w calosci w ten ticker. Poza tym przypadkiem target_weights zostaja bez zmian.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (target_weights, market_data, indicator_set, score, params) -> TargetWeights.

params:
    rebound_ticker (str, wymagane)     - ticker wchodzacy zamiast cash (np. "vt.us")
    indicator_key (str, wymagane)      - klucz w indicator_set z jego momentum
    threshold (float, wymagane)        - prog momentum wymagany do "odbicia"
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.portfolio_risk_engine import REGISTRY
from engine_v2.registry import register
from engine_v2.types import IndicatorSet, MarketData, ScoreMatrix, TargetWeights


@register(REGISTRY, "rebound_starter")
def rebound_starter(
    target_weights: TargetWeights,
    market_data: MarketData,
    indicator_set: IndicatorSet,
    score: ScoreMatrix,
    params: Dict[str, Any],
) -> TargetWeights:
    rebound_ticker = params.get("rebound_ticker")
    indicator_key = params.get("indicator_key")
    threshold = params.get("threshold")
    if not rebound_ticker or indicator_key is None or threshold is None:
        raise ValueError(
            "rebound_starter wymaga params['rebound_ticker'], params['indicator_key'], "
            "params['threshold']."
        )

    if indicator_key not in indicator_set:
        raise ValueError(
            f"rebound_starter: brak wskaznika '{indicator_key}' w indicator_set "
            f"(dostepne: {sorted(indicator_set)})."
        )
    if rebound_ticker not in target_weights.columns:
        raise ValueError(f"rebound_starter: '{rebound_ticker}' nie jest kolumna target_weights.")

    out = target_weights.copy()
    rebound_indicator = indicator_set[indicator_key]

    is_full_cash = (out.get("_CASH", 0.0) >= 1.0 - 1e-9) & (
        out.drop(columns=["_CASH"], errors="ignore").abs().sum(axis=1) <= 1e-9
    )

    for date in out.index[is_full_cash]:
        if date not in rebound_indicator.index:
            continue
        value = rebound_indicator.loc[date, rebound_ticker]
        if pd.notna(value) and value > threshold:
            out.loc[date, :] = 0.0
            out.loc[date, rebound_ticker] = 1.0

    return out
