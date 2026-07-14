"""
PORTFOLIO RISK ENGINE - implementacja "daa_canary_breadth_switch".

Keller & Keuning (2017), "Breadth Momentum and the Canary Universe: Defensive Asset
Allocation" (DAA). Rozni sie od `vaa_canary` na dwa sposoby:

1. Kanarki sa OSOBNYM, MALYM uniwersum (`canary_assets`), NIE calym `offensive_assets` jak w
   VAA - w klasycznym DAA-G4 kanarek to tylko 2 z 4 aktywow ofensywnych (np. VWO+AGG), nie
   wszystkie 4.
2. Udzial ochronny jest CIAGLY (proporcjonalny do szerokosci), nie binarny: policz `b` = liczbe
   kanarkow z score <= 0 (NaN traktowane jako "zly" - ten sam wzorzec co
   `canary_regime_gate.is_bad`), udzial ochronny (cash fraction) = min(1.0, b / breadth_denominator).
   Domyslnie `breadth_denominator = len(canary_assets)` (dla 2 kanarkow: 0/2=0% oba dobre,
   1/2=50% jeden zly, 2/2=100% oba zle) - ALE to jest tylko domyslna wartosc, NIE ogolna regula
   DAA: w oryginalnej pracy Keller/Keuning `breadth_denominator` (tam nazywane "B") jest OSOBNYM
   parametrem od liczby kanarkow, dobieranym per wariant (DAA-G4: B=1 mimo 2 kanarkow - JEDEN zly
   kanarek juz daje 100% ochrony, DAA-G12: B=2 - dopiero wtedy udzial jest naprawde ciagly
   0/50/100%). Patrz `strategies_v2/daa_g4_keller/` (2026-07-14), gdzie ten parametr jest
   faktycznie ustawiony inaczej niz liczba kanarkow.

Reszta: top `top_n_offensive` aktywow ofensywnych wg `score` (NAJLEPSZE DOSTEPNE, bez wzgledu na
znak - inaczej niz `gem_dual_momentum_switch`, DAA nie wymaga dodatniego momentum do wejscia w
ofensywne, sam udzial ochronny juz to kompensuje) dostaje `(1 - cash_fraction)` po rowno; top
`top_n_defensive` aktywow obronnych wg `score` dostaje `cash_fraction` po rowno.

**"Easy Trading" - dynamiczne zmniejszanie liczby aktywow ofensywnych** (user, po zobaczeniu
wyniku `daa_g4_keller` z T=4/B=2: "Blad jest przy 1 zlym kanarku. Keller powinien wtedy miec:
top 2 aktywa po 25% + 50% defensywnie. Repo nadal trzyma top 4 po 12,5% + 50% defensywnie.")
- w oryginalnej metodyce Kellera liczba TRZYMANYCH aktyw ofensywnych NIE jest stala na
`top_n_offensive` - kurczy sie proporcjonalnie do `cash_fraction`:
`t = round((1 - cash_fraction) * top_n_offensive)`. Dla T=4/B=2 przy 1 zlym kanarku:
`cash_fraction=0.5`, `t=round(0.5*4)=2` -> top-2 (nie top-4) dzieli `(1-cash_fraction)=50%` po
rowno = 25% kazde (nie top-4 po 12,5%). WLACZANE opcjonalnym `scale_top_n_with_cash_fraction`
(domyslnie `False` - istniejacy `daa_g4` BEZ ZMIAN zachowania, ta funkcja z T=1 dawalaby
degenerowane `t=round(0.5)=0` przy 1 zlym kanarku z 2, banker's rounding - dlatego NIE jest
wlaczona domyslnie, tylko jawnie dla wariantow z wiekszym T jak `daa_g4_keller`).

Brak wystarczajacej historii (NaN) - bezpiecznie: kanarek z NaN liczy sie jako "zly" (pcha w
strone wiekszej ochrony); jesli w danej "nodze" (ofensywnej albo obronnej) brak JAKIEGOKOLWIEK
uzywalnego kandydata, przypisana jej czesc kapitalu idzie w "_CASH" zamiast zgadywac.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (target_weights, market_data, indicator_set, score, params) -> TargetWeights.

params:
    offensive_assets (list[str], wymagane) - kandydaci "ryzykowni"
    defensive_assets (list[str], wymagane) - kandydaci "obronni"
    canary_assets (list[str], wymagane)    - OSOBNE, male uniwersum tylko do pomiaru szerokosci
                                              (moze, ale nie musi, pokrywac sie z offensive_assets)
    top_n_offensive (int, opcjonalnie, domyslnie 1) - MAKSYMALNA liczba aktyw ofensywnych (przy
        cash_fraction=0); patrz `scale_top_n_with_cash_fraction` - rzeczywista liczba trzymanych
        aktyw moze byc MNIEJSZA, gdy ta opcja jest wlaczona.
    top_n_defensive (int, opcjonalnie, domyslnie 1)
    breadth_denominator (float, opcjonalnie, domyslnie len(canary_assets)) - mianownik "B" w
        cash_fraction = min(1.0, b / breadth_denominator). Ustaw NIZEJ niz len(canary_assets),
        zeby MNIEJ zlych kanarkow wymuszalo pelna ochrone (np. DAA-G4: B=1 z 2 kanarkami).
    scale_top_n_with_cash_fraction (bool, opcjonalnie, domyslnie False) - "Easy Trading": liczba
        TRZYMANYCH aktyw ofensywnych = round((1 - cash_fraction) * top_n_offensive), nie stale
        top_n_offensive. Patrz docstring modulu.
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.portfolio_risk_engine import REGISTRY
from engine_v2.registry import register
from engine_v2.types import IndicatorSet, MarketData, ScoreMatrix, TargetWeights


@register(REGISTRY, "daa_canary_breadth_switch")
def daa_canary_breadth_switch(
    target_weights: TargetWeights,
    market_data: MarketData,
    indicator_set: IndicatorSet,
    score: ScoreMatrix,
    params: Dict[str, Any],
) -> TargetWeights:
    offensive_assets = params.get("offensive_assets")
    defensive_assets = params.get("defensive_assets")
    canary_assets = params.get("canary_assets")
    top_n_offensive = int(params.get("top_n_offensive", 1))
    top_n_defensive = int(params.get("top_n_defensive", 1))
    scale_top_n_with_cash_fraction = bool(params.get("scale_top_n_with_cash_fraction", False))

    if not offensive_assets or not defensive_assets or not canary_assets:
        raise ValueError(
            "daa_canary_breadth_switch wymaga params['offensive_assets'], "
            "params['defensive_assets'] i params['canary_assets']."
        )

    breadth_denominator = float(params.get("breadth_denominator", len(canary_assets)))
    if breadth_denominator <= 0.0:
        raise ValueError("daa_canary_breadth_switch: params['breadth_denominator'] musi byc > 0.")

    missing = sorted((set(offensive_assets) | set(defensive_assets) | set(canary_assets)) - set(score.columns))
    if missing:
        raise ValueError(f"daa_canary_breadth_switch: brak tickerow {missing} w score.")

    out = pd.DataFrame(0.0, index=target_weights.index, columns=target_weights.columns)

    for date in target_weights.index:
        canary_scores = score.loc[date, canary_assets]
        is_bad = (canary_scores <= 0.0) | canary_scores.isna()
        cash_fraction = min(1.0, float(is_bad.sum()) / breadth_denominator)

        offensive_ranked = score.loc[date, offensive_assets].dropna().sort_values(ascending=False)
        defensive_ranked = score.loc[date, defensive_assets].dropna().sort_values(ascending=False)

        if scale_top_n_with_cash_fraction:
            n_offensive = int(round((1.0 - cash_fraction) * top_n_offensive))
        else:
            n_offensive = top_n_offensive
        chosen_offensive = list(offensive_ranked.index[:n_offensive])
        chosen_defensive = list(defensive_ranked.index[:top_n_defensive])

        unallocated = 0.0

        offensive_share = 1.0 - cash_fraction
        if offensive_share > 0.0:
            if chosen_offensive:
                per_asset = offensive_share / len(chosen_offensive)
                for ticker in chosen_offensive:
                    out.loc[date, ticker] = per_asset
            else:
                unallocated += offensive_share

        if cash_fraction > 0.0:
            if chosen_defensive:
                per_asset = cash_fraction / len(chosen_defensive)
                for ticker in chosen_defensive:
                    out.loc[date, ticker] = per_asset
            else:
                unallocated += cash_fraction

        if unallocated > 0.0:
            out.loc[date, "_CASH"] = unallocated

    return out
