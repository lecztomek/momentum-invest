"""
ALPHA WEIGHTING - implementacja "inverse_vol".

Wazy JUZ WYBRANYCH przez SELECTOR odwrotnie proporcjonalnie do ich zmiennosci (wskaznik z
indicator_set, np. `volatility_daily`) - mniej zmienne aktywo dostaje wieksza wage. Zawsze w
pelni inwestuje wsrod wybranych (suma wag wybranych = 1, "_CASH" = 0) - w przeciwienstwie do
`rank_weights` nie ma tu pojecia "oczekiwanej liczby" pozycji do porownania z faktyczna liczba
wybranych, wiec nie ma naturalnego powodu zostawiac cash (chyba ze SELECTOR nic nie wybral).

Zmiennosc moze byc w innej czestotliwosci niz selection/score (np. dzienna vs miesieczna
selection) - dopasowywana przez reindex+ffill (ten sam mechanizm co w `asset_scoring.weighted_sum`
dla eligibility_mask).

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (selection: TargetSelection, score: ScoreMatrix, indicator_set: IndicatorSet,
params: dict) -> TargetWeights. `score` nie jest tu uzywany (inverse_vol nie zaleznosci od
rankingu score), ale jest czescia kontraktu wspolnego dla wszystkich implementacji tego bloku.

params:
    volatility_key (str, wymagane) - klucz w indicator_set ze zmiennoscia
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.alpha_weighting import REGISTRY
from engine_v2.registry import register
from engine_v2.types import IndicatorSet, ScoreMatrix, TargetSelection, TargetWeights


@register(REGISTRY, "inverse_vol")
def inverse_vol(
    selection: TargetSelection, score: ScoreMatrix, indicator_set: IndicatorSet, params: Dict[str, Any]
) -> TargetWeights:
    volatility_key = params.get("volatility_key")
    if not volatility_key:
        raise ValueError("inverse_vol wymaga params['volatility_key'].")

    if volatility_key not in indicator_set:
        raise ValueError(
            f"inverse_vol: brak wskaznika '{volatility_key}' w indicator_set "
            f"(dostepne: {sorted(indicator_set)})."
        )

    volatility = indicator_set[volatility_key].reindex(
        index=selection.index, columns=selection.columns, method="ffill"
    )

    out = pd.DataFrame(0.0, index=selection.index, columns=list(selection.columns) + ["_CASH"])

    for date in selection.index:
        selected = selection.columns[selection.loc[date]]

        if len(selected) == 0:
            out.loc[date, "_CASH"] = 1.0
            continue

        vol_at_date = volatility.loc[date, selected]
        if vol_at_date.isna().any() or (vol_at_date <= 0).any():
            raise ValueError(
                f"inverse_vol: brak lub niepoprawna (<=0) zmiennosc dla wybranych tickerow w {date}: "
                f"{vol_at_date.to_dict()}."
            )

        inv_vol = 1.0 / vol_at_date
        weights = inv_vol / inv_vol.sum()
        for ticker, weight in weights.items():
            out.loc[date, ticker] = weight

    return out
