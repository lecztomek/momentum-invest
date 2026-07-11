"""
PORTFOLIO RISK ENGINE - implementacja "gtaa_trend_bond_reroute".

Odtwarza filtr trendu GTAA AGG3/AGG6 (patrz `strategies_v2/gtaa_agg3/`, `strategies_v2/gtaa_agg6/`):
dla KAZDEGO JUZ WYBRANEGO aktywa (przez SELECTOR top_n + ALPHA_WEIGHTING rowne wagi), sprawdza
czy jego cena na koniec miesiaca jest POWYZEJ `sma_window`-miesiecznej sredniej kroczacej
(rowniez na cenach konca miesiaca). Jesli TAK - przypisana czesc kapitalu zostaje przy tym
aktywie bez zmian. Jesli NIE - TA SAMA czesc kapitalu (nie caly portfel) jest przekierowana do
`bond_fallback_asset` (np. IEF jako zamiennik VGIT, niedostepnego w naszych danych).

Inaczej niz `canary_regime_gate` (GLOBALNY gate na CALA grupe naraz, risk-on/risk-off) - tu
kazdy slot jest oceniany NIEZALEZNIE, wiec czesc portfela moze byc jednoczesnie w akcjach a
czesc w obligacjach w tym samym miesiacu (np. 2 z 3 wybranych aktywow w trendzie, jedno nie -
2/3 zostaje w akcjach, 1/3 trafia do obligacji).

Cena konca miesiaca i SMA licza sie WEWNATRZ tego bloku (nie przez osobny wskaznik w
indicator_set) - swiadoma duplikacja resamplowania, ten sam wzorzec co reszta silnika (patrz
`blocks/indicators/__init__.py`).

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (target_weights, market_data, indicator_set, score, params) -> TargetWeights.

params:
    sma_window (int, wymagane)          - dlugosc SMA w miesiacach (6 w opisie GTAA AGG3/AGG6)
    bond_fallback_asset (str, wymagane) - ticker obligacji, do ktorego trafia kapital "poza trendem"
                                           (musi byc kolumna w target_weights - np. wykluczony z
                                           normalnej selekcji przez `never_eligible`)
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.indicators._month_end_common import month_end_prices, shift_to_next_month_start
from engine_v2.blocks.portfolio_risk_engine import REGISTRY
from engine_v2.registry import register
from engine_v2.types import IndicatorSet, MarketData, ScoreMatrix, TargetWeights


@register(REGISTRY, "gtaa_trend_bond_reroute")
def gtaa_trend_bond_reroute(
    target_weights: TargetWeights,
    market_data: MarketData,
    indicator_set: IndicatorSet,
    score: ScoreMatrix,
    params: Dict[str, Any],
) -> TargetWeights:
    sma_window = params.get("sma_window")
    bond_fallback_asset = params.get("bond_fallback_asset")
    if sma_window is None or not bond_fallback_asset:
        raise ValueError(
            "gtaa_trend_bond_reroute wymaga params['sma_window'] i params['bond_fallback_asset']."
        )
    sma_window = int(sma_window)
    if bond_fallback_asset not in target_weights.columns:
        raise ValueError(
            f"gtaa_trend_bond_reroute: '{bond_fallback_asset}' nie jest kolumna target_weights "
            f"(dostepne: {sorted(target_weights.columns)})."
        )

    month_end = month_end_prices(market_data.prices)
    sma = month_end.rolling(window=sma_window, min_periods=sma_window).mean()
    trend_ok = shift_to_next_month_start(month_end > sma)

    out = target_weights.copy()
    tickers = [c for c in target_weights.columns if c not in ("_CASH", bond_fallback_asset)]

    for date in out.index:
        rerouted = 0.0
        for ticker in tickers:
            weight = out.at[date, ticker]
            if weight <= 0.0:
                continue
            ok = False
            if date in trend_ok.index and ticker in trend_ok.columns:
                value = trend_ok.at[date, ticker]
                ok = bool(value) if pd.notna(value) else False
            if not ok:
                out.at[date, ticker] = 0.0
                rerouted += weight
        if rerouted > 0.0:
            out.at[date, bond_fallback_asset] = out.at[date, bond_fallback_asset] + rerouted

    return out
