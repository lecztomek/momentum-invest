"""
PORTFOLIO RISK ENGINE - implementacja "vaa_canary".

Keller & Keuning (2017), "Breadth Momentum and Vigilant Asset Allocation (VAA)" - wariant
G4-Aggressive-Top1 (4 aktywa ofensywne = jednoczesnie "kanarki", 3 aktywa defensywne, top-1 w
kazdym trybie).

Regula: policz ile z aktywow ofensywnych (kanarkow) ma score <= 0 ("zla szerokosc" / breadth).
Jesli WSZYSTKIE kanarki maja score > 0 - w calosci w JEDNO najlepsze aktywo OFENSYWNE (najwyzszy
score). W PRZECIWNYM RAZIE (choc jeden kanarek zly) - w calosci w JEDNO najlepsze aktywo
DEFENSYWNE (najwyzszy score wsrod defensive_assets, nie ofensywnych).

CALKOWICIE ZASTEPUJE wejsciowy target_weights wlasna logika - SELECTOR/ALPHA_WEIGHTING we
wczesniejszych blokach sa tu tylko "placeholderem" spelniajacym wymog StrategySpec (VAA nie
potrzebuje ich realnej logiki, bo caly wybor miedzy dwoma rozlacznymi zestawami aktywow dzieje
sie tutaj, na podstawie `score` z ASSET_SCORING policzonego dla calego uniwersum).

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (target_weights, market_data, indicator_set, score, params) -> TargetWeights.

params:
    offensive_assets (list[str], wymagane) - kanarki + kandydaci w trybie risk-on
    defensive_assets (list[str], wymagane) - kandydaci w trybie risk-off

Brak pelnej historii scoru (NaN, np. rozgrzewka 12-miesieczna na poczatku) - bezpiecznie pelny
"_CASH", zamiast zgadywac na niepelnych danych.
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.portfolio_risk_engine import REGISTRY
from engine_v2.registry import register
from engine_v2.types import IndicatorSet, MarketData, ScoreMatrix, TargetWeights


@register(REGISTRY, "vaa_canary")
def vaa_canary(
    target_weights: TargetWeights,
    market_data: MarketData,
    indicator_set: IndicatorSet,
    score: ScoreMatrix,
    params: Dict[str, Any],
) -> TargetWeights:
    offensive = params.get("offensive_assets")
    defensive = params.get("defensive_assets")
    if not offensive or not defensive:
        raise ValueError("vaa_canary wymaga params['offensive_assets'] i params['defensive_assets'].")

    missing = sorted((set(offensive) | set(defensive)) - set(score.columns))
    if missing:
        raise ValueError(f"vaa_canary: brak tickerow {missing} w score (sprawdz universe/indicators).")

    out = pd.DataFrame(0.0, index=target_weights.index, columns=target_weights.columns)

    for date in target_weights.index:
        offensive_scores = score.loc[date, offensive]
        if offensive_scores.isna().any():
            out.loc[date, "_CASH"] = 1.0
            continue

        if (offensive_scores > 0).all():
            best = offensive_scores.idxmax()
        else:
            defensive_scores = score.loc[date, defensive]
            if defensive_scores.isna().any():
                out.loc[date, "_CASH"] = 1.0
                continue
            best = defensive_scores.idxmax()

        out.loc[date, best] = 1.0

    return out
