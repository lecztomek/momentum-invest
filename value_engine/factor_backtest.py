"""
FACTOR BACKTEST - silnik koncepcji v4: Value + Quality + Momentum, top 4 z histereza top 8.

SPEC (user, testowana DOKLADNIE ta jedna wersja, bez sweepu wag):
  - uniwersum: duze/plynne spolki GPW, point-in-time (`universe.py`)
  - rebalans raz w miesiacu
  - FINAL = 0.40*Value + 0.30*Quality + 0.30*Momentum (`factor_scoring.py`)
  - portfel: top 4 po FINAL, po 25% przy wejsciu, BEZ ciaglego wyrownywania wag
  - replacement: spolka wypada, gdy nie jest juz w top 8, a kandydat do wejscia jest w top 4
    (prosta histereza)
  - BRAK trailing stopu, profit targetu i timeoutu - sprzedaz wynika WYLACZNIE z pogorszenia rankingu

ROZNICE WOBEC v2/v3 (`quality_value_backtest.py`): tam byla BRAMKA WEJSCIA (drawdown >= 25% +
quality gate) i wyjscia oparte na fundamentach/czasie/stopie. Tu nie ma zadnej bramki - liczy sie
tylko pozycja w rankingu, a jedynym mechanizmem sprzedazy jest wypadniecie z top 8. To inna
strategia, nie inne parametry tej samej, wiec osobny plik (konwencja repo).

DOPRECYZOWANIA SPEC (podjete tak, zeby regula byla jednoznaczna):

1. **Spolka poza top 8 zostaje w portfelu, jesli nie ma kto jej zastapic.** Spec wiaze sprzedaz z
   istnieniem kandydata z top 4 ("wypada, jesli nie jest w top 8, A kandydat jest w top 4"), wiec
   sam spadek rankingu NIE wypycha do gotowki. To celowe: strategia ma byc zawsze zainwestowana.
2. **Wiecej niz jedna podmiana w miesiacu jest dozwolona**, o ile warunki zachodza dla kolejnych par
   (limit `max_replacements_per_month`, domyslnie bez limitu). Inaczej portfel z 4 slabymi pozycjami
   naprawialby sie 4 miesiace.
3. **Pozycja, ktora wypadla z uniwersum PIT, nie jest sprzedawana na sile** - tak samo jak w v2/v3.
   Wypada normalnie, gdy przestanie byc w top 8 (spolka poza uniwersum nie jest w ogole scorowana,
   wiec traktujemy ja jako "poza top 8").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from value_engine.factor_scoring import (
    FactorScore,
    compute_quality,
    compute_value_inputs,
    momentum_12_1,
    score_universe,
)
from value_engine.fundamentals import FundamentalPanel
from value_engine.market_cap import SharesEstimator


@dataclass
class FactorConfig:
    tickers: List[str]
    max_positions: int = 4
    keep_rank: int = 8  # trzymamy, dopoki spolka jest w top `keep_rank` (histereza)
    entry_rank: int = 4  # kandydat musi byc w top `entry_rank`, zeby kogos zastapic
    cost_bps: float = 40.0
    momentum_lookback_days: int = 252
    momentum_skip_days: int = 21
    max_replacements_per_month: Optional[int] = None
    min_value_metrics: int = 2


@dataclass
class Position:
    ticker: str
    entry_date: pd.Timestamp
    entry_price: float
    shares: float
    entry_score: float
    entry_rank: int


@dataclass
class Trade:
    ticker: str
    entry_date: pd.Timestamp
    entry_price: float
    exit_date: pd.Timestamp
    exit_price: float
    exit_reason: str  # "rank_dropout" | "end_of_data"
    gross_return: float
    holding_days: int
    entry_score: float


def run_factor_backtest(
    daily_prices: pd.DataFrame,
    panel: FundamentalPanel,
    estimator: SharesEstimator,
    decision_dates: Sequence[pd.Timestamp],
    config: FactorConfig,
    ticker_to_fundamental_key: Optional[Dict[str, str]] = None,
    eligible_universe: Optional[Dict[pd.Timestamp, List[str]]] = None,
) -> Dict[str, Any]:
    if config.max_positions < 1:
        raise ValueError(f"max_positions musi byc >= 1, dostalem {config.max_positions}.")
    if config.keep_rank < config.entry_rank:
        raise ValueError(
            f"keep_rank ({config.keep_rank}) musi byc >= entry_rank ({config.entry_rank}) - "
            "inaczej histereza dziala odwrotnie i portfel rotuje bez opamietania."
        )

    key_of = ticker_to_fundamental_key or {t: t.upper() for t in config.tickers}
    prices = daily_prices[config.tickers].sort_index()
    priced = prices.ffill()
    cost_rate = config.cost_bps / 10000.0

    cash = 1.0
    positions: Dict[str, Position] = {}
    trades: List[Trade] = []
    decisions: List[Dict[str, Any]] = []
    equity_records: List[tuple] = []
    quality_cache: Dict[tuple, Any] = {}

    decision_set = set(decision_dates)
    first_decision_date: Optional[pd.Timestamp] = None

    def sell(ticker: str, date: pd.Timestamp, price: float, reason: str) -> None:
        nonlocal cash
        position = positions.pop(ticker)
        cash += position.shares * price * (1.0 - cost_rate)
        trades.append(
            Trade(
                ticker=ticker,
                entry_date=position.entry_date,
                entry_price=position.entry_price,
                exit_date=date,
                exit_price=price,
                exit_reason=reason,
                gross_return=price / position.entry_price - 1.0,
                holding_days=(date - position.entry_date).days,
                entry_score=position.entry_score,
            )
        )

    def buy(ticker: str, date: pd.Timestamp, price: float, size: float, score: float, rank: int) -> None:
        nonlocal cash
        spend = min(size, cash)
        if spend <= 0 or price <= 0:
            return
        positions[ticker] = Position(
            ticker=ticker,
            entry_date=date,
            entry_price=price,
            shares=(spend * (1.0 - cost_rate)) / price,
            entry_score=score,
            entry_rank=rank,
        )
        cash -= spend

    def equity_at(row: pd.Series) -> float:
        return cash + sum(
            p.shares * float(row[p.ticker]) for p in positions.values() if pd.notna(row.get(p.ticker))
        )

    for date in prices.index:
        row_price = priced.loc[date]

        if date in decision_set:
            investable = (
                list(config.tickers) if eligible_universe is None else list(eligible_universe.get(date, []))
            )
            momentum = momentum_12_1(priced, date, config.momentum_lookback_days, config.momentum_skip_days)

            value_inputs = {}
            quality_inputs = {}
            for ticker in investable:
                price = row_price.get(ticker)
                fundamental_key = key_of[ticker]
                value_inputs[ticker] = compute_value_inputs(panel, estimator, fundamental_key, price, date)
                cache_key = (fundamental_key, date)
                if cache_key not in quality_cache:
                    quality_cache[cache_key] = compute_quality(panel, fundamental_key, date)
                quality_inputs[ticker] = quality_cache[cache_key]

            scored: List[FactorScore] = score_universe(
                investable, value_inputs, quality_inputs, momentum, min_value_metrics=config.min_value_metrics
            )
            rank_of = {s.ticker: i + 1 for i, s in enumerate(scored)}
            score_of = {s.ticker: s.final for s in scored}

            if scored and first_decision_date is None:
                # Ranking istnieje dopiero, gdy dla co najmniej jednej spolki sa JEDNOCZESNIE:
                # momentum 12-1 (252 sesje historii), opublikowane fundamenty i obecnosc w uniwersum.
                first_decision_date = date

            # --- 1) WEJSCIA na wolne sloty: najlepsi z rankingu ---
            free_slots = config.max_positions - len(positions)
            if free_slots > 0:
                target_size = equity_at(row_price) / config.max_positions
                for candidate in [s for s in scored if s.ticker not in positions][:free_slots]:
                    price = row_price.get(candidate.ticker)
                    if pd.notna(price):
                        buy(
                            candidate.ticker, date, float(price), target_size, candidate.final,
                            rank_of[candidate.ticker],
                        )

            # Rangi trzymanych pozycji ZANIM cokolwiek podmienimy - log musi pokazywac stan, ktory
            # wywolal decyzje. Zapisywanie ich po podmianach jest bezuzyteczne diagnostycznie:
            # pozycja wyrzucona nie jest juz w `positions`, wiec "poza top 8" nigdy sie nie pokazuje.
            ranks_before = {t: rank_of.get(t) for t in sorted(positions)}
            dropouts_before = [
                t for t in positions if rank_of.get(t, len(rank_of) + 1) > config.keep_rank
            ]

            # --- 2) PODMIANA: trzymana poza top `keep_rank` <-> kandydat w top `entry_rank` ---
            replacements = 0
            while config.max_replacements_per_month is None or replacements < config.max_replacements_per_month:
                # spolka poza rankingiem (np. wypadla z uniwersum) traktowana jak "poza top 8"
                dropouts = [
                    t for t in positions if rank_of.get(t, len(rank_of) + 1) > config.keep_rank
                ]
                incoming = [
                    s for s in scored[: config.entry_rank] if s.ticker not in positions
                ]
                if not dropouts or not incoming:
                    break

                weakest = max(dropouts, key=lambda t: rank_of.get(t, len(rank_of) + 1))
                best = incoming[0]
                weakest_price, best_price = row_price.get(weakest), row_price.get(best.ticker)
                if pd.isna(weakest_price) or pd.isna(best_price):
                    break

                sell(weakest, date, float(weakest_price), "rank_dropout")
                buy(
                    best.ticker, date, float(best_price),
                    equity_at(row_price) / config.max_positions, best.final, rank_of[best.ticker],
                )
                replacements += 1

            decisions.append(
                {
                    "date": date,
                    "held": sorted(positions),
                    "n_positions": len(positions),
                    "replacements": replacements,
                    "universe_size": len(investable),
                    "ranked": len(scored),
                    "top": [(s.ticker, round(s.final, 1)) for s in scored[: config.keep_rank]],
                    "held_ranks": ranks_before,
                    "dropouts": dropouts_before,
                    "held_scores": {t: round(score_of.get(t, float("nan")), 1) for t in sorted(positions)},
                }
            )

        position_value = sum(
            p.shares * float(row_price[p.ticker]) for p in positions.values() if pd.notna(row_price.get(p.ticker))
        )
        equity_records.append((date, cash + position_value))

    last_date = prices.index[-1]
    last_prices = priced.loc[last_date]
    for ticker in list(positions):
        price = last_prices.get(ticker)
        if pd.notna(price):
            sell(ticker, last_date, float(price), "end_of_data")

    return {
        "equity_curve": pd.DataFrame(equity_records, columns=["date", "equity"]),
        "trades": trades,
        "decisions": decisions,
        "first_decision_date": first_decision_date,
    }
