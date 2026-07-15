"""
COMBINED SPEC - opis polaczenia kilku strategii w jeden portfel.

Warstwa WYZEJ niz StrategySpec (jedna strategia, wewnetrzne bloki): CombinedSpec opisuje kilka
niezaleznie zaprojektowanych strategii i sposob polaczenia ich JUZ WYKONANYCH (po wlasnym
EXECUTION/HYSTERESIS kazdej strategii) wag wg COMBINERA (patrz combined_pipeline.py). Kazda
strategia niesie WLASNY execution w swoim StrategySpec - CombinedSpec go juz nie potrzebuje
(inaczej niz we wczesniejszej wersji, gdzie bylo jedno, wspolne execution na polaczonym koncie).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class CombinedSpec:
    name: str
    hypothesis: str

    # sciezki do plikow strategy_spec.json (wzgledem katalogu, z ktorego CombinedSpec jest ladowany)
    strategy_spec_paths: List[str] = field(default_factory=list)

    combiner: str = ""
    combiner_params: Dict[str, Any] = field(default_factory=dict)

    # Opcjonalny blok "reporting" (2026-07-15, patrz engine_v2/blocks/reporting/) - w odroznieniu
    # od StrategySpec (blocks["reporting"]/base_params["reporting"]), CombinedSpec nie ma
    # koncepcji "blocks"/"base_params" wcale - to para plaskich pol, ten sam wzorzec co
    # combiner/combiner_params. Wywolywany przez combined_pipeline.run_combined_pipeline_with_reporting(),
    # nie run_combined_pipeline() - strategia bez tego pola dziala identycznie jak dotad.
    reporting: Optional[str] = None
    reporting_params: Dict[str, Any] = field(default_factory=dict)

    created_at: Optional[str] = None

    def validate(self) -> List[str]:
        problems: List[str] = []

        if not self.name:
            problems.append("Brak name.")
        if not self.hypothesis:
            problems.append("Brak hypothesis.")
        if len(self.strategy_spec_paths) < 2:
            problems.append("CombinedSpec wymaga co najmniej 2 strategy_spec_paths.")
        if not self.combiner:
            problems.append("Brak combiner (nazwa implementacji w engine_v2.combiner).")

        return problems

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CombinedSpec":
        return cls(**data)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: Path) -> "CombinedSpec":
        with path.open("r", encoding="utf-8-sig") as f:
            return cls.from_dict(json.load(f))
