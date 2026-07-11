"""
INDICATORS - registry.

Inaczej niz reszta blokow: strategia zwykle potrzebuje KILKU wskaznikow naraz (np. SMA200
trend-filter + momentum 3/6/12), wiec `StrategySpec.blocks["indicators"]` NIE wybiera jednej
implementacji. Zamiast tego `base_params["indicators"]` to slownik instancji:

    "indicators": {
        "sma_200": {"impl": "sma_daily", "window": 200},
        "mom_3":   {"impl": "momentum_monthly", "window": 3}
    }

Kazdy wpis: klucz = nazwa pod jaka dalsze bloki odwoluja sie do wyniku, "impl" = nazwa w tym
REGISTRY, reszta = parametry tej konkretnej implementacji. Orchestrator (pipeline.py, jeszcze
nie zaimplementowany) woła REGISTRY[impl](market_data, params) dla kazdego wpisu i sklada wyniki
w IndicatorSet (Dict[klucz, DataFrame]).

Osobne implementacje per czestotliwosc (np. "momentum_daily" vs "momentum_monthly") zamiast
jednej z parametrem "basis" - kazda implementacja jest w pelni samodzielna (sama resampluje
`market_data.prices`, jesli potrzebuje innej granulacji niz dzienna), zeby bloki byly czytelne
i niezalezne, kosztem drobnej duplikacji resamplowania miedzy plikami.
"""

from engine_v2.registry import make_registry

REGISTRY = make_registry()

from engine_v2.blocks.indicators import sma_daily  # noqa: E402,F401  (rejestruje "sma_daily")
from engine_v2.blocks.indicators import momentum_monthly  # noqa: E402,F401  (rejestruje "momentum_monthly")
from engine_v2.blocks.indicators import volatility_daily  # noqa: E402,F401  (rejestruje "volatility_daily")
from engine_v2.blocks.indicators import ema_ratio_monthly  # noqa: E402,F401  (rejestruje "ema_ratio_monthly")
from engine_v2.blocks.indicators import momentum_month_end  # noqa: E402,F401  (rejestruje "momentum_month_end")
from engine_v2.blocks.indicators import momentum_avg_month_end  # noqa: E402,F401  (rejestruje "momentum_avg_month_end")
from engine_v2.blocks.indicators import corr_to_basket_month_end  # noqa: E402,F401  (rejestruje "corr_to_basket_month_end")
