"""
ASSET FILTERS - implementacja "canary_regime_gate".

Odtwarza kanarkowy gate ze starego silnika (`best17_3m`): liczy ile z tickerow "kanarkowych"
(canary_assets) ma wskaznik <= bad_threshold (brak danych liczy sie jako "zly" - naturalne przy
porownaniu NaN, bo NaN <= X jest False, wiec musimy to potraktowac jawnie). Jesli liczba zlych
kanarkow PRZEKRACZA max_bad_count - CALA grupa docelowych aktywow (target_assets) staje sie
nieeligibilna (regime "risk-off"); w przeciwnym razie eligibilna (regime "risk-on").

Inaczej niz reszta filtrow (ktore oceniaja KAZDY ticker osobno wg JEGO WLASNEJ wartosci) - to
jest GLOBALNY gate: decyzja jest wspolna dla calej `target_assets`, oparta o OSOBNY, maly zestaw
tickerow "kanarkowych" (moze, ale nie musi, pokrywac sie z target_assets).

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (market_data: MarketData, indicator_set: IndicatorSet, params: dict) -> EligibilityMask.

params:
    canary_assets (list[str], wymagane)  - tickery kanarkowe (gauge)
    indicator_key (str, wymagane)        - klucz w indicator_set z wartoscia kanarkowa
    bad_threshold (float, wymagane)      - prog "zlego" kanarka (wskaznik <= prog = zly)
    max_bad_count (int, wymagane)        - ile zlych kanarkow jest jeszcze tolerowane (0 = nawet
                                            jeden zly kanarek wywoluje risk-off)
    target_assets (list[str], wymagane)  - ktore aktywa dostaja True/False wg tego gate'u
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.asset_filters import REGISTRY
from engine_v2.registry import register
from engine_v2.types import EligibilityMask, IndicatorSet, MarketData


@register(REGISTRY, "canary_regime_gate")
def canary_regime_gate(
    market_data: MarketData, indicator_set: IndicatorSet, params: Dict[str, Any]
) -> EligibilityMask:
    canary_assets = params.get("canary_assets")
    indicator_key = params.get("indicator_key")
    bad_threshold = params.get("bad_threshold")
    max_bad_count = params.get("max_bad_count")
    target_assets = params.get("target_assets")

    if not canary_assets or indicator_key is None or bad_threshold is None or max_bad_count is None or not target_assets:
        raise ValueError(
            "canary_regime_gate wymaga params['canary_assets'], params['indicator_key'], "
            "params['bad_threshold'], params['max_bad_count'], params['target_assets']."
        )

    if indicator_key not in indicator_set:
        raise ValueError(
            f"canary_regime_gate: brak wskaznika '{indicator_key}' w indicator_set "
            f"(dostepne: {sorted(indicator_set)})."
        )

    canary_values = indicator_set[indicator_key][canary_assets]
    is_bad = canary_values.le(bad_threshold) | canary_values.isna()
    bad_count = is_bad.sum(axis=1)

    risk_on = bad_count <= max_bad_count  # Series[bool], index=data kanarkow

    universe = list(market_data.prices.columns)
    mask = pd.DataFrame(True, index=market_data.prices.index, columns=universe)

    risk_on_aligned = risk_on.reindex(mask.index, method="ffill").fillna(False)
    for ticker in target_assets:
        mask[ticker] = risk_on_aligned

    return mask
