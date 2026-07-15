"""
CONFIG / STRATEGY SPEC - szkielet.

Deklaratywny opis JEDNEJ strategii: co testujemy i dlaczego, zapisane ZANIM zobaczymy jakikolwiek
wynik (pre-rejestracja). Żadnej logiki liczącej tu nie ma - tylko kształt danych, który reszta
silnika (bloki pipeline'u) będzie wypełniać i konsumować.

Blok strategii = jeden z wymiennych etapów pipeline'u (patrz plan): indicators, asset_filters,
asset_scoring, selector, alpha_weighting, portfolio_risk_engine, overlays, execution. Każdy blok
w StrategySpec to nazwa implementacji (klucz w przyszłym registry) + jej parametry.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

STRATEGY_BLOCKS = [
    "data_loader",
    "data_cleaner",
    "indicators",
    "asset_filters",
    "asset_scoring",
    "selector",
    "alpha_weighting",
    "portfolio_risk_engine",
    "overlays",
    "execution",
    # "reporting" (2026-07-15) - JEDYNY OPCJONALNY blok: dziala PO calym pipeline (dostaje gotowy
    # final_portfolio+equity_curve, nie per-okres jak reszta), wiec NIE jest w
    # pipeline.PIPELINE_ORDER/REQUIRED_SINGLE_CHOICE_BLOCKS - strategia bez niego dziala identycznie
    # jak dotad. Wywolywany przez pipeline.run_strategy_pipeline_with_reporting(), nie
    # run_strategy_pipeline(). Patrz engine_v2/blocks/reporting/.
    "reporting",
]

# Bloki "wielo-instancyjne": w base_params trzymaja slownik NAZWANYCH INSTANCJI (kazda z
# wlasnym "impl" + parametrami), nie jedna implementacje z "blocks". Powod: strategia zwykle
# potrzebuje kilku wskaznikow/filtrow naraz (np. SMA200 + momentum 3/6/12; trend-filter +
# momentum-dodatni), a nie jednego wyboru jak reszta blokow.
MULTI_INSTANCE_BLOCKS = {"indicators", "asset_filters"}


@dataclass
class StrategySpec:
    name: str
    hypothesis: str
    universe: List[str]

    # blocks[nazwa_bloku] = nazwa implementacji z registry, np. {"asset_filters": "sma_trend"}
    blocks: Dict[str, str] = field(default_factory=dict)

    # base_params[nazwa_bloku] = wybrane wartości parametrów tej implementacji
    base_params: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # allowed_param_families[nazwa_bloku][nazwa_parametru] = lista dozwolonych wartości
    # do testu rodziny/sensitivity (kolejna faza, nie teraz)
    allowed_param_families: Dict[str, Dict[str, List[Any]]] = field(default_factory=dict)

    created_at: Optional[str] = None

    def validate(self) -> List[str]:
        """Zwraca listę problemów (pusta = OK). Nie rzuca wyjątków - narzędzie do sprawdzenia,
        nie twardy gate wewnątrz konstruktora."""
        problems: List[str] = []

        if not self.name:
            problems.append("Brak name.")
        if not self.hypothesis:
            problems.append("Brak hypothesis - strategia musi mieć zapisany powód, nie tylko parametry.")
        if not self.universe:
            problems.append("Pusty universe.")

        unknown_blocks = sorted(set(self.blocks) - set(STRATEGY_BLOCKS))
        if unknown_blocks:
            problems.append(f"Nieznane bloki w 'blocks': {unknown_blocks}. Znane: {STRATEGY_BLOCKS}")

        for block_name in self.base_params:
            if block_name in MULTI_INSTANCE_BLOCKS:
                continue
            if block_name not in self.blocks:
                problems.append(f"base_params ma '{block_name}', ale nie ma go w blocks.")

        for block_name in self.allowed_param_families:
            if block_name in MULTI_INSTANCE_BLOCKS:
                continue
            if block_name not in self.blocks:
                problems.append(f"allowed_param_families ma '{block_name}', ale nie ma go w blocks.")

        return problems

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StrategySpec":
        return cls(**data)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: Path) -> "StrategySpec":
        with path.open("r", encoding="utf-8-sig") as f:
            return cls.from_dict(json.load(f))
