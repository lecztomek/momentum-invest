"""
DATA_CLEANER - registry.

Implementacje tego bloku zyja jako osobne pliki w tym folderze, kazda rejestrujaca sie w
REGISTRY pod stringiem uzywanym w StrategySpec.blocks["data_cleaner"]. Orchestrator (pipeline.py)
woła REGISTRY[nazwa](dane, params) - nie importuje zadnej implementacji bezposrednio.

"""

from engine_v2.registry import make_registry

REGISTRY = make_registry()

from engine_v2.blocks.data_cleaner import trim_and_interpolate  # noqa: E402,F401  (rejestruje "trim_and_interpolate")
