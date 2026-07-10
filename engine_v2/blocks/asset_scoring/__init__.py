"""
ASSET_SCORING - registry.

Implementacje tego bloku zyja jako osobne pliki w tym folderze, kazda rejestrujaca sie w
REGISTRY pod stringiem uzywanym w StrategySpec.blocks["asset_scoring"]. Orchestrator (pipeline.py)
woła REGISTRY[nazwa](dane, params) - nie importuje zadnej implementacji bezposrednio.

"""

from engine_v2.registry import make_registry

REGISTRY = make_registry()

from engine_v2.blocks.asset_scoring import weighted_sum  # noqa: E402,F401  (rejestruje "weighted_sum")
