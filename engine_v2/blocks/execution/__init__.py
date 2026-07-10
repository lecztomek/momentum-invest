"""
EXECUTION - registry.

Implementacje tego bloku zyja jako osobne pliki w tym folderze, kazda rejestrujaca sie w
REGISTRY pod stringiem uzywanym w StrategySpec.blocks["execution"]. Orchestrator (pipeline.py)
woła REGISTRY[nazwa](dane, params) - nie importuje zadnej implementacji bezposrednio.

Blok FAZY B - dziala okres po okresie. Kontrakt: (target_weights_row: pd.Series,
context: ExecutionContext, params: dict) -> PeriodExecutionResult. Decyduje CZY w ogole
rebalansowac (np. histereza) i liczy realny wynik okresu (weights_used, turnover, zwrot).
"""

from engine_v2.registry import make_registry

REGISTRY = make_registry()

from engine_v2.blocks.execution import hysteresis  # noqa: E402,F401  (rejestruje "hysteresis")
from engine_v2.blocks.execution import score_gap_hysteresis  # noqa: E402,F401  (rejestruje "score_gap_hysteresis")
