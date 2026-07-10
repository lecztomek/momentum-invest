"""
COMBINER - registry.

Inna warstwa niz `engine_v2/blocks/` (te sa WEWNATRZ jednej strategii). COMBINER laczy
TargetWeights z KILKU niezaleznie policzonych strategii (kazda juz po wlasnej FAZIE A +
OVERLAYS) w jeden Combined TargetWeights - dopiero na nim uruchamia sie JEDNO, wspolne
EXECUTION/HYSTERESIS (patrz `engine_v2/combined_pipeline.py`).

Implementacje zyja jako osobne pliki w tym folderze, kazda rejestrujaca sie w REGISTRY pod
stringiem uzywanym w CombinedSpec.combiner.
"""

from engine_v2.registry import make_registry

REGISTRY = make_registry()

from engine_v2.combiner import fixed_capital_weights  # noqa: E402,F401  (rejestruje "fixed_capital_weights")
