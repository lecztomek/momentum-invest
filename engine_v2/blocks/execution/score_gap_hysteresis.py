"""
EXECUTION / HYSTERESIS - implementacja "score_gap_hysteresis".

Odtwarza `should_keep_current_assets_by_hysteresis` ze starego silnika (`best17_3m`) - inaczej
niz "hysteresis" (prog na roznicy WAGI), tu prog jest na roznicy SCORE: portfel zostaje
NIEZMIENIONY, jesli NAJSLABSZY (najnizszy score) obecnie trzymany aktyw jest w odleglosci
<= min_score_gap od NAJLEPSZEGO "wyzwania" (najlepszy score wsrod aktywow docelowych, ktorych
NIE trzymamy obecnie) - inaczej rebalansuje do celu w calosci.

Jesli sklad docelowy i obecny sa identyczne (te same tickery > 0) - zawsze "keep" (brak
wyzwania). Jesli oba sa cash (brak trzymanych aktywow i brak docelowych) - tez "keep".

Wymaga `context.score_row` (biezacy wiersz SCORE - patrz types.ExecutionContext) - inaczej niz
"hysteresis", ktora potrzebuje tylko wag i zwrotow.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (target_weights_row: pd.Series, context: ExecutionContext, params: dict)
-> PeriodExecutionResult.

params:
    min_score_gap (float, wymagane)           - prog roznicy score do utrzymania portfela
    cost_bps (float, opcjonalnie, domyslnie 0) - koszt transakcyjny w punktach bazowych od turnover
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.execution import REGISTRY
from engine_v2.registry import register
from engine_v2.types import ExecutionContext, PeriodExecutionResult


@register(REGISTRY, "score_gap_hysteresis")
def score_gap_hysteresis(
    target_weights_row: pd.Series, context: ExecutionContext, params: Dict[str, Any]
) -> PeriodExecutionResult:
    if "min_score_gap" not in params:
        raise ValueError("score_gap_hysteresis wymaga params['min_score_gap'].")
    if context.score_row is None:
        raise ValueError("score_gap_hysteresis wymaga context.score_row.")

    min_gap = float(params["min_score_gap"])
    cost_bps = float(params.get("cost_bps", 0.0))
    score_row = context.score_row

    current_weights = context.state.current_weights
    current_held = sorted(t for t, w in current_weights.items() if t != "_CASH" and w > 1e-9)
    target_held = sorted(t for t in target_weights_row.index if t != "_CASH" and target_weights_row[t] > 1e-9)

    if set(current_held) == set(target_held):
        keep_current = True
    elif not current_held and not target_held:
        keep_current = True
    else:
        challengers = [t for t in target_held if t not in current_held]
        if current_held and challengers:
            weakest_current = min(
                (score_row.get(t) for t in current_held if pd.notna(score_row.get(t))), default=None
            )
            best_challenger = max(
                (score_row.get(t) for t in challengers if pd.notna(score_row.get(t))), default=None
            )
            keep_current = (
                weakest_current is not None
                and best_challenger is not None
                and (best_challenger - weakest_current) <= min_gap
            )
        else:
            keep_current = False

    all_tickers = sorted(set(target_weights_row.index) | set(current_weights))
    target = {t: float(target_weights_row.get(t, 0.0)) for t in all_tickers}
    current = {t: float(current_weights.get(t, 0.0)) for t in all_tickers}

    if keep_current:
        weights_used = current
        signal_changed = False
        turnover = 0.0
        operations = 0
        trade_cost = 0.0
    else:
        weights_used = target
        diffs = {t: target[t] - current[t] for t in all_tickers}
        turnover = sum(abs(d) for d in diffs.values()) / 2.0
        operations = sum(1 for d in diffs.values() if d != 0.0)
        signal_changed = operations > 0
        trade_cost = turnover * cost_bps / 10000.0

    returns_row = context.returns_row
    gross_return = sum(
        weight * float(returns_row.get(ticker, 0.0))
        for ticker, weight in weights_used.items()
        if ticker != "_CASH"
    )
    net_return = gross_return - trade_cost

    return PeriodExecutionResult(
        date=context.date,
        weights_used=weights_used,
        signal_changed=signal_changed,
        turnover=turnover,
        operations=operations,
        trade_cost=trade_cost,
        gross_return=gross_return,
        net_return=net_return,
        diagnostics={"kept_current": keep_current},
    )
