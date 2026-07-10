"""
SELECTOR - implementacja "top_n".

Wybiera N tickerow o najwyzszym score w kazdym wierszu (dacie). NaN nigdy nie jest wybierany
(nieeligibilne / brak scoru z ASSET SCORING). Jesli eligibilnych tickerow jest mniej niz N,
wybiera tyle ile jest dostepnych - nie da sie wybrac wiecej niz jest eligibilnych.

Remisy rozstrzygane po kolejnosci kolumn (deterministycznie, ale arbitralnie) - method="first"
w pandas.rank.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (score: ScoreMatrix, params: dict) -> TargetSelection (bool DataFrame, ta sama
siatka co score).

params:
    top_n (int, wymagane) - ile tickerow wybrac na kazda date
"""

from __future__ import annotations

from typing import Any, Dict

from engine_v2.blocks.selector import REGISTRY
from engine_v2.registry import register
from engine_v2.types import ScoreMatrix, TargetSelection


@register(REGISTRY, "top_n")
def top_n(score: ScoreMatrix, params: Dict[str, Any]) -> TargetSelection:
    if "top_n" not in params:
        raise ValueError("top_n wymaga params['top_n'].")

    n = int(params["top_n"])
    if n < 1:
        raise ValueError(f"top_n: params['top_n'] musi byc >= 1, dostalem {n}.")

    ranks = score.rank(axis=1, ascending=False, method="first")
    return (ranks <= n) & score.notna()
