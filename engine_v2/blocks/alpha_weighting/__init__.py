"""
ALPHA_WEIGHTING - registry.

Implementacje tego bloku zyja jako osobne pliki w tym folderze, kazda rejestrujaca sie w
REGISTRY pod stringiem uzywanym w StrategySpec.blocks["alpha_weighting"]. Orchestrator (pipeline.py)
woła REGISTRY[nazwa](selection, score, indicator_set, params) - nie importuje zadnej
implementacji bezposrednio. Kazda implementacja przyjmuje TEN SAM zestaw argumentow, nawet jesli
nie wszystkich uzywa (np. rank_weights ignoruje indicator_set, inverse_vol ignoruje score).
"""

from engine_v2.registry import make_registry

REGISTRY = make_registry()

from engine_v2.blocks.alpha_weighting import rank_weights  # noqa: E402,F401  (rejestruje "rank_weights")
from engine_v2.blocks.alpha_weighting import inverse_vol  # noqa: E402,F401  (rejestruje "inverse_vol")
from engine_v2.blocks.alpha_weighting import rounded_score_weights  # noqa: E402,F401  (rejestruje "rounded_score_weights")
