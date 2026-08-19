"""
SCORING - score kandydata 0-100 dla koncepcji "quality value" na GPW.

    SCORE = 0.50 * DD + 0.25 * REL + 0.25 * QUALITY

  DD      - percentyl obsuniecia od 52W high (najbardziej przeceniona ~100)
  REL     - percentyl slabosci wzgledem rynku za 6M (najbardziej odstajaca w tyl ~100)
  QUALITY - 0 / 25 / 50 / 75 / 100, po 25 pkt za kazdy spelniony warunek:
              1. Net Income TTM > 0
              2. CFO TTM > 0
              3. CFO TTM >= Net Income TTM
              4. Debt / Assets <= Debt / Assets rok wczesniej

DWIE DECYZJE PROJEKTOWE, KTORYCH SPEC NIE PRZESADZAL (podjete tak, zeby regula byla spojna):

1. **Percentyle licza sie na ZBIORZE = kandydaci Z BRAMKI + AKTUALNIE TRZYMANE pozycje.**
   Spec mowi "percentyl wsrod aktualnych kandydatow", ale regula podmiany ("nowy kandydat
   zastepuje najslabsza tylko gdy ma score wyzszy o min. 10 pkt") wymaga, zeby score pozycji
   trzymanej byl PORÓWNYWALNY ze score kandydata. Trzymana pozycja czesto NIE jest juz
   kandydatem (np. odbila powyzej -25%), wiec licząc percentyle tylko wsrod kandydatow
   dostawalibysmy dwie nieporownywalne skale i prog 10 pkt nie mialby sensu. Stad jeden wspolny
   zbior rankingowy.

2. **Percentyl = `rank(pct=True) * 100`** (pandas, remisy usredniane). Spec chcial "najmniej
   przeceniona ~0", a ta definicja daje najslabszemu `1/n * 100` (dla 10 kandydatow: 10, dla 2:
   50). Wybrana swiadomie, bo alternatywa `(rank-1)/(n-1)*100` dzieli przez zero przy jednym
   elemencie w zbiorze - co przy malym uniwersum zdarza sie realnie. UWAGA: przy 1-3 elementach
   percentyl jest z natury zgrubny (jedyny element dostaje 100), wiec DD/REL sa wtedy slabo
   rozdzielcze - to argument za wieksza liczba spolek w uniwersum, nie za zmiana definicji.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import pandas as pd

from value_engine.fundamentals import FundamentalPanel

DD_WEIGHT = 0.50
REL_WEIGHT = 0.25
QUALITY_WEIGHT = 0.25

QUALITY_CRITERIA = ("net_income_positive", "cashflow_positive", "cashflow_ge_net_income", "debt_ratio_not_rising")


@dataclass
class QualityResult:
    """Wynik QUALITY z rozbiciem na kryteria - zeby dalo sie pokazac, DLACZEGO spolka dostala
    tyle punktow (a nie tylko ile)."""

    score: float  # 0/25/50/75/100
    passed: Dict[str, bool]
    values: Dict[str, Optional[float]]

    @property
    def points(self) -> int:
        return sum(1 for value in self.passed.values() if value)


def compute_quality(
    panel: FundamentalPanel,
    ticker: str,
    as_of: pd.Timestamp,
    net_income_metric: str = "IncomeNetProfit",
    cashflow_metric: str = "CashflowOperatingCashflow",
    total_assets_metric: str = "BalanceTotalAssets",
    debt_metrics: Sequence[str] = ("BalanceCurrentBorrowings", "BalanceNoncurrentBorrowings"),
) -> QualityResult:
    """QUALITY na danych POINT-IN-TIME (`panel` zwraca tylko to, co bylo opublikowane do `as_of`).

    BRAK DANYCH = KRYTERIUM NIESPELNIONE (nie "neutralne"). Konserwatywnie: gdy nie wiemy, nie
    przyznajemy punktu - inaczej spolka bez fundamentow przechodzilaby bramke QUALITY>=50 na samym
    braku informacji.

    DLUG = oprocentowane zadluzenie (`Borrowings` biezace + dlugoterminowe), CELOWO BEZ LEASINGU.
    Leasing wszedl do bilansow z IFRS 16 (~2019) - wliczenie go daje sztuczny SKOK zadluzenia u
    kazdej spolki w roku przejscia, co falszywie zapalaloby kryterium "dlug rosnie" dla calego
    rynku naraz. Widac to w danych: `BalanceRightToUseAssets` ma wartosci tylko w 28 z 41
    kwartalow DNP."""
    net_income_ttm = panel.ttm(ticker, net_income_metric, as_of)
    cashflow_ttm = panel.ttm(ticker, cashflow_metric, as_of)

    debt_now = _sum_metrics(panel, ticker, debt_metrics, as_of, shift=0)
    debt_before = _sum_metrics(panel, ticker, debt_metrics, as_of, shift=4)
    assets_now = panel.latest(ticker, total_assets_metric, as_of)
    assets_before = panel.value_shifted(ticker, total_assets_metric, as_of, shift=4)

    debt_ratio_now = debt_now / assets_now if debt_now is not None and assets_now not in (None, 0) else None
    debt_ratio_before = (
        debt_before / assets_before if debt_before is not None and assets_before not in (None, 0) else None
    )

    passed = {
        "net_income_positive": net_income_ttm is not None and net_income_ttm > 0,
        "cashflow_positive": cashflow_ttm is not None and cashflow_ttm > 0,
        "cashflow_ge_net_income": (
            cashflow_ttm is not None and net_income_ttm is not None and cashflow_ttm >= net_income_ttm
        ),
        "debt_ratio_not_rising": (
            debt_ratio_now is not None and debt_ratio_before is not None and debt_ratio_now <= debt_ratio_before
        ),
    }
    values = {
        "net_income_ttm": net_income_ttm,
        "cashflow_ttm": cashflow_ttm,
        "debt_ratio_now": debt_ratio_now,
        "debt_ratio_year_ago": debt_ratio_before,
    }

    return QualityResult(score=sum(passed.values()) / len(QUALITY_CRITERIA) * 100.0, passed=passed, values=values)


def _sum_metrics(
    panel: FundamentalPanel, ticker: str, metrics: Sequence[str], as_of: pd.Timestamp, shift: int
) -> Optional[float]:
    """Suma kilku pozycji bilansowych. Jesli ZADNA nie jest dostepna -> None (nie wiemy). Jesli
    dostepna jest chociaz jedna, brakujace traktujemy jak 0 - typowe dla bilansow, gdzie spolka
    bez np. zadluzenia dlugoterminowego po prostu nie ma tej linii."""
    values = []
    for metric in metrics:
        value = (
            panel.latest(ticker, metric, as_of) if shift == 0 else panel.value_shifted(ticker, metric, as_of, shift)
        )
        if value is not None:
            values.append(value)
    return sum(values) if values else None


def percentile_scores(values: Dict[str, float], higher_is_better: bool = True) -> Dict[str, float]:
    """Percentyl 0-100 w obrebie podanego zbioru. `higher_is_better=True` znaczy, ze WIEKSZA
    wartosc wejsciowa ma dostac WIEKSZY score."""
    if not values:
        return {}
    series = pd.Series(values, dtype="float64")
    ranked = series.rank(pct=True, ascending=higher_is_better)
    return {ticker: float(score) * 100.0 for ticker, score in ranked.items()}


def drawdown_from_high(price: float, rolling_high: float) -> Optional[float]:
    """Obsuniecie jako liczba DODATNIA (0.25 = 25% ponizej szczytu) - zgodnie z jezykiem spec
    ("drawdown >= 25%"), inaczej niz `signals.drawdown_from_rolling_high`, ktore zwraca ujemne."""
    if rolling_high in (None, 0) or price is None or pd.isna(price) or pd.isna(rolling_high):
        return None
    return 1.0 - price / rolling_high


def composite_score(dd_score: float, rel_score: float, quality_score: float) -> float:
    return DD_WEIGHT * dd_score + REL_WEIGHT * rel_score + QUALITY_WEIGHT * quality_score


@dataclass
class ScoredTicker:
    ticker: str
    score: float
    dd_score: float
    rel_score: float
    quality_score: float
    drawdown: float
    relative_weakness: float
    quality: QualityResult
    passes_entry_gate: bool


def score_universe(
    tickers: Sequence[str],
    drawdowns: Dict[str, float],
    relative_weakness: Dict[str, float],
    qualities: Dict[str, QualityResult],
    min_drawdown: float = 0.25,
    min_quality: float = 50.0,
) -> List[ScoredTicker]:
    """Liczy SCORE dla podanego zbioru tickerow (patrz decyzja projektowa nr 1 w docstringu
    modulu - zbior to kandydaci Z BRAMKI + aktualnie trzymane pozycje, zeby prog 10 pkt przy
    podmianie mial sens).

    `passes_entry_gate` mowi, czy dana spolka moze byc KUPIONA (drawdown >= progu I QUALITY >=
    progu). Pozycje juz trzymane sa scorowane niezaleznie od bramki - bramka dotyczy wejscia, nie
    utrzymania."""
    usable = [
        t
        for t in tickers
        if drawdowns.get(t) is not None and relative_weakness.get(t) is not None and t in qualities
    ]
    dd_scores = percentile_scores({t: drawdowns[t] for t in usable})
    rel_scores = percentile_scores({t: relative_weakness[t] for t in usable})

    scored = []
    for ticker in usable:
        quality = qualities[ticker]
        scored.append(
            ScoredTicker(
                ticker=ticker,
                score=composite_score(dd_scores[ticker], rel_scores[ticker], quality.score),
                dd_score=dd_scores[ticker],
                rel_score=rel_scores[ticker],
                quality_score=quality.score,
                drawdown=drawdowns[ticker],
                relative_weakness=relative_weakness[ticker],
                quality=quality,
                passes_entry_gate=drawdowns[ticker] >= min_drawdown and quality.score >= min_quality,
            )
        )

    scored.sort(key=lambda s: s.score, reverse=True)
    return scored
