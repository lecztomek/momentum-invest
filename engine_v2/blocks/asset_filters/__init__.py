"""
ASSET_FILTERS - registry.

Tak jak INDICATORS, a inaczej niz reszta blokow: strategia moze potrzebowac kilku filtrow naraz
(np. trend-filter + momentum-dodatni), gdzie kazdy MOZE COS WYRZUCIC - laczone przez AND. Wiec
`StrategySpec.blocks["asset_filters"]` NIE wybiera jednej implementacji. Zamiast tego
`base_params["asset_filters"]` to slownik instancji:

    "asset_filters": {
        "trend": {"impl": "price_above_indicator", "indicator_key": "sma_200"}
    }

Kazdy wpis: klucz = nazwa instancji (do diagnostyki/raportowania), "impl" = nazwa w tym
REGISTRY, reszta = parametry tej implementacji (w tym opcjonalny "assets" - patrz _common.py).
Orchestrator (`pipeline._run_asset_filters`) woła REGISTRY[impl](market_data, indicator_set,
params) dla kazdego wpisu i laczy wynikowe maski przez AND w jeden EligibilityMask.
"""

from engine_v2.registry import make_registry

REGISTRY = make_registry()

from engine_v2.blocks.asset_filters import price_above_indicator  # noqa: E402,F401  (rejestruje "price_above_indicator")
from engine_v2.blocks.asset_filters import indicator_positive  # noqa: E402,F401  (rejestruje "indicator_positive")
