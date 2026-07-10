"""
OVERLAYS - registry.

Implementacje tego bloku zyja jako osobne pliki w tym folderze, kazda rejestrujaca sie w
REGISTRY pod stringiem uzywanym w StrategySpec.blocks["overlays"]. Orchestrator (pipeline.py)
woła REGISTRY[nazwa](dane, params) - nie importuje zadnej implementacji bezposrednio.

Blok FAZY B - dziala okres po okresie (nie na calej tabeli naraz jak Faza A). Kontrakt:
(target_weights_row: pd.Series, context: OverlayContext, params: dict) -> pd.Series - wagi
docelowe TYLKO dla biezacej daty, ewentualnie zmodyfikowane (np. rebound po duzym spadku).

Na razie tylko "none" (pass-through) - realny overlay dojdzie gdy konkretna strategia go zazada.
"""

from engine_v2.registry import make_registry

REGISTRY = make_registry()

from engine_v2.blocks.overlays import none  # noqa: E402,F401  (rejestruje "none")
