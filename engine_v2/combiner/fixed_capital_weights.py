"""
COMBINER - implementacja "fixed_capital_weights".

Laczy TargetWeights z kilku strategii (kazda juz po wlasnej FAZIE A + OVERLAYS) w jeden combined
TargetWeights - wazona suma wg STALEJ alokacji kapitalu miedzy strategiami.

Strategie moga miec rozne uniwersa (kolumny) - laczone przez unie kolumn, brakujace tickery w
danej strategii traktowane jako 0 (ta strategia po prostu w nich nie inwestuje).

Strategie moga tez miec rozne zakresy dat (rozne okna rozgrzewki wskaznikow) - dla dat, ktorych
dana strategia jeszcze/juz nie ma, jej wklad to "_CASH"=1.0 (jakby jeszcze nic nie robila), NIE
zera na calej linii - inaczej suma wierszy wyszlaby ponizej 1.0 (brakujaca strategia po prostu
znikalaby z wagi kapitalu zamiast bezpiecznie siedziec w gotowce).

Poniewaz kazda strategia sama sumuje sie do 1 (wliczajac "_CASH"), a wagi kapitalu tez sumuja
sie do 1, wynik matematycznie tez sumuje sie do 1 - bez dodatkowej normalizacji.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (strategy_target_weights: Dict[str, TargetWeights], params: dict) -> TargetWeights.

params:
    capital_weights (dict[str, float], wymagane) - nazwa strategii -> udzial kapitalu (suma = 1)
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.combiner import REGISTRY
from engine_v2.registry import register
from engine_v2.types import TargetWeights


@register(REGISTRY, "fixed_capital_weights")
def fixed_capital_weights(
    strategy_target_weights: Dict[str, TargetWeights], params: Dict[str, Any]
) -> TargetWeights:
    capital_weights = params.get("capital_weights")
    if not capital_weights:
        raise ValueError(
            "fixed_capital_weights wymaga params['capital_weights'] (niepusty slownik strategia->udzial)."
        )

    missing = sorted(set(capital_weights) - set(strategy_target_weights))
    if missing:
        raise ValueError(
            f"fixed_capital_weights: brak danych dla strategii {missing} w strategy_target_weights "
            f"(dostepne: {sorted(strategy_target_weights)})."
        )

    total = sum(capital_weights.values())
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"fixed_capital_weights: capital_weights musi sumowac sie do 1.0, dostalem {total}.")

    all_index = sorted(set().union(*(tw.index for tw in strategy_target_weights.values())))
    all_columns = sorted(set().union(*(tw.columns for tw in strategy_target_weights.values())))
    if "_CASH" not in all_columns:
        all_columns.append("_CASH")

    combined = pd.DataFrame(0.0, index=all_index, columns=all_columns)
    for strategy_name, capital_weight in capital_weights.items():
        tw = strategy_target_weights[strategy_name]

        # brakujace TICKERY (kolumny) u tej strategii = 0 (po prostu w nie nie inwestuje)
        tw_full = tw.reindex(columns=all_columns, fill_value=0.0)
        # brakujace DATY (spoza jej wlasnego zakresu) = pelny cash, nie zera na calej linii
        missing_dates = pd.Index(all_index).difference(tw_full.index)
        if len(missing_dates) > 0:
            filler = pd.DataFrame(0.0, index=missing_dates, columns=all_columns)
            filler["_CASH"] = 1.0
            tw_full = pd.concat([tw_full, filler]).sort_index()

        combined = combined + tw_full.loc[all_index] * capital_weight

    return combined
