"""
OVERLAYS - implementacja "none".

Pass-through: zwraca target_weights_row bez zmian. Dla strategii, ktore nie potrzebuja zadnego
overlaya (np. rebound, vol-target) ponad to co dala juz FAZA A.

Kontrakt: (target_weights_row: pd.Series, context: OverlayContext, params: dict) -> pd.Series.
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from engine_v2.blocks.overlays import REGISTRY
from engine_v2.registry import register
from engine_v2.types import OverlayContext


@register(REGISTRY, "none")
def none(target_weights_row: pd.Series, context: OverlayContext, params: Dict[str, Any]) -> pd.Series:
    return target_weights_row.copy()
