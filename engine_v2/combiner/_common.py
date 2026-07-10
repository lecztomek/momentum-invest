"""
COMBINER - wspolne helpery dla implementacji w tym folderze.
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd

from engine_v2.types import TargetWeights


def reindex_to_common_shape(
    strategy_target_weights: Dict[str, TargetWeights], all_index: pd.Index, all_columns: List[str]
) -> Dict[str, pd.DataFrame]:
    """Dopasowuje kazda strategie do wspolnego ksztaltu (unia kolumn/dat innych strategii):
    brakujace TICKERY (kolumny) = 0 (strategia po prostu w nie nie inwestuje), brakujace DATY
    (spoza wlasnego zakresu danej strategii, np. inne okno rozgrzewki) = PELNY cash, nie zera na
    calej linii (inaczej brakujaca strategia znikalaby z wagi kapitalu zamiast bezpiecznie
    siedziec w gotowce)."""
    out: Dict[str, pd.DataFrame] = {}
    for name, tw in strategy_target_weights.items():
        tw_full = tw.reindex(columns=all_columns, fill_value=0.0)
        missing_dates = pd.Index(all_index).difference(tw_full.index)
        if len(missing_dates) > 0:
            filler = pd.DataFrame(0.0, index=missing_dates, columns=all_columns)
            filler["_CASH"] = 1.0
            tw_full = pd.concat([tw_full, filler]).sort_index()
        out[name] = tw_full.loc[all_index]
    return out


def common_index_and_columns(strategy_target_weights: Dict[str, TargetWeights]) -> tuple:
    all_index = pd.Index(sorted(set().union(*(tw.index for tw in strategy_target_weights.values()))))
    all_columns = sorted(set().union(*(tw.columns for tw in strategy_target_weights.values())))
    if "_CASH" not in all_columns:
        all_columns.append("_CASH")
    return all_index, all_columns
