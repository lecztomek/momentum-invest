"""
QUALITY BACKTEST - silnik koncepcji v6 "czysta jakosc".

SPEC (user):
  - uniwersum: plynne spolki GPW, point-in-time
  - BEZ Value i BEZ Momentum; score = wylacznie jakosc biznesu (`quality_scoring.py`)
  - ranking: kupujemy **top 20-25%** spolek
  - portfel: **equal weight**
  - rebalans: **kwartalny**
  - histereza: trzymamy, dopoki pozycja nie spadnie ponizej **40-50 percentyla** rankingu
  - exit: pogorszenie quality albo wypadniecie ponizej progu
  - BEZ stop lossow, kanarka i profit targetow

DLACZEGO OSOBNY SILNIK, A NIE `scorer=` W `factor_backtest.py`. v5 dalo sie wpiac przez `scorer=`,
bo roznilo sie WYLACZNIE rankingiem. v6 zmienia trzy rzeczy w samej mechanice portfela:

  1. **Liczba pozycji jest ZMIENNA** - `top 20-25% uniwersum` to 3 pozycje przy 14 rankowanych
     spolkach i 5 przy 22. `factor_backtest` ma staly `max_positions` i dzieli kapital na sztywno.
  2. **Histereza na PERCENTYLU, nie na pozycji w rankingu** - "ponizej 45 percentyla" znaczy co
     innego przy 10 i przy 22 spolkach, a `keep_rank=8` znaczylo cos innego (to wlasnie ten problem
     wywrocil v4 przy poszerzeniu uniwersum z 22 do 41 spolek).
  3. **Equal weight z realnym rebalansem** - v4/v5 kupowaly po 1/N i NIE wyrownywaly wag pozniej.
     Tu "equal weight + rebalans kwartalny" znaczy dociazanie i odchudzanie pozycji, wiec pojawiaja
     sie koszty, ktorych tamten silnik nie liczy.

DOPRECYZOWANIA SPEC:

1. **Spolka, ktora wypadla z uniwersum PIT (spadla plynnosc), NIE jest sprzedawana na sile** - tak
   samo jak w v2-v5. Wymuszona sprzedaz przy zaniku plynnosci jest nierealistyczna: wtedy najtrudniej
   wyjsc. Taka pozycja nie jest tez scorowana, wiec czeka na powrot do uniwersum.
2. **Spolka, ktora JEST w uniwersum, ale nie da sie jej ocenic** (brak opublikowanych fundamentow,
   mniej niz `min_components` skladnikow) jest SPRZEDAWANA - to dokladnie "pogorszenie quality" ze
   spec: przestalismy wiedziec, czy firma jest dobra.
3. **Gdy uniwersum sie zwezi i mamy wiecej pozycji niz `top X%`**, nadwyzka jest sprzedawana od
   najslabszej. Inaczej liczba pozycji tylko rosla by w czasie i "top 20-25%" przestalo by cokolwiek
   znaczyc.
4. **`gross_return` w logu transakcji to zwrot CENOWY** (cena wyjscia / cena wejscia), a nie zwrot
   pieniezny pozycji - przy rebalansie liczba akcji zmienia sie w trakcie zycia pozycji, wiec te
   dwie liczby nie sa tozsame. Krzywa kapitalu jest oczywiscie liczona z faktycznych stanow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from value_engine.fundamentals import FundamentalPanel
from value_engine.quality_scoring import QualityScore, compute_quality_inputs, score_universe


@dataclass
class QualityConfig:
    tickers: List[str]
    top_fraction: float = 0.25  # spec: "top 20-25%"
    keep_percentile: float = 45.0  # spec: "ponizej np. 40-50 percentyla"
    min_positions: int = 1
    max_positions: Optional[int] = None  # bez limitu; przy top 25% i 22 nazwach to i tak ~5
    cost_bps: float = 40.0
    min_components: int = 4
    rebalance_to_equal_weight: bool = True
    # Pozycja jest wyrownywana tylko wtedy, gdy odchylenie od wagi docelowej przekracza ten prog -
    # bez tego kazdy kwartal generuje kilkanascie mikro-transakcji, ktore w rzeczywistosci nikt by
    # nie zlozyl, a ktore kosztuja 40 bps od kazdej zlotowki obrotu.
    rebalance_tolerance: float = 0.02


@dataclass
class Position:
    ticker: str
    entry_date: pd.Timestamp
    entry_price: float
    shares: float
    entry_score: float
    entry_percentile: float


@dataclass
class Trade:
    ticker: str
    entry_date: pd.Timestamp
    entry_price: float
    exit_date: pd.Timestamp
    exit_price: float
    exit_reason: str  # "below_keep_percentile" | "quality_unavailable" | "over_target" | "end_of_data"
    gross_return: float
    holding_days: int
    entry_score: float


def run_quality_backtest(
    daily_prices: pd.DataFrame,
    panel: FundamentalPanel,
    decision_dates: Sequence[pd.Timestamp],
    config: QualityConfig,
    ticker_to_fundamental_key: Optional[Dict[str, str]] = None,
    eligible_universe: Optional[Dict[pd.Timestamp, List[str]]] = None,
) -> Dict[str, Any]:
    if not 0.0 < config.top_fraction <= 1.0:
        raise ValueError(f"top_fraction musi byc w (0, 1], dostalem {config.top_fraction}.")
    if not 0.0 <= config.keep_percentile <= 100.0:
        raise ValueError(f"keep_percentile musi byc w [0, 100], dostalem {config.keep_percentile}.")

    key_of = ticker_to_fundamental_key or {t: t.upper() for t in config.tickers}
    prices = daily_prices[config.tickers].sort_index()
    priced = prices.ffill()
    cost_rate = config.cost_bps / 10000.0
    score_cache: Dict[tuple, Any] = {}

    cash = 1.0
    positions: Dict[str, Position] = {}
    trades: List[Trade] = []
    decisions: List[Dict[str, Any]] = []
    equity_records: List[tuple] = []
    turnover_records: List[tuple] = []

    decision_set = set(decision_dates)
    first_decision_date: Optional[pd.Timestamp] = None

    def equity_at(row: pd.Series) -> float:
        return cash + sum(
            p.shares * float(row[p.ticker]) for p in positions.values() if pd.notna(row.get(p.ticker))
        )

    def _weights(row: pd.Series) -> Dict[str, float]:
        total = equity_at(row)
        if total <= 0:
            return {}
        return {
            t: round(p.shares * float(row[t]) / total, 4)
            for t, p in sorted(positions.items())
            if pd.notna(row.get(t))
        }

    def sell(ticker: str, date: pd.Timestamp, price: float, reason: str) -> float:
        nonlocal cash
        position = positions.pop(ticker)
        proceeds = position.shares * price
        cash += proceeds * (1.0 - cost_rate)
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
        return proceeds

    def buy(ticker: str, date: pd.Timestamp, price: float, size: float, score: QualityScore) -> float:
        nonlocal cash
        spend = min(size, cash)
        if spend <= 0 or price <= 0:
            return 0.0
        positions[ticker] = Position(
            ticker=ticker,
            entry_date=date,
            entry_price=price,
            shares=(spend * (1.0 - cost_rate)) / price,
            entry_score=score.final,
            entry_percentile=score.percentile,
        )
        cash -= spend
        return spend

    def rebalance(date: pd.Timestamp, row: pd.Series) -> float:
        """Wyrownuje wagi trzymanych pozycji do 1/N. Zwraca obrot (wartosc bezwzglednie
        przehandlowana), zeby dalo sie pokazac koszt tej operacji."""
        nonlocal cash
        if not positions:
            return 0.0
        target = equity_at(row) / len(positions)
        traded = 0.0

        # DWA PRZEBIEGI: najpierw WSZYSTKIE sprzedaze, potem WSZYSTKIE dokupienia. Jeden przebieg
        # zostawial gotowke bezczynnie: pozycja do dociazenia przetworzona PRZED pozycja, ktora ma
        # ja sfinansowac, widziala `cash = 0` i nic nie kupowala, a gotowka ze pozniejszej sprzedazy
        # lezala do nastepnego kwartalu. Zlapane na realnych danych - 2009-01-02: wagi 0.395 / 0.500
        # i 10.5% w gotowce po "wyrownaniu do 1/N".
        plans = []
        for position in list(positions.values()):
            price = row.get(position.ticker)
            if pd.isna(price) or float(price) <= 0:
                continue
            price = float(price)
            delta = target - position.shares * price
            if abs(delta) < config.rebalance_tolerance * target:
                continue
            plans.append((position, price, delta))

        for position, price, delta in plans:
            if delta >= 0:
                continue
            shares_to_sell = min(position.shares, -delta / price)
            position.shares -= shares_to_sell
            cash += shares_to_sell * price * (1.0 - cost_rate)
            traded += shares_to_sell * price

        for position, price, delta in plans:
            if delta <= 0:
                continue
            spend = min(delta, cash)
            if spend <= 0:
                continue
            position.shares += (spend * (1.0 - cost_rate)) / price
            cash -= spend
            traded += spend

        return traded

    for date in prices.index:
        row_price = priced.loc[date]
        turnover = 0.0

        if date in decision_set:
            investable = (
                list(config.tickers) if eligible_universe is None else list(eligible_universe.get(date, []))
            )
            inputs = {}
            for ticker in investable:
                cache_key = (key_of[ticker], date)
                if cache_key not in score_cache:
                    score_cache[cache_key] = compute_quality_inputs(panel, key_of[ticker], date)
                inputs[ticker] = score_cache[cache_key]
            scored = score_universe(investable, inputs, min_components=config.min_components)

            if scored and first_decision_date is None:
                first_decision_date = date

            percentile_of = {s.ticker: s.percentile for s in scored}
            investable_set = set(investable)
            n_target = max(config.min_positions, round(config.top_fraction * len(scored))) if scored else 0
            if config.max_positions is not None:
                n_target = min(n_target, config.max_positions)

            # --- 1) WYJSCIA: ponizej progu percentyla albo brak oceny (patrz doprecyzowania 1-2) ---
            for ticker in list(positions):
                if ticker not in investable_set:
                    continue  # wypadla z uniwersum PIT - nie sprzedajemy na sile
                price = row_price.get(ticker)
                if pd.isna(price):
                    continue
                if ticker not in percentile_of:
                    turnover += sell(ticker, date, float(price), "quality_unavailable")
                elif percentile_of[ticker] < config.keep_percentile:
                    turnover += sell(ticker, date, float(price), "below_keep_percentile")

            # --- 2) NADWYZKA nad top X% - sprzedajemy od najslabszej (doprecyzowanie 3) ---
            while len(positions) > n_target:
                weakest = min(positions, key=lambda t: percentile_of.get(t, -1.0))
                price = row_price.get(weakest)
                if pd.isna(price):
                    break
                turnover += sell(weakest, date, float(price), "over_target")

            # --- 3) WEJSCIA: najlepsi z rankingu na wolne miejsca ---
            free_slots = n_target - len(positions)
            if free_slots > 0:
                candidates = [s for s in scored if s.ticker not in positions][:free_slots]
                # Rozmiar liczony na docelowej liczbie pozycji, a nie na wolnych miejscach - inaczej
                # przy 1 wolnym miejscu z 4 wpakowalibysmy w nie caly wolny kapital.
                target_size = equity_at(row_price) / n_target if n_target else 0.0
                for candidate in candidates:
                    price = row_price.get(candidate.ticker)
                    if pd.notna(price):
                        turnover += buy(candidate.ticker, date, float(price), target_size, candidate)

            # --- 4) EQUAL WEIGHT ---
            if config.rebalance_to_equal_weight:
                turnover += rebalance(date, row_price)

            decisions.append(
                {
                    "date": date,
                    "held": sorted(positions),
                    "n_positions": len(positions),
                    "n_target": n_target,
                    "universe_size": len(investable),
                    "ranked": len(scored),
                    "top": [(s.ticker, round(s.final, 1)) for s in scored[: max(n_target, 5)]],
                    "held_percentiles": {t: round(percentile_of.get(t, float("nan")), 1) for t in sorted(positions)},
                    # Wagi PO wszystkich operacjach danego dnia - przy `rebalance_to_equal_weight`
                    # powinny byc niemal rowne; rozjazd pokazuje, ile realnie robi rebalans.
                    "weights": _weights(row_price),
                    "turnover": turnover,
                }
            )

        position_value = sum(
            p.shares * float(row_price[p.ticker]) for p in positions.values() if pd.notna(row_price.get(p.ticker))
        )
        equity_records.append((date, cash + position_value))
        turnover_records.append((date, turnover))

    last_date = prices.index[-1]
    last_prices = priced.loc[last_date]
    for ticker in list(positions):
        price = last_prices.get(ticker)
        if pd.notna(price):
            sell(ticker, last_date, float(price), "end_of_data")

    return {
        "equity_curve": pd.DataFrame(equity_records, columns=["date", "equity"]),
        "turnover": pd.DataFrame(turnover_records, columns=["date", "turnover"]),
        "trades": trades,
        "decisions": decisions,
        "first_decision_date": first_decision_date,
    }
