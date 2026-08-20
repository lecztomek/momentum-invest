"""
FSCORE BACKTEST - silnik koncepcji v7 (Piotroski F-Score na spolkach o wysokim B/M).

SPEC (user): raz w roku top 20% po Book-to-Market -> z nich tylko F-Score 8-9 -> equal weight ->
holding 12 miesiecy -> dane z roku `t` uzywane od 1.07.t+1.

Silnik jest CELOWO najprostszy w calym module i nie dziedziczy nic po v4-v6: nie ma histerezy,
progu percentyla, trailing stopu ani podmian w trakcie roku. Cykl zycia pozycji to DOKLADNIE jeden
rok - 1 lipca sprzedajemy wszystko i skladamy portfel od zera. Kazdy dodatkowy mechanizm bylby
odejsciem od odtwarzanego badania.

DOPRECYZOWANIA SPEC:

1. **Gdy zadna spolka nie przejdzie bramki, portfel siedzi w GOTOWCE** (zwrot 0% za ten rok). To
   jedyna uczciwa interpretacja: strategia mowi "kupuj F-Score 8-9 z taniej polowy rynku", a nie
   "kup cokolwiek". Wynik raportuje `time_in_market`, bo przy malym uniwersum to jest kluczowa
   liczba - patrz README (na 41 spolkach bramka przepuszcza cos w 4 z 22 lat).
2. **Holding = do nastepnej daty rocznej**, a nie sztywne 365 dni. Daty decyzyjne to pierwsza sesja
   od 1 lipca, wiec odstep to 12 miesiecy +/- kilka dni sesyjnych.
3. **Spolka, ktora wypadla z uniwersum PIT w trakcie roku, NIE jest sprzedawana** - portfel jest
   przebudowywany wylacznie w dacie rocznej (spojne z v2-v6, gdzie zanik plynnosci tez nie wymusza
   sprzedazy).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from value_engine.fscore import (
    DEFAULT_MIN_LAG_MONTHS,
    FScore,
    book_to_market,
    compute_fscore,
    top_book_to_market,
)
from value_engine.fundamentals import FundamentalPanel
from value_engine.market_cap import SharesEstimator


@dataclass
class FScoreConfig:
    tickers: List[str]
    book_to_market_fraction: float = 0.20  # spec: "20% spolek z najwyzszym B/M"
    min_fscore: int = 8  # spec: "kupujemy tylko F-Score 8-9"
    require_all_signals: bool = True  # bramka, nie ranking - patrz decyzja 4 w `fscore.py`
    max_positions: Optional[int] = None
    cost_bps: float = 40.0
    min_lag_months: int = DEFAULT_MIN_LAG_MONTHS


@dataclass
class Trade:
    ticker: str
    entry_date: pd.Timestamp
    entry_price: float
    exit_date: pd.Timestamp
    exit_price: float
    gross_return: float
    holding_days: int
    fscore: int
    book_to_market: float


@dataclass
class YearDecision:
    date: pd.Timestamp
    universe_size: int
    book_to_market_ranked: int
    candidates: List[str] = field(default_factory=list)  # top X% po B/M
    selected: List[str] = field(default_factory=list)  # z nich F-Score >= progu
    scores: Dict[str, int] = field(default_factory=dict)
    in_market: bool = False


def run_fscore_backtest(
    daily_prices: pd.DataFrame,
    annual_panel: FundamentalPanel,
    estimator: SharesEstimator,
    decision_dates: Sequence[pd.Timestamp],
    config: FScoreConfig,
    ticker_to_fundamental_key: Optional[Dict[str, str]] = None,
    eligible_universe: Optional[Dict[pd.Timestamp, List[str]]] = None,
) -> Dict[str, Any]:
    if not 0.0 < config.book_to_market_fraction <= 1.0:
        raise ValueError(
            f"book_to_market_fraction musi byc w (0, 1], dostalem {config.book_to_market_fraction}."
        )
    if not 0 <= config.min_fscore <= 9:
        raise ValueError(f"min_fscore musi byc w [0, 9], dostalem {config.min_fscore}.")

    key_of = ticker_to_fundamental_key or {t: t.upper() for t in config.tickers}
    prices = daily_prices[config.tickers].sort_index()
    priced = prices.ffill()
    cost_rate = config.cost_bps / 10000.0

    cash = 1.0
    holdings: Dict[str, Dict[str, Any]] = {}
    trades: List[Trade] = []
    decisions: List[YearDecision] = []
    equity_records: List[tuple] = []
    decision_set = set(decision_dates)
    first_decision_date: Optional[pd.Timestamp] = None

    for date in prices.index:
        row = priced.loc[date]

        if date in decision_set:
            # --- 1) SPRZEDAJ WSZYSTKO (holding = dokladnie jeden rok) ---
            for ticker, holding in list(holdings.items()):
                price = row.get(ticker)
                if pd.isna(price):
                    continue
                price = float(price)
                cash += holding["shares"] * price * (1.0 - cost_rate)
                trades.append(
                    Trade(
                        ticker=ticker,
                        entry_date=holding["entry_date"],
                        entry_price=holding["entry_price"],
                        exit_date=date,
                        exit_price=price,
                        gross_return=price / holding["entry_price"] - 1.0,
                        holding_days=(date - holding["entry_date"]).days,
                        fscore=holding["fscore"],
                        book_to_market=holding["book_to_market"],
                    )
                )
                del holdings[ticker]

            # --- 2) SELEKCJA: top X% po B/M, z nich F-Score >= progu ---
            investable = (
                list(config.tickers)
                if eligible_universe is None
                else list(eligible_universe.get(date, []))
            )
            ratios: Dict[str, float] = {}
            for ticker in investable:
                market_cap = estimator.market_cap(key_of[ticker], row.get(ticker), date)
                ratio = book_to_market(
                    annual_panel, key_of[ticker], market_cap, date, min_lag_months=config.min_lag_months
                )
                if ratio is not None:
                    ratios[ticker] = ratio

            candidates = top_book_to_market(ratios, config.book_to_market_fraction)
            scores: Dict[str, FScore] = {
                ticker: compute_fscore(
                    annual_panel, key_of[ticker], date, min_lag_months=config.min_lag_months
                )
                for ticker in candidates
            }
            selected = [
                ticker
                for ticker in candidates
                if scores[ticker].score >= config.min_fscore
                and (scores[ticker].complete or not config.require_all_signals)
            ]
            # Przy remisie na F-Score decyduje wyzszy B/M - deterministycznie, bez losowosci.
            selected.sort(key=lambda t: (-scores[t].score, -ratios[t]))
            if config.max_positions is not None:
                selected = selected[: config.max_positions]

            if ratios and first_decision_date is None:
                # Ranking B/M istnieje dopiero, gdy jest opublikowany raport roczny ORAZ
                # odtworzona kapitalizacja - dopiero od tego momentu metryki maja sens.
                first_decision_date = date

            # --- 3) KUP equal weight ---
            if selected:
                target = cash / len(selected)
                for ticker in selected:
                    price = row.get(ticker)
                    if pd.isna(price) or float(price) <= 0:
                        continue
                    price = float(price)
                    holdings[ticker] = {
                        "entry_date": date,
                        "entry_price": price,
                        "shares": (target * (1.0 - cost_rate)) / price,
                        "fscore": scores[ticker].score,
                        "book_to_market": ratios[ticker],
                    }
                    cash -= target

            decisions.append(
                YearDecision(
                    date=date,
                    universe_size=len(investable),
                    book_to_market_ranked=len(ratios),
                    candidates=sorted(candidates),
                    selected=sorted(selected),
                    scores={t: s.score for t, s in scores.items()},
                    in_market=bool(selected),
                )
            )

        position_value = sum(
            holding["shares"] * float(row[ticker])
            for ticker, holding in holdings.items()
            if pd.notna(row.get(ticker))
        )
        equity_records.append((date, cash + position_value))

    last_date = prices.index[-1]
    last_row = priced.loc[last_date]
    for ticker, holding in list(holdings.items()):
        price = last_row.get(ticker)
        if pd.isna(price):
            continue
        price = float(price)
        cash += holding["shares"] * price * (1.0 - cost_rate)
        trades.append(
            Trade(
                ticker=ticker,
                entry_date=holding["entry_date"],
                entry_price=holding["entry_price"],
                exit_date=last_date,
                exit_price=price,
                gross_return=price / holding["entry_price"] - 1.0,
                holding_days=(last_date - holding["entry_date"]).days,
                fscore=holding["fscore"],
                book_to_market=holding["book_to_market"],
            )
        )
        del holdings[ticker]

    return {
        "equity_curve": pd.DataFrame(equity_records, columns=["date", "equity"]),
        "trades": trades,
        "decisions": decisions,
        "first_decision_date": first_decision_date,
    }
