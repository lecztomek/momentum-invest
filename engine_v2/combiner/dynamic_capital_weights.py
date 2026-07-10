"""
COMBINER - implementacja "dynamic_capital_weights".

Odtwarza `dynamic_combined` ze starego silnika (`engine/dynamic_combined.py`): gdy KTORAS
strategia jest w danym okresie CALKOWICIE w cash (same _CASH albo puste wagi), jej kapital NIE
marnuje sie jako bezczynna gotowka w polaczonym portfelu - zamiast tego zostaje ODDANY
strategiom, ktore SA aktualnie zainwestowane (proporcjonalnie do ich WLASNYCH `capital_weights`).
Jesli WSZYSTKIE strategie sa w cash w danym okresie - caly polaczony portfel jest w cash.

Regula starego silnika (tylko dla 2 strategii A/B, patrz `dynamic_allocation_for_states`):
    A risk, B risk  -> stale capital_weights (np. 80/20)
    A cash, B risk  -> B dostaje 100%
    A risk, B cash  -> A dostaje 100%
    A cash, B cash  -> 100% cash

Ten combiner to GENERALIZACJA na dowolna liczbe strategii: kazdy okres OSOBNO klasyfikuje kazda
strategie jako "cash" (wszystkie wagi poza _CASH ~ 0) albo "risk" (trzyma cokolwiek), po czym
RENORMALIZUJE `capital_weights` TYLKO wsrod strategii aktualnie w "risk" w tym okresie (dla N=2
daje dokladnie te same reguly co stary silnik).

To jest analogiczna idea do `alpha_weighting.rank_weights`'s `redistribute_if_short` -
nie zostawiamy martwej gotowki tam, gdzie inna czesc systemu mogla ja realnie wykorzystac.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (strategy_target_weights: Dict[str, TargetWeights], params: dict)
-> (TargetWeights, EffectiveCapitalWeights). Drugi element - DataFrame (index=data, kolumny=nazwy
strategii) z FAKTYCZNIE uzytym udzialem kapitalu KAZDEJ strategii w KAZDYM okresie (0.0 w
okresach, gdy dana strategia byla w cash) - patrz `combined_pipeline.py`, ktory tego uzywa do
poprawnego wazenia metryk okresu (turnover/gross_return/trade_cost); statyczne `capital_weights`
z params NIE wystarcza, bo tu realny udzial zmienia sie okres-po-okresie.

params:
    capital_weights (dict[str, float], wymagane) - BAZOWA alokacja kapitalu (strategia -> udzial,
        suma = 1), uzywana wprost gdy WSZYSTKIE strategie sa jednoczesnie "w risk" w danym
        okresie; w pozostalych okresach renormalizowana tylko wsrod strategii "w risk".
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.combiner import REGISTRY
from engine_v2.combiner._common import common_index_and_columns, reindex_to_common_shape
from engine_v2.registry import register
from engine_v2.types import TargetWeights


def _is_cash_row(row: pd.Series) -> bool:
    non_cash = row.drop(labels=["_CASH"], errors="ignore")
    return bool((non_cash.abs() <= 1e-9).all())


@register(REGISTRY, "dynamic_capital_weights")
def dynamic_capital_weights(
    strategy_target_weights: Dict[str, TargetWeights], params: Dict[str, Any]
) -> TargetWeights:
    capital_weights = params.get("capital_weights")
    if not capital_weights:
        raise ValueError(
            "dynamic_capital_weights wymaga params['capital_weights'] (niepusty slownik strategia->udzial)."
        )

    missing = sorted(set(capital_weights) - set(strategy_target_weights))
    if missing:
        raise ValueError(
            f"dynamic_capital_weights: brak danych dla strategii {missing} w strategy_target_weights "
            f"(dostepne: {sorted(strategy_target_weights)})."
        )

    total = sum(capital_weights.values())
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"dynamic_capital_weights: capital_weights musi sumowac sie do 1.0, dostalem {total}.")

    all_index, all_columns = common_index_and_columns(strategy_target_weights)
    full_by_name = reindex_to_common_shape(strategy_target_weights, all_index, all_columns)

    combined = pd.DataFrame(0.0, index=all_index, columns=all_columns)
    effective_weights = pd.DataFrame(0.0, index=all_index, columns=list(capital_weights))

    for date in all_index:
        risk_names = [name for name in capital_weights if not _is_cash_row(full_by_name[name].loc[date])]

        if not risk_names:
            combined.loc[date, "_CASH"] = 1.0
            continue

        risk_total = sum(capital_weights[name] for name in risk_names)
        for name in risk_names:
            effective_weight = capital_weights[name] / risk_total
            combined.loc[date] = combined.loc[date] + full_by_name[name].loc[date] * effective_weight
            effective_weights.loc[date, name] = effective_weight

    return combined, effective_weights
