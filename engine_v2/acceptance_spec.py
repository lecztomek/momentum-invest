"""
ACCEPTANCE SPEC - szkielet.

Deklaratywny opis CO UZNAJEMY ZA SUKCES, ustalony PRZED zobaczeniem wyniku. `global` i wpisy w
`named_periods` dziela ten sam zestaw kluczy (Criteria) - dla named period podajesz tylko te
kryteria, ktore Cie interesuja, reszta nie jest sprawdzana per-okresowo (tylko globalnie).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class Criteria:
    min_cagr: Optional[float] = None
    max_drawdown: Optional[float] = None
    min_sharpe: Optional[float] = None
    min_calmar: Optional[float] = None
    max_annual_turnover: Optional[float] = None
    max_consecutive_negative_months: Optional[int] = None
    max_time_underwater_months: Optional[int] = None
    min_pct_positive_rolling_windows: Optional[float] = None


@dataclass
class ParamStabilitySpec:
    max_relative_metric_drop_within_family: Optional[float] = None


@dataclass
class UkMappingAcceptance:
    max_weights_mismatch_months_pct: Optional[float] = None
    min_monthly_return_correlation: Optional[float] = None
    max_single_month_return_diff: Optional[float] = None
    max_cagr_gap_vs_us: Optional[float] = None
    max_drawdown_gap_vs_us: Optional[float] = None


@dataclass
class AcceptanceSpec:
    global_: Criteria = field(default_factory=Criteria)
    named_periods: Dict[str, Criteria] = field(default_factory=dict)
    param_stability: ParamStabilitySpec = field(default_factory=ParamStabilitySpec)
    uk_mapping: UkMappingAcceptance = field(default_factory=UkMappingAcceptance)

    def validate(self) -> List[str]:
        problems: List[str] = []

        if self.global_.max_drawdown is not None and self.global_.max_drawdown > 0:
            problems.append("global.max_drawdown powinien byc <= 0 (to jest drawdown, ujemna liczba).")

        for name, criteria in self.named_periods.items():
            if criteria.max_drawdown is not None and criteria.max_drawdown > 0:
                problems.append(f"named_periods.{name}.max_drawdown powinien byc <= 0.")

        u = self.uk_mapping
        if u.min_monthly_return_correlation is not None and not (-1.0 <= u.min_monthly_return_correlation <= 1.0):
            problems.append("uk_mapping.min_monthly_return_correlation musi byc w [-1, 1].")

        return problems

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["global"] = d.pop("global_")
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AcceptanceSpec":
        d = dict(data)
        global_criteria = Criteria(**d.get("global", {}))
        named_periods = {
            name: Criteria(**criteria) for name, criteria in d.get("named_periods", {}).items()
        }
        param_stability = ParamStabilitySpec(**d.get("param_stability", {}))
        uk_mapping = UkMappingAcceptance(**d.get("uk_mapping", {}))
        return cls(
            global_=global_criteria,
            named_periods=named_periods,
            param_stability=param_stability,
            uk_mapping=uk_mapping,
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: Path) -> "AcceptanceSpec":
        with path.open("r", encoding="utf-8-sig") as f:
            return cls.from_dict(json.load(f))
