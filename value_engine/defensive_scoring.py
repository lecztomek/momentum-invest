"""
DEFENSIVE SCORING - scoring koncepcji v5 "Quality Defensive".

    FINAL = 0.50 * QUALITY + 0.50 * LOW_VOL       (kazdy komponent 0-100)

QUALITY (0-100): sredni percentyl trzech wskaznikow:
    ROE TTM          = zysk netto TTM / kapital wlasny                (wyzej = lepiej)
    ROIC TTM         = EBIT TTM * (1 - stawka podatku) / (dlug + kapital wlasny)   (wyzej = lepiej)
    Debt / MarketCap = (dlug biezacy + dlugoterminowy) / kapitalizacja (NIZEJ = lepiej)

LOW_VOL (0-100): percentyl `VOL = srednia(vol_6m, vol_12m)`, gdzie vol to odchylenie standardowe
dziennych zwrotow w oknie, anualizowane. NIZSZA zmiennosc = WYZSZY score.

DECYZJE, KTORYCH SPEC NIE PRZESADZAL:

1. **ROIC**: spec podaje tylko nazwe. Uzyty mianownik to `dlug oprocentowany + kapital wlasny`
   (invested capital), licznik to `EBIT * (1 - 0.19)` - 19% to realna stawka CIT w Polsce, wiec
   NOPAT jest przyblizeniem podrecznikowym, a nie zgadywaniem. Stawka jest parametrem
   (`tax_rate`). Dlug BEZ leasingu, tak jak wszedzie w tym module - patrz uzasadnienie IFRS 16
   w `scoring.py`.

2. **Ujemny kapital wlasny** (realny przypadek przy spolce po duzych stratach) unieważnia ROE i
   ROIC - wtedy zwracamy None dla tych metryk, a nie ujemna wartosc. Ujemny mianownik odwraca znak
   i spolka z ogromna strata wygladalaby na najbardziej rentowna w rankingu.

3. **Spolki finansowe** sa wykluczane na poziomie uniwersum, nie tutaj (user: "na poczatek
   non-financials"). Dla banku/windykatora `Debt / MarketCap` nie ma sensu, bo dlug jest jego
   surowcem, a nie obciazeniem - patrz `financial_sectors` w `run_defensive.py`.

Percentyle jak w reszcie repo: `rank(pct=True) * 100`, remisy usredniane.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import pandas as pd

from value_engine.fundamentals import FundamentalPanel
from value_engine.market_cap import SharesEstimator
from value_engine.scoring import percentile_scores

QUALITY_WEIGHT = 0.50
LOW_VOL_WEIGHT = 0.50

DEFAULT_TAX_RATE = 0.19  # CIT w Polsce
_STATEMENT_UNIT = 1000.0  # BiznesRadar podaje sprawozdania w tysiacach
TRADING_DAYS_PER_YEAR = 252

QUALITY_METRICS = ("roe", "roic", "debt_to_market_cap")
_DEBT_METRICS = ("BalanceCurrentBorrowings", "BalanceNoncurrentBorrowings")


@dataclass
class QualityInputs:
    roe: Optional[float] = None
    roic: Optional[float] = None
    debt_to_market_cap: Optional[float] = None
    market_cap: Optional[float] = None

    def available(self) -> int:
        return sum(1 for name in QUALITY_METRICS if getattr(self, name) is not None)


@dataclass
class DefensiveScore:
    ticker: str
    final: float
    quality: float
    low_vol: float
    quality_inputs: QualityInputs
    volatility: float
    vol_6m: float
    vol_12m: float
    components: Dict[str, float] = field(default_factory=dict)


def _sum_debt(panel: FundamentalPanel, ticker: str, as_of: pd.Timestamp) -> Optional[float]:
    values = [panel.latest(ticker, metric, as_of) for metric in _DEBT_METRICS]
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def compute_quality_inputs(
    panel: FundamentalPanel,
    estimator: SharesEstimator,
    ticker: str,
    price: Optional[float],
    as_of: pd.Timestamp,
    tax_rate: float = DEFAULT_TAX_RATE,
) -> QualityInputs:
    market_cap = estimator.market_cap(ticker, price, as_of)
    equity = panel.latest(ticker, "BalanceCapital", as_of)
    net_income = panel.ttm(ticker, "IncomeNetProfit", as_of)
    ebit = panel.ttm(ticker, "IncomeEBIT", as_of)
    debt = _sum_debt(panel, ticker, as_of)

    # Ujemny kapital wlasny odwracalby znak - lepiej brak wskaznika niz wskaznik mylacy (patrz
    # decyzja nr 2 w docstringu modulu).
    equity_usable = equity if equity is not None and equity > 0 else None

    roe = None if net_income is None or equity_usable is None else net_income / equity_usable

    roic = None
    if ebit is not None and equity_usable is not None:
        invested_capital = equity_usable + (debt or 0.0)
        if invested_capital > 0:
            roic = ebit * (1.0 - tax_rate) / invested_capital

    debt_to_market_cap = None
    if debt is not None and market_cap is not None and market_cap > 0:
        debt_to_market_cap = debt * _STATEMENT_UNIT / market_cap

    return QualityInputs(
        roe=roe, roic=roic, debt_to_market_cap=debt_to_market_cap, market_cap=market_cap
    )


def realized_volatility(
    prices: pd.DataFrame, date: pd.Timestamp, window_days: int
) -> Dict[str, Optional[float]]:
    """Anualizowane odchylenie standardowe dziennych zwrotow z ostatnich `window_days` sesji.

    Okno konczy sie na `date` wlacznie - dzienne ceny sa znane w dniu decyzyjnym, wiec to nie jest
    look-ahead. Wymagane PELNE okno: przy krotszej historii zwracamy None, zeby swiezo notowana
    spolka nie dostawala sztucznie niskiej zmiennosci z kilku dni."""
    index = prices.index
    position = index.get_indexer([date])[0]
    if position < window_days:
        return {ticker: None for ticker in prices.columns}

    window = prices.iloc[position - window_days : position + 1]
    returns = window.pct_change().iloc[1:]

    out: Dict[str, Optional[float]] = {}
    for ticker in prices.columns:
        series = returns[ticker].dropna()
        if len(series) < window_days // 2:
            out[ticker] = None
            continue
        deviation = float(series.std())
        # Zerowa zmiennosc = cena stala przez cale okno (zawieszenie notowan, martwy szereg), a nie
        # "najbezpieczniejsza spolka swiata". Bez tego takie papiery zajmowalyby caly portfel, bo
        # dostawalyby LOW_VOL = 100.
        out[ticker] = deviation * (TRADING_DAYS_PER_YEAR ** 0.5) if deviation > 0 else None
    return out


def score_universe(
    tickers: Sequence[str],
    quality_inputs: Dict[str, QualityInputs],
    vol_6m: Dict[str, Optional[float]],
    vol_12m: Dict[str, Optional[float]],
    min_quality_metrics: int = 2,
) -> List[DefensiveScore]:
    """Zwraca liste posortowana malejaco po `final`.

    Spolka wchodzi do rankingu tylko gdy ma OBIE zmiennosci (6M i 12M) oraz co najmniej
    `min_quality_metrics` z 3 wskaznikow Quality - inaczej jej QUALITY bylby liczony z innej
    podstawy niz u pozostalych i nieporownywalny."""
    usable = [
        ticker
        for ticker in tickers
        if vol_6m.get(ticker) is not None
        and vol_12m.get(ticker) is not None
        and ticker in quality_inputs
        and quality_inputs[ticker].available() >= min_quality_metrics
    ]
    if not usable:
        return []

    # ROE i ROIC: wyzej = lepiej. Debt/MarketCap: NIZEJ = lepiej, wiec odwracamy kierunek rankingu.
    percentiles: Dict[str, Dict[str, float]] = {}
    for metric in QUALITY_METRICS:
        present = {
            t: getattr(quality_inputs[t], metric)
            for t in usable
            if getattr(quality_inputs[t], metric) is not None
        }
        percentiles[metric] = percentile_scores(
            present, higher_is_better=metric != "debt_to_market_cap"
        )

    volatility = {t: (vol_6m[t] + vol_12m[t]) / 2.0 for t in usable}
    # NIZSZA zmiennosc = WYZSZY score
    low_vol_percentiles = percentile_scores(volatility, higher_is_better=False)

    scored: List[DefensiveScore] = []
    for ticker in usable:
        parts = {m: percentiles[m][ticker] for m in QUALITY_METRICS if ticker in percentiles[m]}
        quality_score = sum(parts.values()) / len(parts)
        low_vol_score = low_vol_percentiles[ticker]
        scored.append(
            DefensiveScore(
                ticker=ticker,
                final=QUALITY_WEIGHT * quality_score + LOW_VOL_WEIGHT * low_vol_score,
                quality=quality_score,
                low_vol=low_vol_score,
                quality_inputs=quality_inputs[ticker],
                volatility=volatility[ticker],
                vol_6m=float(vol_6m[ticker]),
                vol_12m=float(vol_12m[ticker]),
                components=parts,
            )
        )

    scored.sort(key=lambda s: s.final, reverse=True)
    return scored


def build_scorer(
    panel: FundamentalPanel,
    estimator: SharesEstimator,
    vol_6m_days: int = 126,
    vol_12m_days: int = 252,
    tax_rate: float = DEFAULT_TAX_RATE,
    min_quality_metrics: int = 2,
    ticker_to_fundamental_key: Optional[Dict[str, str]] = None,
):
    """Buduje `scorer` w formacie oczekiwanym przez `factor_backtest.run_factor_backtest` - dzieki
    temu v5 uzywa tej samej, przetestowanej mechaniki slotow i ksiegowania co v4."""

    def scorer(date: pd.Timestamp, investable: List[str], price_frame: pd.DataFrame) -> List[DefensiveScore]:
        key_of = ticker_to_fundamental_key or {t: t.upper() for t in investable}
        row = price_frame.loc[date]
        quality_inputs = {
            ticker: compute_quality_inputs(
                panel, estimator, key_of[ticker], row.get(ticker), date, tax_rate=tax_rate
            )
            for ticker in investable
        }
        vol_6m = realized_volatility(price_frame[investable], date, vol_6m_days) if investable else {}
        vol_12m = realized_volatility(price_frame[investable], date, vol_12m_days) if investable else {}
        return score_universe(
            investable, quality_inputs, vol_6m, vol_12m, min_quality_metrics=min_quality_metrics
        )

    return scorer
