"""
DATA_LOADER - registry.

Implementacje tego bloku zyja jako osobne pliki w tym folderze, kazda rejestrujaca sie w
REGISTRY pod stringiem uzywanym w StrategySpec.blocks["data_loader"]. Orchestrator (pipeline.py)
woła REGISTRY[nazwa](dane, params) - nie importuje zadnej implementacji bezposrednio.
"""

from engine_v2.registry import make_registry

REGISTRY = make_registry()

from engine_v2.blocks.data_loader import csv_loader  # noqa: E402,F401  (import rejestruje "stooq_csv")
from engine_v2.blocks.data_loader import dividend_adjusted_csv_loader  # noqa: E402,F401  (rejestruje "stooq_csv_dividend_adjusted")
