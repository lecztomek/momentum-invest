"""
ALPHA WEIGHTING - implementacja "rounded_score_weights".

Wagi PROPORCJONALNE do score wsrod juz WYBRANYCH przez SELECTOR, zaokraglone do bloku
`round_to` (domyslnie 0.10 = 10 punktow procentowych), z gwarantowanym MINIMUM
`min_weight_blocks` blokow na kazdy wybrany ticker - zbudowane pod strategie typu "all-weather",
gdzie kilka klas aktywow (np. akcje/obligacje/zloto/surowce) ma byc ZAWSZE jednoczesnie
trzymanych (nigdy calkowicie wyzerowanych), a SILA wzgledna (score) tylko PRZECHYLA alokacje
wokol tego minimum, nie decyduje o wejsciu/wyjsciu.

Algorytm na kazda date:
1. `total_blocks = round(1.0 / round_to)` (np. 10 dla round_to=0.10).
2. Kazdy z N wybranych tickerow dostaje NAJPIERW `min_weight_blocks` blokow (gwarantowane
   minimum) - zuzywa to `N * min_weight_blocks` blokow.
3. Pozostale `total_blocks - N*min_weight_blocks` blokow ("dyskrecjonalna pula") rozdzielane sa
   PROPORCJONALNIE do wzglednej sily (`score - min(score)` wsrod wybranych, przesuniete zeby
   najslabszy mial 0 - jesli wszystkie rowne, po rowno) metoda NAJWIEKSZEJ RESZTY (Largest
   Remainder / Hamilton): idealne, uamkowe przydzialy sa zaokraglane w dol, a brakujace bloki
   (do wyzerowania reszty) trafiaja do tickerow z NAJWIEKSZA czescia ulamkowa (remisy: wyzszy
   score, potem alfabetycznie - w pelni deterministyczne).
4. Suma blokow zawsze wynosi dokladnie `total_blocks` (wagi zawsze sumuja sie do 1.0, bez dryfu
   zaokraglen) - to jest cala racja bytu metody najwiekszej reszty zamiast naiwnego
   `round(ideal_weight, -1)` na kazdym tickerze z osobna (to NIE gwarantuje sumy 1.0).

Jesli SELECTOR wybral 0 tickerow (np. przejsciowo, przed rozgrzewka wskaznikow) - 100% cash,
tak jak inne implementacje tego bloku.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (selection: TargetSelection, score: ScoreMatrix, indicator_set: IndicatorSet,
params: dict) -> TargetWeights.

params:
    round_to (float, opcjonalnie, domyslnie 0.10)         - wielkosc bloku zaokraglenia
    min_weight_blocks (int, opcjonalnie, domyslnie 1)     - gwarantowane minimum blokow/ticker
"""

from __future__ import annotations

import math
from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.alpha_weighting import REGISTRY
from engine_v2.registry import register
from engine_v2.types import IndicatorSet, ScoreMatrix, TargetSelection, TargetWeights


def _allocate_blocks(strengths: Dict[str, float], remaining_blocks: int) -> Dict[str, int]:
    """Largest Remainder Method: rozdziela `remaining_blocks` calkowitych blokow proporcjonalnie
    do `strengths` (nieujemne wagi wzgledne). Zwraca ticker -> liczba dodatkowych blokow."""
    tickers = list(strengths)
    total_strength = sum(strengths.values())

    if remaining_blocks <= 0 or not tickers:
        return {t: 0 for t in tickers}

    if total_strength <= 0:
        # brak sily wzglednej (wszystkie score rowne) - rozdzielamy po rowno
        strengths = {t: 1.0 for t in tickers}
        total_strength = float(len(tickers))

    ideal = {t: remaining_blocks * s / total_strength for t, s in strengths.items()}
    floor_blocks = {t: math.floor(v) for t, v in ideal.items()}
    remainder = {t: ideal[t] - floor_blocks[t] for t in tickers}

    deficit = remaining_blocks - sum(floor_blocks.values())
    # sortowanie: najwieksza reszta pierwsza; remisy - wyzsza pierwotna sila, potem alfabetycznie
    order = sorted(tickers, key=lambda t: (-remainder[t], -strengths[t], t))

    extra = {t: 0 for t in tickers}
    for t in order[:deficit]:
        extra[t] = 1

    return {t: floor_blocks[t] + extra[t] for t in tickers}


@register(REGISTRY, "rounded_score_weights")
def rounded_score_weights(
    selection: TargetSelection, score: ScoreMatrix, indicator_set: IndicatorSet, params: Dict[str, Any]
) -> TargetWeights:
    round_to = float(params.get("round_to", 0.10))
    min_weight_blocks = int(params.get("min_weight_blocks", 1))

    if round_to <= 0 or round_to > 1.0:
        raise ValueError("rounded_score_weights: round_to musi byc w przedziale (0, 1].")
    if min_weight_blocks < 0:
        raise ValueError("rounded_score_weights: min_weight_blocks nie moze byc ujemny.")

    total_blocks = round(1.0 / round_to)
    if abs(total_blocks * round_to - 1.0) > 1e-9:
        raise ValueError(f"rounded_score_weights: round_to={round_to} nie dzieli 1.0 na rowne bloki.")

    out = pd.DataFrame(0.0, index=selection.index, columns=list(selection.columns) + ["_CASH"])

    for date in selection.index:
        selected = list(selection.columns[selection.loc[date]])

        if not selected:
            out.loc[date, "_CASH"] = 1.0
            continue

        if len(selected) * min_weight_blocks > total_blocks:
            raise ValueError(
                f"rounded_score_weights: {date} ma {len(selected)} wybranych tickerow, ale "
                f"min_weight_blocks={min_weight_blocks} wymagaloby {len(selected) * min_weight_blocks} "
                f"blokow z {total_blocks} dostepnych (round_to={round_to})."
            )

        scores = {t: float(score.loc[date, t]) for t in selected}
        min_score = min(scores.values())
        strengths = {t: s - min_score for t, s in scores.items()}

        remaining_blocks = total_blocks - len(selected) * min_weight_blocks
        extra_blocks = _allocate_blocks(strengths, remaining_blocks)

        for ticker in selected:
            blocks = min_weight_blocks + extra_blocks[ticker]
            out.loc[date, ticker] = blocks * round_to

    return out
