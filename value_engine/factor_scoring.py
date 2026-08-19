"""
FACTOR SCORING - trzyczynnikowy score dla koncepcji v4: Value + Quality + Momentum.

    FINAL = 0.40 * VALUE + 0.30 * QUALITY + 0.30 * MOMENTUM     (kazdy komponent 0-100)

VALUE (0-100): sredni percentyl trzech wskaznikow "taniosci". Spec mowil `P/E`, `P/BV`,
`FCF/Market Cap`; zaimplementowane jako RENTOWNOSCI (odwrotnosci dwoch pierwszych):

    earnings_yield = zysk netto TTM / kapitalizacja      (odwrotnosc P/E)
    book_to_price  = kapital wlasny / kapitalizacja      (odwrotnosc P/BV)
    fcf_yield      = (CFO - CAPEX) TTM / kapitalizacja   (dokladnie jak w spec)

To ta sama tresc czynnika, ale odwrocenie usuwa dwie patologie mnoznikow: (1) przy stracie P/E jest
NIEOKRESLONE, a `earnings_yield` jest po prostu ujemny i ladnie sortuje sie na koniec rankingu;
(2) przy zysku bliskim zera P/E leci do +nieskonczonosci, wiec spolka na granicy rentownosci
wygladalaby na "najdrozsza na rynku", mimo ze jest tuz obok tej ze strata. Rentownosc jest
monotoniczna i ciagla przez zero. Kierunek jest jednolity dla wszystkich trzech: WYZEJ = taniej.

QUALITY (0-100): po 20 pkt za kazde z 5 kryteriow ze spec: zysk TTM > 0; CFO TTM > 0; CFO >= zysk
netto; ROA > 0; zadluzenie/aktywa nie rosnie r/r.
UWAGA - REDUNDANCJA W SPEC: `ROA > 0` to (przy dodatnich aktywach) DOKLADNIE to samo co
`zysk TTM > 0`, wiec te dwa kryteria zawsze zapalaja sie razem i "dodatni zysk" wazy w praktyce
40, a nie 20 pkt. Zaimplementowane doslownie jak w spec (nie zmieniam cicho regul), ale warto to
wiedziec przy czytaniu wynikow - patrz test `test_roa_criterion_is_redundant_with_positive_profit`.

MOMENTUM (0-100): percentyl zwrotu 12-1, czyli od t-252 do t-21 sesji (pomijamy ostatni miesiac).
Pominiecie ostatniego miesiaca to standard w literaturze momentum - krotkoterminowe odwrocenie
(short-term reversal) dziala przeciwnie do momentum i zaszumia sygnal.

Percentyle licza sie na tym samym zbiorze co w `scoring.py`: `rank(pct=True) * 100`, remisy
usredniane, WIEKSZA wartosc wejsciowa = WYZSZY score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import pandas as pd

from value_engine.fundamentals import FundamentalPanel
from value_engine.market_cap import SharesEstimator
from value_engine.scoring import percentile_scores

VALUE_WEIGHT = 0.40
QUALITY_WEIGHT = 0.30
MOMENTUM_WEIGHT = 0.30

QUALITY_CRITERIA = (
    "net_income_positive",
    "cashflow_positive",
    "cashflow_ge_net_income",
    "roa_positive",
    "debt_ratio_not_rising",
)
VALUE_METRICS = ("earnings_yield", "book_to_price", "fcf_yield")

# BiznesRadar podaje sprawozdania w TYSIACACH, a kapitalizacje w sztukach waluty.
_STATEMENT_UNIT = 1000.0


@dataclass
class ValueInputs:
    """Surowe rentownosci jednej spolki (None = nie da sie policzyc)."""

    earnings_yield: Optional[float] = None
    book_to_price: Optional[float] = None
    fcf_yield: Optional[float] = None
    market_cap: Optional[float] = None

    def available(self) -> int:
        return sum(1 for name in VALUE_METRICS if getattr(self, name) is not None)


@dataclass
class QualityInputs:
    score: float
    passed: Dict[str, bool] = field(default_factory=dict)
    values: Dict[str, Optional[float]] = field(default_factory=dict)


def compute_value_inputs(
    panel: FundamentalPanel,
    estimator: SharesEstimator,
    ticker: str,
    price: Optional[float],
    as_of: pd.Timestamp,
) -> ValueInputs:
    market_cap = estimator.market_cap(ticker, price, as_of)
    if market_cap is None or market_cap <= 0:
        return ValueInputs()

    net_income = panel.ttm(ticker, "IncomeNetProfit", as_of)
    equity = panel.latest(ticker, "BalanceCapital", as_of)
    cashflow = panel.ttm(ticker, "CashflowOperatingCashflow", as_of)
    capex = panel.ttm(ticker, "CashflowCapex", as_of)

    # CAPEX na BiznesRadarze bywa raportowany ze znakiem ujemnym (wyplyw) albo dodatnim (kwota
    # nakladow) - bierzemy wartosc bezwzgledna, zeby FCF = CFO - naklady niezaleznie od konwencji.
    free_cashflow = None if cashflow is None or capex is None else cashflow - abs(capex)

    return ValueInputs(
        earnings_yield=None if net_income is None else net_income * _STATEMENT_UNIT / market_cap,
        book_to_price=None if equity is None or equity <= 0 else equity * _STATEMENT_UNIT / market_cap,
        fcf_yield=None if free_cashflow is None else free_cashflow * _STATEMENT_UNIT / market_cap,
        market_cap=market_cap,
    )


def compute_quality(panel: FundamentalPanel, ticker: str, as_of: pd.Timestamp) -> QualityInputs:
    """5 kryteriow x 20 pkt. Brak danych = kryterium NIESPELNIONE (konserwatywnie - gdy nie wiemy,
    nie przyznajemy punktu)."""
    net_income = panel.ttm(ticker, "IncomeNetProfit", as_of)
    cashflow = panel.ttm(ticker, "CashflowOperatingCashflow", as_of)
    total_assets = panel.latest(ticker, "BalanceTotalAssets", as_of)
    assets_before = panel.value_shifted(ticker, "BalanceTotalAssets", as_of, shift=4)

    debt_now = _sum_debt(panel, ticker, as_of, shift=0)
    debt_before = _sum_debt(panel, ticker, as_of, shift=4)
    debt_ratio_now = debt_now / total_assets if debt_now is not None and total_assets else None
    debt_ratio_before = debt_before / assets_before if debt_before is not None and assets_before else None

    roa = net_income / total_assets if net_income is not None and total_assets else None

    passed = {
        "net_income_positive": net_income is not None and net_income > 0,
        "cashflow_positive": cashflow is not None and cashflow > 0,
        "cashflow_ge_net_income": cashflow is not None and net_income is not None and cashflow >= net_income,
        "roa_positive": roa is not None and roa > 0,
        "debt_ratio_not_rising": (
            debt_ratio_now is not None and debt_ratio_before is not None and debt_ratio_now <= debt_ratio_before
        ),
    }
    return QualityInputs(
        score=sum(passed.values()) / len(QUALITY_CRITERIA) * 100.0,
        passed=passed,
        values={
            "net_income_ttm": net_income,
            "cashflow_ttm": cashflow,
            "roa": roa,
            "debt_ratio_now": debt_ratio_now,
            "debt_ratio_year_ago": debt_ratio_before,
        },
    )


def _sum_debt(panel: FundamentalPanel, ticker: str, as_of: pd.Timestamp, shift: int) -> Optional[float]:
    """Oprocentowane zadluzenie (Borrowings biezace + dlugoterminowe), bez leasingu - patrz
    uzasadnienie IFRS 16 w `scoring.py`."""
    values = []
    for metric in ("BalanceCurrentBorrowings", "BalanceNoncurrentBorrowings"):
        value = panel.latest(ticker, metric, as_of) if shift == 0 else panel.value_shifted(ticker, metric, as_of, shift)
        if value is not None:
            values.append(value)
    return sum(values) if values else None


def momentum_12_1(prices: pd.DataFrame, date: pd.Timestamp, lookback: int = 252, skip: int = 21) -> Dict[str, Optional[float]]:
    """Zwrot 12-1: od t-`lookback` do t-`skip`. Pomijamy ostatni miesiac (short-term reversal)."""
    index = prices.index
    position = index.get_indexer([date])[0]
    if position < lookback:
        return {ticker: None for ticker in prices.columns}

    start_date, end_date = index[position - lookback], index[position - skip]
    out: Dict[str, Optional[float]] = {}
    for ticker in prices.columns:
        start_price, end_price = prices.at[start_date, ticker], prices.at[end_date, ticker]
        valid = pd.notna(start_price) and pd.notna(end_price) and start_price > 0
        out[ticker] = float(end_price / start_price - 1.0) if valid else None
    return out


@dataclass
class FactorScore:
    ticker: str
    final: float
    value: float
    quality: float
    momentum: float
    value_inputs: ValueInputs
    quality_inputs: QualityInputs
    raw_momentum: float


def score_universe(
    tickers: Sequence[str],
    value_inputs: Dict[str, ValueInputs],
    quality_inputs: Dict[str, QualityInputs],
    momentum: Dict[str, Optional[float]],
    min_value_metrics: int = 2,
) -> List[FactorScore]:
    """Zwraca liste posortowana malejaco po `final`.

    Spolka wchodzi do rankingu tylko gdy ma policzalne momentum ORAZ co najmniej
    `min_value_metrics` z 3 wskaznikow Value - inaczej jej VALUE bylby sredniа z jednej losowej
    metryki i nieporownywalny z reszta."""
    usable = [
        ticker
        for ticker in tickers
        if momentum.get(ticker) is not None
        and ticker in value_inputs
        and value_inputs[ticker].available() >= min_value_metrics
        and ticker in quality_inputs
    ]
    if not usable:
        return []

    # percentyl kazdej metryki Value osobno, potem srednia z DOSTEPNYCH - dzieki temu brak jednej
    # metryki nie wyklucza spolki i nie zanizu jej Value sztucznie do zera
    value_percentiles: Dict[str, Dict[str, float]] = {}
    for metric in VALUE_METRICS:
        present = {t: getattr(value_inputs[t], metric) for t in usable if getattr(value_inputs[t], metric) is not None}
        value_percentiles[metric] = percentile_scores(present)

    momentum_percentiles = percentile_scores({t: momentum[t] for t in usable})

    scored: List[FactorScore] = []
    for ticker in usable:
        parts = [value_percentiles[m][ticker] for m in VALUE_METRICS if ticker in value_percentiles[m]]
        value_score = sum(parts) / len(parts)
        quality_score = quality_inputs[ticker].score
        momentum_score = momentum_percentiles[ticker]
        scored.append(
            FactorScore(
                ticker=ticker,
                final=VALUE_WEIGHT * value_score + QUALITY_WEIGHT * quality_score + MOMENTUM_WEIGHT * momentum_score,
                value=value_score,
                quality=quality_score,
                momentum=momentum_score,
                value_inputs=value_inputs[ticker],
                quality_inputs=quality_inputs[ticker],
                raw_momentum=float(momentum[ticker]),
            )
        )

    scored.sort(key=lambda s: s.final, reverse=True)
    return scored
