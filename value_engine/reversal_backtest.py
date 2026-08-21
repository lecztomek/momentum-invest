"""
REVERSAL BACKTEST - silnik koncepcji v9 "Large-Cap Overreaction Reversal".

SPEC: trigger = spadek miesieczny <= -20%; bramka jakosci/distressu (`reversal.evaluate_gate`);
kupno na poczatku kolejnego miesiaca po sygnale; max 4 spolki equal weight; holding 3 / 6 / 12
miesiecy; exit tylko po holdingu albo przy fundamental fail; bez trailing stopu, momentum, kanarka i
rankingu poza "najwiekszy spadek".

DLACZEGO OSOBNY SILNIK. Najblizszy jest `quality_value_backtest.py` (v2/v3): tez ma sloty,
`fundamental_fail` i timeout. Ale rozni sie w trzech rzeczach, ktore siedza w rdzeniu logiki, nie w
parametrach: (1) trigger to **zwrot miesieczny**, nie obsuniecie od 52W high, (2) bramka to osiem
warunkow distressu, nie `QUALITY >= 50`, (3) wybor kandydata to **najwiekszy spadek**, nie score
przekrojowy. Wpiecie tego flagami znaczyloby trzy rozgalezienia w kazdej z tych warstw.

DOPRECYZOWANIA SPEC:

1. **"Kupno na poczatku kolejnego miesiaca po sygnale"** = pierwsza sesja miesiaca NASTEPUJACEGO po
   miesiacu, w ktorym byl spadek. Sygnal "spadek w miesiacu M" jest znany dopiero po zamknieciu M,
   czyli na pierwszej sesji M+1 - i wtedy kupujemy, po cenie z tej sesji. **Zero opoznienia wiecej**:
   dodatkowy miesiac czekania byl by inna strategia (i tak da sie ja sprawdzic parametrem
   `entry_delay_months`).
2. **Bramka jest sprawdzana W DNIU ZAKUPU**, na danych opublikowanych do tego dnia - a nie w dniu,
   w ktorym spadek sie zaczal.
3. **Brak podmian.** Spec mowi "max 4 spolki" i nie przewiduje zastepowania, wiec przy pelnym
   portfelu nowi kandydaci sa POMIJANI (nie kolejkowani). Log zapisuje, ilu kandydatow przepadlo z
   braku slotu - przy 4 pozycjach i 3-miesiecznym holdingu to istotna liczba.
4. **`fundamental_fail` sprawdzany co miesiac** na tej samej bramce co wejscie. Spec mowi "exit ...
   wczesniej przy fundamental fail", a jedyna sensowna definicja "fail" to przestanie spelniac
   warunki, ktore byly warunkiem wejscia.
5. **Spolka, ktora wypadla z uniwersum PIT, NIE jest sprzedawana na sile** - tak jak w v2-v8.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from value_engine.fundamentals import FundamentalPanel
from value_engine.reversal import GateResult, evaluate_gate, find_candidates, monthly_returns


@dataclass
class ReversalConfig:
    tickers: List[str]
    trigger: float = -0.20  # spec: zwrot miesieczny <= -20%
    holding_months: int = 6  # spec: testujemy 3 / 6 / 12
    max_positions: int = 4
    cost_bps: float = 40.0
    entry_delay_months: int = 0  # 0 = kupno na pierwszej sesji miesiaca po spadku
    check_fundamental_fail: bool = True
    max_debt_ratio: float = 0.60
    max_debt_ratio_jump: float = 0.10
    max_revenue_drop: float = 0.20
    max_ebit_drop: float = 0.40
    max_share_issuance: float = 0.10

    def gate_kwargs(self) -> Dict[str, float]:
        return {
            "max_debt_ratio": self.max_debt_ratio,
            "max_debt_ratio_jump": self.max_debt_ratio_jump,
            "max_revenue_drop": self.max_revenue_drop,
            "max_ebit_drop": self.max_ebit_drop,
            "max_share_issuance": self.max_share_issuance,
        }


@dataclass
class Position:
    ticker: str
    entry_date: pd.Timestamp
    entry_price: float
    shares: float
    trigger_return: float
    deadline: pd.Timestamp


@dataclass
class Trade:
    ticker: str
    entry_date: pd.Timestamp
    entry_price: float
    exit_date: pd.Timestamp
    exit_price: float
    exit_reason: str  # "holding_period" | "fundamental_fail" | "end_of_data"
    gross_return: float
    holding_days: int
    trigger_return: float


def run_reversal_backtest(
    daily_prices: pd.DataFrame,
    panel: FundamentalPanel,
    decision_dates: Sequence[pd.Timestamp],
    config: ReversalConfig,
    ticker_to_fundamental_key: Optional[Dict[str, str]] = None,
    eligible_universe: Optional[Dict[pd.Timestamp, List[str]]] = None,
) -> Dict[str, Any]:
    if config.trigger >= 0:
        raise ValueError(f"trigger musi byc ujemny (spadek), dostalem {config.trigger}.")
    if config.holding_months < 1:
        raise ValueError(f"holding_months musi byc >= 1, dostalem {config.holding_months}.")
    if config.max_positions < 1:
        raise ValueError(f"max_positions musi byc >= 1, dostalem {config.max_positions}.")

    key_of = ticker_to_fundamental_key or {t: t.upper() for t in config.tickers}
    prices = daily_prices[config.tickers].sort_index()
    priced = prices.ffill()
    cost_rate = config.cost_bps / 10000.0
    returns_by_date = monthly_returns(prices, decision_dates)

    cash = 1.0
    positions: Dict[str, Position] = {}
    trades: List[Trade] = []
    decisions: List[Dict[str, Any]] = []
    equity_records: List[tuple] = []
    rejection_counts: Dict[str, int] = {}
    pending: Dict[pd.Timestamp, List[tuple]] = {}

    ordered_dates = [d for d in decision_dates if d in prices.index]
    date_position = {date: index for index, date in enumerate(ordered_dates)}
    decision_set = set(ordered_dates)
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
                trigger_return=position.trigger_return,
            )
        )

    def equity_at(row: pd.Series) -> float:
        return cash + sum(
            p.shares * float(row[p.ticker]) for p in positions.values() if pd.notna(row.get(p.ticker))
        )

    for date in prices.index:
        row_price = priced.loc[date]

        if date in decision_set:
            index = date_position[date]

            # --- 1) WYJSCIA: koniec holdingu albo fundamental fail ---
            for ticker in list(positions):
                position = positions[ticker]
                price = row_price.get(ticker)
                if pd.isna(price):
                    continue
                if date >= position.deadline:
                    sell(ticker, date, float(price), "holding_period")
                elif config.check_fundamental_fail:
                    gate = evaluate_gate(panel, key_of[ticker], date, **config.gate_kwargs())
                    if not gate.ok:
                        sell(ticker, date, float(price), "fundamental_fail")

            # --- 2) SYGNAL: spadek w POPRZEDNIM miesiacu, bramka liczona NA DZIS ---
            investable = (
                list(config.tickers)
                if eligible_universe is None
                else list(eligible_universe.get(date, []))
            )
            returns = returns_by_date.get(date, {})
            candidates, gates, triggered = find_candidates(
                returns, investable, panel, date, trigger=config.trigger,
                ticker_to_fundamental_key=key_of, **config.gate_kwargs(),
            )
            for gate in gates.values():
                for failure in gate.failures():
                    rejection_counts[failure] = rejection_counts.get(failure, 0) + 1

            if investable and returns and first_decision_date is None:
                # Strategia moze dzialac od momentu, w ktorym uniwersum PIT NIE JEST PUSTE i istnieje
                # zwrot miesieczny. Warunek `investable` jest tu istotny: bez niego okno metryk
                # zaczynaloby sie w 1993 (pierwsze ceny w zbiorze), a strategia siedzialaby kilka lat
                # w gotowce, bo zadna spolka nie przechodzila jeszcze progu plynnosci. To rozwodnilo
                # by CAGR o okres, w ktorym strategia z definicji nie mogla nic kupic.
                first_decision_date = date

            # --- 3) KOLEJKA (opcjonalne opoznienie wejscia) ---
            target_index = index + config.entry_delay_months
            if target_index < len(ordered_dates):
                pending.setdefault(ordered_dates[target_index], []).extend(candidates)

            # --- 4) WEJSCIA equal weight na wolne sloty ---
            ready = pending.pop(date, [])
            free_slots = config.max_positions - len(positions)
            bought: List[str] = []
            skipped_no_slot = 0
            if ready:
                deadline_index = min(index + config.holding_months, len(ordered_dates) - 1)
                deadline = ordered_dates[deadline_index]
                target_size = equity_at(row_price) / config.max_positions
                for ticker, drop in ready:
                    if ticker in positions:
                        continue
                    if free_slots <= 0:
                        skipped_no_slot += 1
                        continue
                    price = row_price.get(ticker)
                    if pd.isna(price) or float(price) <= 0:
                        continue
                    spend = min(target_size, cash)
                    if spend <= 0:
                        skipped_no_slot += 1
                        continue
                    positions[ticker] = Position(
                        ticker=ticker,
                        entry_date=date,
                        entry_price=float(price),
                        shares=(spend * (1.0 - cost_rate)) / float(price),
                        trigger_return=drop,
                        deadline=deadline,
                    )
                    cash -= spend
                    free_slots -= 1
                    bought.append(ticker)

            decisions.append(
                {
                    "date": date,
                    "universe_size": len(investable),
                    "triggered": sorted(triggered),
                    "passed_gate": [t for t, _ in candidates],
                    "bought": bought,
                    "skipped_no_slot": skipped_no_slot,
                    "held": sorted(positions),
                    "n_positions": len(positions),
                }
            )

        position_value = sum(
            p.shares * float(row_price[p.ticker])
            for p in positions.values()
            if pd.notna(row_price.get(p.ticker))
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
        "rejection_counts": rejection_counts,
        "first_decision_date": first_decision_date,
    }
