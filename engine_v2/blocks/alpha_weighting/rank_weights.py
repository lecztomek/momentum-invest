"""
ALPHA WEIGHTING - implementacja "rank_weights".

Przypisuje ustalone wagi wg pozycji w rankingu score, WSROD JUZ WYBRANYCH przez SELECTOR:
najlepszy (najwyzszy score) dostaje weights[0], drugi weights[1], itd.

Jesli wybranych tickerow jest MNIEJ niz dlugosc listy wag, nadwyzka (1 - suma przypisanych wag)
ide do "_CASH" - nie forsujemy pelnej inwestycji, jesli SELECTOR nie dostarczyl tylu kandydatow.
Jesli wybranych jest WIECEJ niz dlugosc listy wag (niespojna konfiguracja SELECTOR/params), blok
rzuca czytelny blad zamiast po cichu ucinac nadwyzke.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (selection: TargetSelection, score: ScoreMatrix, indicator_set: IndicatorSet,
params: dict) -> TargetWeights (float DataFrame, index=data, kolumny=tickery z selection +
"_CASH", suma w wierszu = 1). `indicator_set` nie jest tu uzywany (rank_weights potrzebuje
tylko score), ale jest czescia kontraktu WSPOLNEGO dla wszystkich implementacji tego bloku - np.
`inverse_vol` go potrzebuje (zmiennosc z indicator_set), wiec orchestrator woła kazda
implementacje tak samo.

params:
    weights (list[float], wymagane) - wagi malejaco wg rankingu (np. [0.8, 0.2] dla top2)
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.alpha_weighting import REGISTRY
from engine_v2.registry import register
from engine_v2.types import IndicatorSet, ScoreMatrix, TargetSelection, TargetWeights


@register(REGISTRY, "rank_weights")
def rank_weights(
    selection: TargetSelection, score: ScoreMatrix, indicator_set: IndicatorSet, params: Dict[str, Any]
) -> TargetWeights:
    weights_list = params.get("weights")
    if not weights_list:
        raise ValueError("rank_weights wymaga params['weights'] (niepusta lista wag malejaco wg rankingu).")

    out = pd.DataFrame(0.0, index=selection.index, columns=list(selection.columns) + ["_CASH"])

    for date in selection.index:
        selected = selection.columns[selection.loc[date]]

        if len(selected) == 0:
            out.loc[date, "_CASH"] = 1.0
            continue

        if len(selected) > len(weights_list):
            raise ValueError(
                f"rank_weights: {date} ma {len(selected)} wybranych tickerow, ale tylko "
                f"{len(weights_list)} wag w params['weights']."
            )

        ranked = score.loc[date, selected].sort_values(ascending=False).index
        assigned = 0.0
        for ticker, weight in zip(ranked, weights_list):
            out.loc[date, ticker] = weight
            assigned += weight
        out.loc[date, "_CASH"] = 1.0 - assigned

    return out
