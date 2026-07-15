"""
REPORTING - registry.

Nowy typ bloku (2026-07-15, user: "Nowy blok ma byc i powinien isc na koncu [...] musi to byc
wbudowane w silnik tak zebym mogl miec inne implementacje") - dziala PO calym pipeline (dostaje
juz GOTOWY, cala-historie `final_portfolio` + dzienna `equity_curve`), nie per-okres jak reszta
blokow. Dlatego jest OPCJONALNY: NIE jest czescia `PIPELINE_ORDER`/`REQUIRED_SINGLE_CHOICE_BLOCKS`
w `pipeline.py` (strategia bez `blocks["reporting"]` dziala DOKLADNIE jak dotad - zero zmian dla
istniejacych ~50 strategii), wywolywany osobno przez `run_strategy_pipeline_with_reporting()`.

Kontrakt: (final_portfolio: pd.DataFrame, equity_curve: pd.DataFrame, params: dict) -> None
(efekt uboczny - zapis pliku; w odroznieniu od reszty blokow, ktore zwracaja dane do dalszych
etapow pipeline'u, "reporting" jest ZAWSZE ostatnim etapem, nic po nim nie konsumuje wyniku).

Implementacje zyja jako osobne pliki w tym folderze, kazda rejestrujaca sie w REGISTRY pod
stringiem uzywanym w StrategySpec.blocks["reporting"].
"""

from engine_v2.registry import make_registry

REGISTRY = make_registry()

from engine_v2.blocks.reporting import monthly_csv_export  # noqa: E402,F401  (rejestruje "monthly_csv_export")
