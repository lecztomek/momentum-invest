"""
EXECUTION / HYSTERESIS - implementacja "score_gap_hysteresis_rank_aware".

EKSPERYMENT (2026-08-08, user analizuje 2022 dla `best17_a`: "No to zle to dziala ten gap trzeba
go zmienic") - CELOWO OSOBNY blok (nie zmiana `score_gap_hysteresis.py`, z ktorego korzysta 12
innych strategii/wariantow best17 - zero ryzyka dla nich).

Znaleziony problem w oryginalnym `score_gap_hysteresis`: `keep_current` porownuje TYLKO ZBIOR
trzymanych tickerow (`set(current_held) == set(target_held)`) - jesli zbior sie NIE zmienil,
portfel jest "keep"owany z DOKLADNIE takimi samymi wagami jak poprzednio, NIEZALEZNIE od tego, czy
KOLEJNOSC/ranking wewnatrz tego zbioru sie odwrocil. Realny przyklad z 2022: `best17_a` trzymal
xlk.us (80%) + dbc.us (20%) od grudnia 2021 - od marca 2022 `dbc.us` mial WYZSZY score (ema7_16)
niz `xlk.us` (rosnaca przewaga: marzec +0.022, czerwiec +0.112), ale poniewaz OBA byly juz
"trzymane" (ten sam zbior top-2), histereza nigdy nie przeliczyla wag - `xlk.us` zostal na 80% az
do lipca, mimo ze "powinien" byc na 20% od marca. To NIE jest blad we wdrozeniu (odtwarza
`should_keep_current_assets_by_hysteresis` ze starego silnika 1:1), ale realna cecha, ktora
warto przetestowac w wariancie.

Mechanizm: identyczny jak `score_gap_hysteresis` (patrz jej docstring dla pelnego opisu progu
`min_score_gap`, `forced_exit_due_to_asset_gate`, `full_position_size`), z JEDNYM dodatkiem: gdy
`set(current_held) == set(target_held)` (zbior sie nie zmienil), DODATKOWO sprawdzamy, czy
kolejnosc wag przypisanych obecnie trzymanym aktywom nadal zgadza sie z ich biezacym rankingiem
score - jesli ktrykolwiek aktyw z NIZSZA obecnie waga ma score WYZSZY o wiecej niz `min_score_gap`
od aktywa z WYZSZA obecnie waga, wymuszamy PELNY rebalans do `target` (ktory poprawnie przypisuje
wagi wg aktualnego rankingu - `alpha_weighting` jest juz "swiadome" score, tylko `execution` go
wczesniej ignorowal w tym przypadku).

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu) ani z
`score_gap_hysteresis.py` (swiadoma duplikacja, zeby byc w pelni niezaleznym od przyszlych zmian
oryginalnego blocku).

Kontrakt: (target_weights_row: pd.Series, context: ExecutionContext, params: dict)
-> PeriodExecutionResult.

params: identyczne jak `score_gap_hysteresis` (min_score_gap [wymagane], cost_bps [opcjonalnie],
full_position_size [opcjonalnie]).
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.execution import REGISTRY
from engine_v2.registry import register
from engine_v2.types import ExecutionContext, PeriodExecutionResult


def _rank_order_violated(current_held, current_weights, score_row, min_gap: float) -> bool:
    """Czy ktorys NIZEJ wazony obecnie trzymany aktyw ma score wyzszy o wiecej niz `min_gap` od
    KTOREGOKOLWIEK WYZEJ wazonego obecnie trzymanego aktywa - odtwarza kolejnosc slotow z
    `alpha_weighting` (najwyzsza waga = najlepszy rank)."""
    held_by_weight_desc = sorted(current_held, key=lambda t: -current_weights.get(t, 0.0))
    for i, higher_weight_ticker in enumerate(held_by_weight_desc):
        higher_score = score_row.get(higher_weight_ticker)
        if pd.isna(higher_score):
            continue
        for lower_weight_ticker in held_by_weight_desc[i + 1 :]:
            lower_score = score_row.get(lower_weight_ticker)
            if pd.notna(lower_score) and (lower_score - higher_score) > min_gap:
                return True
    return False


@register(REGISTRY, "score_gap_hysteresis_rank_aware")
def score_gap_hysteresis_rank_aware(
    target_weights_row: pd.Series, context: ExecutionContext, params: Dict[str, Any]
) -> PeriodExecutionResult:
    if "min_score_gap" not in params:
        raise ValueError("score_gap_hysteresis_rank_aware wymaga params['min_score_gap'].")
    if context.score_row is None:
        raise ValueError("score_gap_hysteresis_rank_aware wymaga context.score_row.")

    min_gap = float(params["min_score_gap"])
    cost_bps = float(params.get("cost_bps", 0.0))
    full_position_size = params.get("full_position_size")
    score_row = context.score_row

    current_weights = context.state.current_weights
    current_held = sorted(t for t, w in current_weights.items() if t != "_CASH" and w > 1e-9)
    target_held = sorted(t for t in target_weights_row.index if t != "_CASH" and target_weights_row[t] > 1e-9)

    current_held_ineligible = any(pd.isna(score_row.get(t)) for t in current_held)

    if current_held_ineligible:
        keep_current = False
    elif set(current_held) == set(target_held):
        if not current_held:
            keep_current = True
        else:
            keep_current = not _rank_order_violated(current_held, current_weights, score_row, min_gap)
    elif not current_held and not target_held:
        keep_current = True
    elif full_position_size is not None and len(current_held) != int(full_position_size):
        keep_current = False
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
