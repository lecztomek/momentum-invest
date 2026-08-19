"""
QUALITY VALUE BACKTEST - silnik koncepcji "przeceniona, slaba wzgledem rynku, ale wysokiej
jakosci spolka GPW".

SPEC (dokladnie jak zdefiniowana przez usera):
  - uniwersum: ~20-25 duzych/plynnych spolek GPW, bez bankow i ubezpieczycieli
  - max 4 pozycje, docelowo po 25%
  - bramka wejscia: drawdown >= 25% od 52W high ORAZ QUALITY >= 50
  - SCORE = 0.50*DD + 0.25*REL + 0.25*QUALITY (patrz `scoring.py`)
  - wolny slot -> kupujemy najlepszego kandydata
  - pelny portfel -> nowy kandydat zastepuje najslabsza pozycje TYLKO gdy ma score wyzszy o >= 10 pkt
  - wyjscie: fundamental fail ALBO max holding (24/36 mies.); BEZ szybkiego profit targetu
  - rebalans raz w miesiacu

ROZNICE WOBEC `backtest.py` (poprzednia, odrzucona koncepcja - patrz README): tam byl prog
obsuniecia + binarny filtr zdrowia + profit target; tu jest ciagly ranking percentylowy, regula
podmiany z progiem i wyjscie oparte na fundamentach, nie na cenie. Osobny plik, bo to inna
strategia, a nie inne parametry tej samej - zgodnie z konwencja repo.

TRZY DOPRECYZOWANIA SPEC (podjete tak, zeby regula byla wykonalna i sprawdzalna):

1. **"fundamental fail" = QUALITY < `min_quality`** (ten sam prog, co w bramce wejscia, domyslnie
   50). Spec nie definiowal tego osobno; uzycie tego samego progu jest spojne: trzymamy dopoki
   spolka spelnialaby warunek, na ktorym ja kupilismy.

2. **Co najwyzej JEDNA podmiana na miesiac** (spec: "nowy kandydat zastepuje najslabsza" - liczba
   pojedyncza). Konfigurowalne przez `max_replacements_per_month`, ale domyslnie 1, zeby nie robic
   cichego, wielokrotnego obrotu portfelem w jednym dniu decyzyjnym.

3. **`rebalance_to_target=False` domyslnie.** "Docelowo po 25%" + "rebalans raz w miesiacu" da sie
   czytac dwojako: (a) decyzje podejmujemy miesiecznie, wagi dryfuja, (b) wagi sa co miesiac
   przywracane do 25%. Domyslnie (a), bo (b) dodaje obrot i koszty, ktore spec nie omawia - ale
   flaga jest, bo to realna roznica i warto ja zmierzyc osobno.

KOLEJNOSC W DNIU DECYZYJNYM (istotna): wyjscia -> scoring -> wejscia na wolne sloty -> podmiana.
Wyjscia przed wejsciami, zeby zwolniony slot byl uzywalny od razu.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from value_engine.fundamentals import FundamentalPanel
from value_engine.scoring import QualityResult, compute_quality, drawdown_from_high, score_universe


@dataclass
class QualityValueConfig:
    tickers: List[str]
    max_positions: int = 4
    min_drawdown: float = 0.25  # bramka: >= 25% ponizej 52W high
    min_quality: float = 50.0  # bramka wejscia I prog "fundamental fail" przy wyjsciu
    replace_margin: float = 10.0  # nowy kandydat musi byc lepszy o tyle pkt, zeby podmienic
    max_holding_months: int = 24
    max_replacements_per_month: int = 1
    rebalance_to_target: bool = False
    # WERSJA v3 (user): "Bez comiesiecznej podmiany na podstawie score. Nowy kandydat zastepuje
    # istniejaca pozycje tylko jesli: (1) obecna nie przechodzi quality gate, albo (2) osiagnela
    # 36 miesiecy. Score sluzy tylko do wyboru najlepszego kandydata do wolnego slotu."
    # Te dwa warunki to DOKLADNIE istniejace wyjscia `fundamental_fail` i `timeout`, po ktorych
    # zwolniony slot i tak jest wypelniany najlepszym kandydatem - wiec v3 = v2 z wylaczona
    # podmiana po score. Osobny silnik nie jest potrzebny, wystarczy ta flaga.
    allow_score_replacement: bool = True
    # TRAILING STOP (user): "Po wejsciu zapisujemy highest_close_since_entry. Trailing stop:
    # sprzedaj, jesli kurs spadnie np. 20% od najwyzszego close od momentu zakupu."
    # None = wylaczony. Sprawdzany CODZIENNIE, nie tylko w dniu decyzyjnym - stop jest zleceniem
    # stojacym, a sprawdzanie go raz w miesiacu przepuszczaloby obsuniecia znacznie glebsze niz
    # zadeklarowany prog (przy 20% progu i miesiecznej kontroli realna strata siegala by tyle, ile
    # kurs zdazyl spasc do najblizszego 1. dnia miesiaca).
    trailing_stop: Optional[float] = None
    cost_bps: float = 40.0
    high_lookback_days: int = 252  # 52W high
    relative_lookback_days: int = 126  # ~6M do REL


@dataclass
class Position:
    ticker: str
    entry_date: pd.Timestamp
    entry_price: float
    shares: float
    entry_score: float
    highest_close: float = 0.0  # najwyzszy close OD MOMENTU ZAKUPU - baza trailing stopu


@dataclass
class Trade:
    ticker: str
    entry_date: pd.Timestamp
    entry_price: float
    exit_date: pd.Timestamp
    exit_price: float
    exit_reason: str  # "fundamental_fail" | "timeout" | "replaced" | "end_of_data"
    gross_return: float
    holding_days: int
    entry_score: float


def _relative_weakness(
    prices: pd.DataFrame, benchmark: pd.Series, date: pd.Timestamp, lookback_days: int
) -> Dict[str, Optional[float]]:
    """REL wejsciowy: `return_benchmark - return_spolki` za okno `lookback_days`. Im bardziej
    spolka zostala w tyle, tym WIEKSZA wartosc (i tym wyzszy percentyl w `scoring`)."""
    index = prices.index
    position = index.get_indexer([date])[0]
    if position < lookback_days:
        return {ticker: None for ticker in prices.columns}

    past_date = index[position - lookback_days]
    benchmark_return = _safe_return(benchmark.get(past_date), benchmark.get(date))

    out: Dict[str, Optional[float]] = {}
    for ticker in prices.columns:
        stock_return = _safe_return(prices.at[past_date, ticker], prices.at[date, ticker])
        out[ticker] = (
            None if stock_return is None or benchmark_return is None else benchmark_return - stock_return
        )
    return out


def _safe_return(start: Optional[float], end: Optional[float]) -> Optional[float]:
    if start is None or end is None or pd.isna(start) or pd.isna(end) or start <= 0:
        return None
    return end / start - 1.0


def run_quality_value_backtest(
    daily_prices: pd.DataFrame,
    benchmark: pd.Series,
    panel: FundamentalPanel,
    decision_dates: Sequence[pd.Timestamp],
    config: QualityValueConfig,
    ticker_to_fundamental_key: Optional[Dict[str, str]] = None,
    eligible_universe: Optional[Dict[pd.Timestamp, List[str]]] = None,
) -> Dict[str, Any]:
    """`eligible_universe` (opcjonalne): uniwersum POINT-IN-TIME, data -> lista spolek realnie
    inwestowalnych w tym momencie (patrz `universe.py`). Ogranicza WYLACZNIE NOWE WEJSCIA; pozycja
    juz trzymana, ktora wypadla z uniwersum (np. spadla plynnosc), NIE jest sprzedawana na sile -
    wychodzi normalnymi reguami (fundamental fail / max holding). Wymuszona sprzedaz przy spadku
    plynnosci bylaby zresztą nierealistyczna: wtedy najtrudniej wyjsc.
    Gdy `None` - uniwersum stale, `config.tickers` przez cala historie."""
    if config.max_positions < 1:
        raise ValueError(f"max_positions musi byc >= 1, dostalem {config.max_positions}.")

    key_of = ticker_to_fundamental_key or {t: t.upper() for t in config.tickers}
    prices = daily_prices[config.tickers].sort_index()
    priced = prices.ffill()
    rolling_high = priced.rolling(window=config.high_lookback_days, min_periods=config.high_lookback_days).max()
    benchmark = benchmark.reindex(prices.index).ffill()
    cost_rate = config.cost_bps / 10000.0

    cash = 1.0
    positions: Dict[str, Position] = {}
    trades: List[Trade] = []
    decisions: List[Dict[str, Any]] = []
    equity_records: List[tuple] = []
    quality_cache: Dict[tuple, QualityResult] = {}

    decision_set = set(decision_dates)
    first_decision_date: Optional[pd.Timestamp] = None

    def quality_of(ticker: str, date: pd.Timestamp) -> QualityResult:
        cache_key = (ticker, date)
        if cache_key not in quality_cache:
            quality_cache[cache_key] = compute_quality(panel, key_of[ticker], date)
        return quality_cache[cache_key]

    def equity_at(date_prices: pd.Series) -> float:
        return cash + sum(
            p.shares * float(date_prices.get(p.ticker) or 0.0)
            for p in positions.values()
            if not pd.isna(date_prices.get(p.ticker))
        )

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

    def buy(ticker: str, date: pd.Timestamp, price: float, size: float, score: float) -> None:
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
            highest_close=price,
        )
        cash -= spend

    for date in prices.index:
        row_price = priced.loc[date]

        # --- 0) TRAILING STOP: aktualizacja szczytu i kontrola CODZIENNIE (zlecenie stojace) ---
        # Robione PRZED blokiem decyzyjnym, zeby slot zwolniony stopem byl od razu dostepny, jesli
        # dzis wypada dzien decyzyjny, i PRZED wycena, zeby equity odzwierciedlalo sprzedaz.
        for ticker in list(positions):
            price = row_price.get(ticker)
            if price is None or pd.isna(price):
                continue
            position = positions[ticker]
            position.highest_close = max(position.highest_close, float(price))
            if config.trailing_stop is not None and float(price) <= position.highest_close * (
                1.0 - config.trailing_stop
            ):
                sell(ticker, date, float(price), "trailing_stop")

        if date in decision_set:
            # --- 1) WYJSCIA: fundamental fail albo przetrzymanie ---
            for ticker in list(positions):
                price = row_price.get(ticker)
                if price is None or pd.isna(price):
                    continue
                position = positions[ticker]
                months_held = (date.year - position.entry_date.year) * 12 + (date.month - position.entry_date.month)

                reason = None
                if quality_of(ticker, date).score < config.min_quality:
                    reason = "fundamental_fail"
                elif months_held >= config.max_holding_months:
                    reason = "timeout"
                if reason:
                    sell(ticker, date, float(price), reason)

            # --- 2) SCORING: kandydaci z bramki + aktualnie trzymane (jedna wspolna skala) ---
            relative = _relative_weakness(priced, benchmark, date, config.relative_lookback_days)
            drawdowns: Dict[str, float] = {}
            qualities: Dict[str, QualityResult] = {}
            for ticker in config.tickers:
                drawdown = drawdown_from_high(row_price.get(ticker), rolling_high.at[date, ticker])
                if drawdown is None or relative.get(ticker) is None:
                    continue
                drawdowns[ticker] = drawdown
                qualities[ticker] = quality_of(ticker, date)

            scored = score_universe(
                list(drawdowns),
                drawdowns,
                {t: relative[t] for t in drawdowns},
                qualities,
                min_drawdown=config.min_drawdown,
                min_quality=config.min_quality,
            )
            by_ticker = {s.ticker: s for s in scored}

            investable = None if eligible_universe is None else set(eligible_universe.get(date, []))

            if first_decision_date is None and any(
                qualities[t].values["net_income_ttm"] is not None
                and (investable is None or t in investable)
                for t in qualities
            ):
                # Metryki liczymy od momentu, gdy dla co najmniej jednej spolki byly JEDNOCZESNIE:
                # sygnaly cenowe (52W high, 6M relative), OPUBLIKOWANE fundamenty ORAZ obecnosc w
                # uniwersum point-in-time.
                # UWAGA: samo `scored` nie wystarcza jako warunek - `compute_quality` zwraca
                # poprawny obiekt ze score 0 takze gdy fundamentow NIE MA (brak danych = kryterium
                # niespelnione), wiec ranking istnieje juz od 1995 (same ceny), a fundamenty
                # zaczynaja sie dopiero ~2005. Bez tego warunku metryki liczylyby sie od 1995 i
                # dekada martwej gotowki cicho rozwadnialaby CAGR - ten sam blad, co naprawiony
                # w `engine_v2` dla strategii laczonych (CHANGELOG 2026-08-12 (2)).
                first_decision_date = date

            candidates = [
                s
                for s in scored
                if s.passes_entry_gate
                and s.ticker not in positions
                and (investable is None or s.ticker in investable)
            ]

            # --- 3) WEJSCIA na wolne sloty ---
            free_slots = config.max_positions - len(positions)
            if free_slots > 0 and candidates:
                target_size = equity_at(row_price) / config.max_positions
                for candidate in candidates[:free_slots]:
                    price = row_price.get(candidate.ticker)
                    if price is not None and not pd.isna(price):
                        buy(candidate.ticker, date, float(price), target_size, candidate.score)

            # --- 4) PODMIANA najslabszej pozycji, gdy portfel pelny ---
            replacements = 0
            while (
                config.allow_score_replacement
                and len(positions) >= config.max_positions
                and replacements < config.max_replacements_per_month
            ):
                held_scored = [(by_ticker[t].score, t) for t in positions if t in by_ticker]
                remaining = [c for c in candidates if c.ticker not in positions]
                if not held_scored or not remaining:
                    break
                weakest_score, weakest = min(held_scored)
                best = remaining[0]
                if best.score - weakest_score < config.replace_margin:
                    break

                weakest_price = row_price.get(weakest)
                best_price = row_price.get(best.ticker)
                if weakest_price is None or pd.isna(weakest_price) or best_price is None or pd.isna(best_price):
                    break

                sell(weakest, date, float(weakest_price), "replaced")
                buy(
                    best.ticker,
                    date,
                    float(best_price),
                    equity_at(row_price) / config.max_positions,
                    best.score,
                )
                replacements += 1

            # --- 5) opcjonalny rebalans do 25% ---
            if config.rebalance_to_target and positions:
                cash = _rebalance_to_target(positions, row_price, cash, config)

            decisions.append(
                {
                    "date": date,
                    "held": sorted(positions),
                    "n_positions": len(positions),
                    "candidates": [(c.ticker, round(c.score, 2)) for c in candidates],
                    "scores": {s.ticker: round(s.score, 2) for s in scored},
                    "replacements": replacements,
                }
            )

        position_value = 0.0
        for position in positions.values():
            price = row_price.get(position.ticker)
            if price is not None and not pd.isna(price):
                position_value += position.shares * float(price)
        equity_records.append((date, cash + position_value))

    # pozycje otwarte na koniec danych - domykamy, zeby statystyki transakcji byly kompletne
    last_date = prices.index[-1]
    last_prices = priced.loc[last_date]
    for ticker in list(positions):
        price = last_prices.get(ticker)
        if price is not None and not pd.isna(price):
            sell(ticker, last_date, float(price), "end_of_data")

    return {
        "equity_curve": pd.DataFrame(equity_records, columns=["date", "equity"]),
        "trades": trades,
        "decisions": decisions,
        "first_decision_date": first_decision_date,
    }


def _rebalance_to_target(
    positions: Dict[str, Position],
    row_price: pd.Series,
    cash: float,
    config: QualityValueConfig,
) -> float:
    """Przywraca wagi do 1/max_positions equity. Zwraca nowy stan gotowki."""
    equity = cash + sum(
        p.shares * float(row_price.get(p.ticker) or 0.0)
        for p in positions.values()
        if not pd.isna(row_price.get(p.ticker))
    )
    target = equity / config.max_positions
    cost_rate = config.cost_bps / 10000.0

    for ticker, position in positions.items():
        price = row_price.get(ticker)
        if price is None or pd.isna(price) or price <= 0:
            continue
        difference = target - position.shares * float(price)
        # martwa strefa 5% - bez niej rebalans handlowalby groszami kazdego miesiaca
        if abs(difference) < target * 0.05:
            continue
        cash -= difference + abs(difference) * cost_rate
        position.shares = target / float(price)

    return cash
