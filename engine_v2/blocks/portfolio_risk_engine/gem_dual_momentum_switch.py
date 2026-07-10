"""
PORTFOLIO RISK ENGINE - implementacja "gem_dual_momentum_switch".

Rekonstrukcja strategii "The One" (inwestujdlugoterminowo.pl) w oparciu o standardowa regule
Dual Momentum (Antonacci, GEM), na ktora strona sie powoluje - autor NIE ujawnia pelnego
algorytmu sygnalu risk-on/off, wiec to jest jawna rekonstrukcja wg publicznie znanej metodologii
GEM, nie wierne odtworzenie nieujawnionego szczegolu.

Regula (na dacie t, wg `score` = 13612W momentum - patrz asset_scoring.weighted_sum):
  1. best_on  = aktywo risk-on z najwyzszym score.
  2. best_off = aktywo risk-off z najwyzszym score.
  3. Jesli best_on.score > 0 ORAZ best_on.score > best_off.score (absolutny + wzgledny
     momentum test GEM) - w calosci w best_on (risk-on).
  4. W przeciwnym razie (risk-off): sprawdz surowy 12-miesieczny momentum (NIE 13612W) best_off
     - jesli ujemny, idz w calosci w "_CASH" (modyfikacja opisana na stronie: "mozliwosc
     pozostania w gotowce przy Risk-Off, jesli zwrot z obligacji za 12 miesiecy jest ujemny"),
     inaczej w calosci w best_off.

Brak pelnej historii scoru/momentum (NaN) - bezpiecznie pelny "_CASH".

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (target_weights, market_data, indicator_set, score, params) -> TargetWeights.

params:
    risk_on_assets (list[str], wymagane)  - kandydaci w trybie risk-on
    risk_off_assets (list[str], wymagane) - kandydaci w trybie risk-off
    mom_12_key (str, wymagane)            - klucz w indicator_set z SUROWYM 12-miesiecznym
                                             momentum (do testu cash-fallback, niezaleznie od
                                             tego jak zbudowany jest `score`)
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.portfolio_risk_engine import REGISTRY
from engine_v2.registry import register
from engine_v2.types import IndicatorSet, MarketData, ScoreMatrix, TargetWeights


@register(REGISTRY, "gem_dual_momentum_switch")
def gem_dual_momentum_switch(
    target_weights: TargetWeights,
    market_data: MarketData,
    indicator_set: IndicatorSet,
    score: ScoreMatrix,
    params: Dict[str, Any],
) -> TargetWeights:
    risk_on = params.get("risk_on_assets")
    risk_off = params.get("risk_off_assets")
    mom_12_key = params.get("mom_12_key")
    if not risk_on or not risk_off or not mom_12_key:
        raise ValueError(
            "gem_dual_momentum_switch wymaga params['risk_on_assets'], "
            "params['risk_off_assets'] i params['mom_12_key']."
        )

    missing_tickers = sorted((set(risk_on) | set(risk_off)) - set(score.columns))
    if missing_tickers:
        raise ValueError(f"gem_dual_momentum_switch: brak tickerow {missing_tickers} w score.")
    if mom_12_key not in indicator_set:
        raise ValueError(
            f"gem_dual_momentum_switch: brak wskaznika '{mom_12_key}' w indicator_set "
            f"(dostepne: {sorted(indicator_set)})."
        )

    mom_12 = indicator_set[mom_12_key]
    out = pd.DataFrame(0.0, index=target_weights.index, columns=target_weights.columns)

    for date in target_weights.index:
        on_scores = score.loc[date, risk_on]
        off_scores = score.loc[date, risk_off]

        if on_scores.isna().any() or off_scores.isna().any():
            out.loc[date, "_CASH"] = 1.0
            continue

        best_on, best_on_score = on_scores.idxmax(), on_scores.max()
        best_off, best_off_score = off_scores.idxmax(), off_scores.max()

        if best_on_score > 0 and best_on_score > best_off_score:
            out.loc[date, best_on] = 1.0
            continue

        best_off_mom_12 = mom_12.loc[date, best_off] if date in mom_12.index else None
        if best_off_mom_12 is None or pd.isna(best_off_mom_12) or best_off_mom_12 < 0:
            out.loc[date, "_CASH"] = 1.0
        else:
            out.loc[date, best_off] = 1.0

    return out
