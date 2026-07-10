"""
EXECUTION / HYSTERESIS - implementacja "hysteresis".

Decyduje, czy w ogole rebalansowac: porownuje wagi docelowe (z FAZY A, po overlayach) do
REALNIE trzymanych (context.state.current_weights). Jesli NAJWIEKSZA pojedyncza roznica na
ktoryms tickerze przekracza hysteresis_pct - rebalansuje do celu. W przeciwnym razie zostaje
przy dotychczasowych wagach (unika handlu przez szum).

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (target_weights_row: pd.Series, context: ExecutionContext, params: dict)
-> PeriodExecutionResult.

params:
    hysteresis_pct (float, wymagane)          - prog max pojedynczej roznicy wagi do rebalansu
    cost_bps (float, opcjonalnie, domyslnie 0) - koszt transakcyjny w punktach bazowych, liczony
                                                  od turnover (tylko gdy faktycznie rebalansujemy)

Uwaga: `turnover` w wyniku to standardowa definicja (suma |roznic| / 2), mimo ze SAMA DECYZJA
o rebalansie uzywa reguly "max pojedynczej roznicy" - to dwie rozne rzeczy (prog decyzyjny
vs metryka do raportowania/kosztow).
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.execution import REGISTRY
from engine_v2.registry import register
from engine_v2.types import ExecutionContext, PeriodExecutionResult


@register(REGISTRY, "hysteresis")
def hysteresis(
    target_weights_row: pd.Series, context: ExecutionContext, params: Dict[str, Any]
) -> PeriodExecutionResult:
    if "hysteresis_pct" not in params:
        raise ValueError("hysteresis wymaga params['hysteresis_pct'].")

    hysteresis_pct = float(params["hysteresis_pct"])
    cost_bps = float(params.get("cost_bps", 0.0))

    current_weights = context.state.current_weights
    all_tickers = sorted(set(target_weights_row.index) | set(current_weights))

    target = {t: float(target_weights_row.get(t, 0.0)) for t in all_tickers}
    current = {t: float(current_weights.get(t, 0.0)) for t in all_tickers}
    diffs = {t: target[t] - current[t] for t in all_tickers}

    max_abs_diff = max((abs(d) for d in diffs.values()), default=0.0)
    signal_changed = max_abs_diff > hysteresis_pct

    if signal_changed:
        weights_used = target
        turnover = sum(abs(d) for d in diffs.values()) / 2.0
        operations = sum(1 for d in diffs.values() if d != 0.0)
        trade_cost = turnover * cost_bps / 10000.0
    else:
        weights_used = current
        turnover = 0.0
        operations = 0
        trade_cost = 0.0

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
        diagnostics={"max_abs_diff": max_abs_diff},
    )
