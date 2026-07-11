"""
COMBINER - registry.

Inna warstwa niz `engine_v2/blocks/` (te sa WEWNATRZ jednej strategii). COMBINER laczy
TargetWeights-ksztaltne tabele z KILKU niezaleznie policzonych strategii w jedna Combined
TargetWeights - kazda strategia liczy je JUZ PO WLASNYM, PELNYM solo pipeline (WLACZNIE z
wlasnym EXECUTION/HYSTERESIS), wiec to co tu wchodzi to JUZ WYKONANE wagi, nie surowy target
sprzed histerezy (patrz `engine_v2/combined_pipeline.py`).

Implementacje zyja jako osobne pliki w tym folderze, kazda rejestrujaca sie w REGISTRY pod
stringiem uzywanym w CombinedSpec.combiner.
"""

from engine_v2.registry import make_registry

REGISTRY = make_registry()

from engine_v2.combiner import fixed_capital_weights  # noqa: E402,F401  (rejestruje "fixed_capital_weights")
from engine_v2.combiner import dynamic_capital_weights  # noqa: E402,F401  (rejestruje "dynamic_capital_weights")
from engine_v2.combiner import momentum_hedge_overlay  # noqa: E402,F401  (rejestruje "momentum_hedge_overlay")
from engine_v2.combiner import relative_strength_capital_weights  # noqa: E402,F401  (rejestruje "relative_strength_capital_weights")
