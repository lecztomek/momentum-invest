"""
RUN SPEC - szkielet.

Deklaratywny opis CO ODPALAMY TERAZ: ktora strategia, ktory test protocol, ktore kryteria, tryb.
Wskazuje na pliki STRATEGY SPEC / TEST SPEC / ACCEPTANCE SPEC (relatywnie do wlasnego folderu),
nie zawiera ich tresci - zeby jeden zestaw strategy/test/acceptance dalo sie odpalic w kilku
trybach bez duplikowania plikow.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

VALID_MODES = ["search", "validation", "final"]


@dataclass
class RunSpec:
    strategy_spec: str
    test_spec: str
    acceptance_spec: str
    mode: str
    notes: Optional[str] = None

    def validate(self) -> List[str]:
        problems: List[str] = []

        if self.mode not in VALID_MODES:
            problems.append(f"mode='{self.mode}' nieznany. Dozwolone: {VALID_MODES}")

        return problems

    def resolve_paths(self, base_dir: Path) -> Dict[str, Path]:
        """Zwraca sciezki do plikow spec wzgledem folderu, w ktorym lezy ten run_spec."""
        return {
            "strategy_spec": base_dir / self.strategy_spec,
            "test_spec": base_dir / self.test_spec,
            "acceptance_spec": base_dir / self.acceptance_spec,
        }

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunSpec":
        return cls(**data)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: Path) -> "RunSpec":
        with path.open("r", encoding="utf-8-sig") as f:
            return cls.from_dict(json.load(f))
