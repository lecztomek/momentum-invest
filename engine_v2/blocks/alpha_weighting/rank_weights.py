"""
ALPHA WEIGHTING - implementacja "rank_weights".

Przypisuje ustalone wagi wg pozycji w rankingu score, WSROD JUZ WYBRANYCH przez SELECTOR:
najlepszy (najwyzszy score) dostaje weights[0], drugi weights[1], itd.

Jesli wybranych tickerow jest MNIEJ niz dlugosc listy wag - domyslnie (redistribute_if_short=False)
nadwyzka (1 - suma przypisanych wag) idzie do "_CASH" (nie forsujemy pelnej inwestycji, jesli
SELECTOR nie dostarczyl tylu kandydatow). Z redistribute_if_short=True zamiast tego wagi
UZYWANE (weights[:len(selected)]) sa renormalizowane do sumy 1.0 - odtwarza to
`build_rank_weight_target` ze starego silnika (`engine/backtest_hybrid_search.py`), ktory ZAWSZE
zostaje w pelni zainwestowany: przy top_n=2 i tylko 1 dostepnym kandydacie, stary silnik daje mu
100% (nie weights[0]=0.8 + 20% cash). Sprawdzone bezposrednio na `best17_a` (2009-10-01: stary
silnik {"iau.us": 1.0}, engine_v2 bez tej flagi {"iau.us": 0.8, "_CASH": 0.2}) - to byla ostatnia,
znaczaca przyczyna rozjazdu po naprawie rozgrzewki wskaznikow i indeksow kanarka (patrz README,
sekcja "Znany, naprawiony bug (5)").

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
    redistribute_if_short (bool, opcjonalnie, domyslnie False) - patrz opis wyzej
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
    redistribute_if_short = bool(params.get("redistribute_if_short", False))

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
        usable_weights = list(weights_list[: len(ranked)])
        if redistribute_if_short and len(ranked) < len(weights_list):
            total = sum(usable_weights)
            if total > 0:
                usable_weights = [w / total for w in usable_weights]

        assigned = 0.0
        for ticker, weight in zip(ranked, usable_weights):
            out.loc[date, ticker] = weight
            assigned += weight
        out.loc[date, "_CASH"] = 1.0 - assigned

    return out
