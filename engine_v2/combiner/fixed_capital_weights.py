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

Kontrakt: (strategy_target_weights: Dict[str, TargetWeights], params: dict)
-> (TargetWeights, EffectiveCapitalWeights). Drugi element - DataFrame (index=data, kolumny=nazwy
strategii) z FAKTYCZNIE uzytym udzialem kapitalu KAZDEJ strategii w KAZDYM okresie - dla tego
combinera to po prostu stale `capital_weights` powtorzone w kazdym wierszu, ale kontrakt jest
wspolny z `dynamic_capital_weights` (gdzie udzial NAPRAWDE zmienia sie okres-po-okresie) - patrz
tam. `combined_pipeline.py` uzywa tego do poprawnego wazenia metryk okresu (turnover/gross_return/
trade_cost) - waga STATYCZNA z params nie wystarczy, gdy inny combiner realokuje kapital
dynamicznie.

params:
    capital_weights (dict[str, float], wymagane) - nazwa strategii -> udzial kapitalu (suma = 1)
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.combiner import REGISTRY
from engine_v2.combiner._common import common_index_and_columns, reindex_to_common_shape
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

    all_index, all_columns = common_index_and_columns(strategy_target_weights)
    full_by_name = reindex_to_common_shape(strategy_target_weights, all_index, all_columns)

    combined = pd.DataFrame(0.0, index=all_index, columns=all_columns)
    for strategy_name, capital_weight in capital_weights.items():
        combined = combined + full_by_name[strategy_name] * capital_weight

    effective_weights = pd.DataFrame(
        {name: float(weight) for name, weight in capital_weights.items()}, index=all_index
    )

    return combined, effective_weights
