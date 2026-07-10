"""
PORTFOLIO_RISK_ENGINE - registry.

Implementacje tego bloku zyja jako osobne pliki w tym folderze, kazda rejestrujaca sie w
REGISTRY pod stringiem uzywanym w StrategySpec.blocks["portfolio_risk_engine"]. Orchestrator (pipeline.py)
woła REGISTRY[nazwa](dane, params) - nie importuje zadnej implementacji bezposrednio.

Dziala na JUZ ZBUDOWANYM portfelu (wyjscie ALPHA WEIGHTING), ale ma dostep do calego
market_data/indicator_set/score - moze wiec zrobic cokolwiek: od prostego przesuniecia wagi w
strone "_CASH" (np. "none"), po CALKOWITE zastapienie skladu portfela wlasna logika (np.
"vaa_canary" - kanarkowy sygnal decydujacy risk-on/risk-off miedzy dwoma calkiem roznymi
zestawami aktywow). Zaden formalny kontrakt nie ogranicza, JAK bardzo implementacja moze
zmienic target_weights - to jest swiadomie najbardziej elastyczny blok w silniku.
"""

from engine_v2.registry import make_registry

REGISTRY = make_registry()

from engine_v2.blocks.portfolio_risk_engine import none  # noqa: E402,F401  (rejestruje "none")
from engine_v2.blocks.portfolio_risk_engine import vaa_canary  # noqa: E402,F401  (rejestruje "vaa_canary")
from engine_v2.blocks.portfolio_risk_engine import gem_dual_momentum_switch  # noqa: E402,F401  (rejestruje "gem_dual_momentum_switch")
from engine_v2.blocks.portfolio_risk_engine import rebound_starter  # noqa: E402,F401  (rejestruje "rebound_starter")
