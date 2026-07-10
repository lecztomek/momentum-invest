"""
Kontrakty danych (interfejsy) miedzy blokami. Zadnej logiki tu nie ma - tylko ksztalt danych,
ktory kazdy blok musi przyjmowac/zwracac, zeby dalo sie je skladac w dowolnej kombinacji.

Wszystkie "panelowe" DataFrame'y maja wspolna konwencje: index = data (miesieczna, jak w calym
projekcie), kolumny = tickery.

Pipeline dzieli sie na dwie fazy:
  FAZA A (wektoryzowalna, liczona raz dla calej historii naraz, blok nie widzi wlasnego stanu
          z poprzedniego okresu):
    DATA LOADER -> DATA CLEANER -> INDICATORS -> ASSET FILTERS -> ASSET SCORING -> SELECTOR
    -> ALPHA WEIGHTING -> PORTFOLIO RISK ENGINE
    Wynik fazy A: TargetWeights - "co strategia CHCIALABY trzymac", per data, bez wiedzy o
    tym co realnie jest w portfelu.

  FAZA B (sekwencyjna, okres po okresie, niesie PortfolioState miedzy iteracjami):
    OVERLAYS -> EXECUTION/HYSTERESIS -> FINAL PORTFOLIO
    Overlay (np. rebound) potrzebuje wiedziec czy AKTUALNIE jestesmy w cash: to zalezy od tego,
    co sie realnie wykonalo w poprzednim okresie, nie od TargetWeights. Execution/hysteresis
    porownuje target do poprzednich REALNIE wykonanych wag, nie da sie tego zwektoryzowac.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import pandas as pd

# ---------------------------------------------------------------------------
# FAZA A - typy przepływające miedzy blokami wektoryzowalnymi
# ---------------------------------------------------------------------------


@dataclass
class MarketData:
    """Wyjscie DATA LOADER / DATA CLEANER. prices/returns: index=data, kolumny=tickery."""
    prices: pd.DataFrame
    returns: pd.DataFrame


# IndicatorSet: nazwa wskaznika -> DataFrame(index=data, kolumny=tickery), np. {"sma_200": df}
IndicatorSet = Dict[str, pd.DataFrame]

# EligibilityMask: DataFrame(bool), index=data, kolumny=tickery. True = aktywo przeszlo filtr.
EligibilityMask = pd.DataFrame

# ScoreMatrix: DataFrame(float), index=data, kolumny=tickery. Wyzej = lepiej. NaN = brak scoru.
ScoreMatrix = pd.DataFrame

# TargetSelection: DataFrame(bool), index=data, kolumny=tickery. True = wybrane przez SELECTOR.
TargetSelection = pd.DataFrame

# TargetWeights: DataFrame(float), index=data, kolumny=tickery (+ ewentualnie "_CASH").
# Suma w wierszu = 1. To jest wyjscie calej FAZY A (po ALPHA WEIGHTING i PORTFOLIO RISK ENGINE).
TargetWeights = pd.DataFrame


# ---------------------------------------------------------------------------
# FAZA B - stan niesiony miedzy okresami + wynik jednego okresu
# ---------------------------------------------------------------------------


@dataclass
class PortfolioState:
    """Stan przenoszony z okresu na okres w petli sekwencyjnej. To jest jedyne miejsce,
    gdzie 'pamiec' miedzy miesiacami w ogole istnieje."""
    current_weights: Dict[str, float] = field(default_factory=lambda: {"_CASH": 1.0})
    equity: float = 1.0
    tax_base_equity: float = 1.0
    last_target_signature: Optional[tuple] = None
    is_full_cash: bool = True


@dataclass
class PeriodExecutionResult:
    """Wynik jednego okresu (jeden przyszly wiersz w FINAL PORTFOLIO)."""
    date: pd.Timestamp
    weights_used: Dict[str, float]
    signal_changed: bool
    turnover: float
    operations: int
    trade_cost: float
    gross_return: float
    net_return: float
    tax_amount: float = 0.0
    diagnostics: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Kontekst przekazywany do blokow FAZY B (maja dostep do wiecej niz tylko wlasnego wejscia)
# ---------------------------------------------------------------------------


@dataclass
class OverlayContext:
    date: pd.Timestamp
    state: PortfolioState
    market_data: MarketData


@dataclass
class ExecutionContext:
    date: pd.Timestamp
    state: PortfolioState
    returns_row: pd.Series
