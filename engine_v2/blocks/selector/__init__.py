"""
SELECTOR - registry.

Implementacje tego bloku zyja jako osobne pliki w tym folderze, kazda rejestrujaca sie w
REGISTRY pod stringiem uzywanym w StrategySpec.blocks["selector"]. Orchestrator (pipeline.py)
woła REGISTRY[nazwa](dane, params) - nie importuje zadnej implementacji bezposrednio.

"""

from engine_v2.registry import make_registry

REGISTRY = make_registry()

from engine_v2.blocks.selector import top_n  # noqa: E402,F401  (rejestruje "top_n")
