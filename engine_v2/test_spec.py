"""
TEST SPEC - szkielet.

Deklaratywny opis JAK ZAWSZE TESTUJEMY: okna train/test, walk-forward, ablation, sensitivity,
koszty, UK mapping. Ustalone raz, przed zobaczeniem wyniku - nie zmieniamy tego post-hoc, bo
wynik danej strategii wygląda gorzej/lepiej niż chcielibyśmy.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class DateWindow:
    start: str
    end: str


@dataclass
class WalkForwardSpec:
    enabled: bool = False
    window_months: Optional[int] = None
    step_months: Optional[int] = None


@dataclass
class AblationSpec:
    enabled: bool = False
    modules_to_test: List[str] = field(default_factory=list)


@dataclass
class SensitivitySpec:
    enabled: bool = False
    blocks: List[str] = field(default_factory=list)


@dataclass
class CostsSpec:
    transaction_cost_bps_one_way: float = 0.0
    annual_tax_rate: float = 0.0


@dataclass
class UkMappingSpec:
    enabled: bool = False
    ticker_mapping_file: Optional[str] = None
    uk_data_dir: str = "data/uk"
    uk_benchmark: Optional[str] = None
    run_once_at_end: bool = True
    checks: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class TestSpec:
    train_window: DateWindow
    test_window: DateWindow
    walk_forward: WalkForwardSpec = field(default_factory=WalkForwardSpec)
    ablation: AblationSpec = field(default_factory=AblationSpec)
    sensitivity: SensitivitySpec = field(default_factory=SensitivitySpec)
    costs: CostsSpec = field(default_factory=CostsSpec)
    uk_mapping: UkMappingSpec = field(default_factory=UkMappingSpec)

    def validate(self) -> List[str]:
        problems: List[str] = []

        if self.train_window.start >= self.train_window.end:
            problems.append("train_window: start musi byc przed end.")
        if self.test_window.start >= self.test_window.end:
            problems.append("test_window: start musi byc przed end.")
        if self.train_window.end >= self.test_window.start:
            problems.append(
                "train_window i test_window sie nakladaja - test_window musi byc PO train_window "
                "(inaczej to nie jest prawdziwy out-of-sample test)."
            )

        if self.walk_forward.enabled:
            if not self.walk_forward.window_months or not self.walk_forward.step_months:
                problems.append("walk_forward.enabled=true, ale brakuje window_months/step_months.")

        if self.ablation.enabled and not self.ablation.modules_to_test:
            problems.append("ablation.enabled=true, ale modules_to_test jest puste.")

        if self.sensitivity.enabled and not self.sensitivity.blocks:
            problems.append("sensitivity.enabled=true, ale blocks jest puste.")

        if self.uk_mapping.enabled and not self.uk_mapping.ticker_mapping_file:
            problems.append("uk_mapping.enabled=true, ale brakuje ticker_mapping_file.")

        return problems

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestSpec":
        d = dict(data)
        d["train_window"] = DateWindow(**d["train_window"])
        d["test_window"] = DateWindow(**d["test_window"])
        d["walk_forward"] = WalkForwardSpec(**d.get("walk_forward", {}))
        d["ablation"] = AblationSpec(**d.get("ablation", {}))
        d["sensitivity"] = SensitivitySpec(**d.get("sensitivity", {}))
        d["costs"] = CostsSpec(**d.get("costs", {}))
        d["uk_mapping"] = UkMappingSpec(**d.get("uk_mapping", {}))
        return cls(**d)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: Path) -> "TestSpec":
        with path.open("r", encoding="utf-8-sig") as f:
            return cls.from_dict(json.load(f))
