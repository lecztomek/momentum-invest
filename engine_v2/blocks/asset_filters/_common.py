"""
Wspolne pomocnicze dla implementacji ASSET FILTERS - NIE jest to zarejestrowana implementacja,
tylko funkcja uzywana przez pliki w tym folderze, zeby nie duplikowac tej samej logiki w kazdym
z nich.
"""

from __future__ import annotations

from typing import Any, List, Optional

import pandas as pd


def apply_asset_scope(mask: pd.DataFrame, universe: List[str], assets_param: Optional[Any]) -> pd.DataFrame:
    """Ogranicza dzialanie filtra do podzbioru uniwersum (param "assets" - lista tickerow albo
    brak/"all" = wszystkie). Tickery SPOZA zakresu dostaja automatycznie True - filtr ktory nie
    dotyczy danego aktywa nie moze go wyeliminowac (filtry laczy sie przez AND, wiec "nie
    dotyczy" musi znaczyc "przepuszczam", nie "odrzucam")."""
    if assets_param is None or assets_param == "all":
        return mask

    scoped = set(assets_param)
    unknown = scoped - set(universe)
    if unknown:
        raise ValueError(f"asset_filters: nieznane tickery w 'assets': {sorted(unknown)}")

    out = mask.copy()
    out_of_scope_cols = [c for c in mask.columns if c not in scoped]
    if out_of_scope_cols:
        out[out_of_scope_cols] = True
    return out
