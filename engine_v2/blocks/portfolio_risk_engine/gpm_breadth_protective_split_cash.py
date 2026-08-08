"""
PORTFOLIO RISK ENGINE - implementacja "gpm_breadth_protective_split_cash".

Eksperyment odpornosci (2026-07-16, user: "Czy gpm moze byc w cash?" -> "A moze test wersji gpm
ktora chroni sie w cash") - CELOWO OSOBNA implementacja, nie nowy parametr w
`gpm_breadth_protective_split.py` (user: "Nie lepiej zrob osobna strategie") - zero ryzyka dla
`gpm`/`gpm_mid_10`/`gpm_mid_13`/`gpm_lite_7`/`gpm_best17_a` i innych juz istniejacych strategii,
ktore uzywaja oryginalnego blocku bez zadnych zmian.

Identyczny mechanizm skalowania udzialu ochronnego wedlug szerokosci rynku co
`gpm_breadth_protective_split` (patrz jej docstring dla pelnego wyjasnienia wzoru), z JEDNA
roznica: udzial ochronny idzie WPROST w "_CASH", NIGDY w `protective_assets` (ich score jest
tu calkowicie ignorowany - `protective_assets` nie jest nawet wymagany). Test: czy realna
przewaga `gpm` nad prostym "uciekaj do cashu, gdy szerokosc rynku slaba" pochodzi z faktycznego
trzymania obligacji ochronnych (dochod z odsetek + ewentualne "flight to quality" rally w trakcie
wyprzedazy akcji), czy wylacznie z samego mechanizmu skalowania udzialu.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu) ani z
`gpm_breadth_protective_split.py` (swiadoma duplikacja logiki liczenia `n`/`protective_share`,
zeby ta implementacja byla w pelni niezalezna i nie ryzykowala przypadkowej zmiany zachowania
oryginalnego blocku przy jakiejkolwiek przyszlej modyfikacji tego pliku).

Kontrakt: (target_weights, market_data, indicator_set, score, params) -> TargetWeights.

params:
    risky_assets (list[str], wymagane)                             - aktywa ryzykowne (licznik szerokosci)
    top_n_risky (int, opcjonalnie, domyslnie 3)                     - ile aktywow ryzykownych trzymac naraz
    full_protective_max_n (int, opcjonalnie, domyslnie 6)           - n <= tyle => 100% ochrony (cash)
    protective_scale_denominator (float, opcjonalnie, domyslnie 6)  - mianownik skalowania powyzej progu
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.portfolio_risk_engine import REGISTRY
from engine_v2.registry import register
from engine_v2.types import IndicatorSet, MarketData, ScoreMatrix, TargetWeights


@register(REGISTRY, "gpm_breadth_protective_split_cash")
def gpm_breadth_protective_split_cash(
    target_weights: TargetWeights,
    market_data: MarketData,
    indicator_set: IndicatorSet,
    score: ScoreMatrix,
    params: Dict[str, Any],
) -> TargetWeights:
    risky_assets = params.get("risky_assets")
    top_n_risky = int(params.get("top_n_risky", 3))
    full_protective_max_n = int(params.get("full_protective_max_n", 6))
    protective_scale_denominator = float(params.get("protective_scale_denominator", 6))

    if not risky_assets:
        raise ValueError("gpm_breadth_protective_split_cash wymaga params['risky_assets'].")

    missing = sorted(set(risky_assets) - set(score.columns))
    if missing:
        raise ValueError(f"gpm_breadth_protective_split_cash: brak tickerow {missing} w score.")

    out = pd.DataFrame(0.0, index=target_weights.index, columns=target_weights.columns)

    for date in target_weights.index:
        risky_scores = score.loc[date, risky_assets]
        n = int((risky_scores > 0).sum())

        if n <= full_protective_max_n:
            protective_share = 1.0
        else:
            protective_share = (len(risky_assets) - n) / protective_scale_denominator
            protective_share = max(0.0, min(1.0, protective_share))

        risky_ranked = risky_scores.dropna().sort_values(ascending=False)
        chosen_risky = list(risky_ranked.index[:top_n_risky])

        if protective_share > 0.0:
            out.loc[date, "_CASH"] += protective_share

        risky_share = 1.0 - protective_share
        if risky_share > 0.0:
            if chosen_risky:
                per_asset = risky_share / len(chosen_risky)
                for ticker in chosen_risky:
                    out.loc[date, ticker] = per_asset
            else:
                out.loc[date, "_CASH"] += risky_share

    return out
