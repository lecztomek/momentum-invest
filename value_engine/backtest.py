"""
BACKTEST - silnik POJEDYNCZYCH TRANSAKCJI (otwarcie -> trzymanie -> wlasny warunek wyjscia).

DLACZEGO TO NIE JEST W `engine_v2` (ocena zrobiona przed napisaniem tego pliku):

`engine_v2` jest silnikiem ROTACYJNYM, BEZSTANOWYM WZGLEDEM POZYCJI: kazdego miesiaca liczy wagi
docelowe OD ZERA z biezacych wartosci wskaznikow, a `PortfolioState` niesie miedzy miesiacami
wylacznie `current_weights` / `equity` / `tax_base_equity` / `last_target_signature`. NIE ma tam
ani CENY WEJSCIA pozycji, ani CZASU JEJ TRZYMANIA.

Ta koncepcja wymaga obu:
  - "exit po odbiciu do okreslonego poziomu" -> potrzebna cena wejscia kazdej pozycji osobno,
  - "exit po maks. 6 miesiacach"            -> potrzebny czas trzymania kazdej pozycji osobno.

Dodanie tych pol do `PortfolioState` znaczylo by modyfikacje WSPOLNEGO silnika, z ktorego
korzysta ~50 istniejacych strategii - wprost przeciwko ustalonej w tym repo zasadzie ("warianty
eksperymentalne wspoldzielonych mechanizmow to ZAWSZE osobny plik, nigdy dodatkowa flaga w
produkcyjnym bloku"). Do tego jest to inny PARADYGMAT (portfel zawsze w pelni zaalokowany wg
biezacego sygnalu vs dyskretne transakcje z wlasnym cyklem zycia), a nie brakujacy parametr.

Co JEST ponownie uzyte z `engine_v2` (bez kopiowania):
  - `blocks.data_loader["stooq_csv"]` - dane PL sa w tym samym formacie stooq (patrz `signals.py`),
  - `metrics.compute_metrics` - te same definicje CAGR/MaxDD/Sharpe/Calmar, wiec liczby z
    `value_engine` sa porownywalne 1:1 z reszta repo.

KSIEGOWANIE: prawdziwa dzienna krzywa equity (gotowka + pozycje wycenione po biezacej cenie), a
nie szereg miesiecznych zwrotow - dzieki temu MaxDD jest uczciwy (lapie obsuniecia WEWNATRZ
miesiaca trzymania, nie tylko na datach decyzyjnych).

KOLEJNOSC W DNIU DECYZYJNYM jest istotna i celowa: najpierw WYJSCIA, potem WEJSCIA - inaczej
zwolniony slot nie moglby byc uzyty w tym samym miesiacu i strategia sztucznie by czekala.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from value_engine.fundamentals import FundamentalPanel


@dataclass
class StrategyConfig:
    """Parametry strategii. Wartosci domyslne = pierwsze rozsadne zalozenia z opisu koncepcji
    (user: "np. >=25% ponizej 52W high", "max 2-3 spolki", "po maks. 6 miesiacach") - nie sa
    zadnym optimum, sa punktem startu do sweepu."""

    tickers: List[str]
    max_positions: int = 3
    min_drawdown: float = -0.25  # "mocno przeceniona": co najmniej 25% ponizej 52W high
    exit_gain: float = 0.20  # "odbicie do okreslonego poziomu": +20% od ceny wejscia
    max_holding_months: int = 6
    cost_bps: float = 40.0  # jednostronnie, ta sama konwencja co strategie US w tym repo
    require_positive_net_profit: bool = True
    require_positive_cashflow: bool = True
    max_debt_growth: Optional[float] = 0.30  # "zadluzenie nie rosnie mocno": < +30% r/r
    net_profit_metric: str = "IncomeNetProfit"
    cashflow_metric: str = "CashflowOperatingCashflow"
    debt_metric: str = "BalanceNoncurrentLiabilities"


@dataclass
class Position:
    ticker: str
    entry_date: pd.Timestamp
    entry_price: float
    shares: float


@dataclass
class Trade:
    ticker: str
    entry_date: pd.Timestamp
    entry_price: float
    exit_date: pd.Timestamp
    exit_price: float
    exit_reason: str
    gross_return: float
    holding_days: int


@dataclass
class HealthCheck:
    """Wynik filtra fundamentalnego dla jednej spolki na jedna date - trzymany osobno, zeby
    dalo sie pokazac DLACZEGO spolka zostala odrzucona (a nie tylko ze zostala)."""

    healthy: bool
    reasons: Dict[str, Any] = field(default_factory=dict)


def check_health(panel: FundamentalPanel, ticker: str, as_of: pd.Timestamp, config: StrategyConfig) -> HealthCheck:
    """Filtr "tylko zdrowe firmy" na danych POINT-IN-TIME (patrz `fundamentals.py`).

    Brak danych = NIE zdrowa. To jest swiadomie konserwatywne: gdy nie wiemy, nie kupujemy.
    Traktowanie braku danych jako "OK" wpuszczaloby do portfela spolki w okresie, w ktorym
    strategia realnie nie miala o nich zadnej informacji fundamentalnej."""
    reasons: Dict[str, Any] = {}
    healthy = True

    if config.require_positive_net_profit:
        net_profit_ttm = panel.ttm(ticker, config.net_profit_metric, as_of)
        reasons["net_profit_ttm"] = net_profit_ttm
        if net_profit_ttm is None or net_profit_ttm <= 0:
            healthy = False

    if config.require_positive_cashflow:
        cashflow_ttm = panel.ttm(ticker, config.cashflow_metric, as_of)
        reasons["cashflow_ttm"] = cashflow_ttm
        if cashflow_ttm is None or cashflow_ttm <= 0:
            healthy = False

    if config.max_debt_growth is not None:
        debt_now = panel.latest(ticker, config.debt_metric, as_of)
        debt_before = panel.value_shifted(ticker, config.debt_metric, as_of, shift=4)
        reasons["debt_now"] = debt_now
        reasons["debt_year_ago"] = debt_before
        if debt_now is None or debt_before is None:
            healthy = False
        elif debt_before > 0:
            growth = debt_now / debt_before - 1.0
            reasons["debt_growth"] = growth
            if growth > config.max_debt_growth:
                healthy = False
        # debt_before <= 0 (brak/zerowe zadluzenie rok temu): iloraz nie ma sensu, nie karzemy

    return HealthCheck(healthy=healthy, reasons=reasons)


def run_backtest(
    daily_prices: pd.DataFrame,
    drawdown: pd.DataFrame,
    panel: FundamentalPanel,
    decision_dates: List[pd.Timestamp],
    config: StrategyConfig,
    ticker_to_fundamental_key: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Zwraca dict z `equity_curve` (dzienna), `trades`, `decisions` (log co miesiac) i
    `first_decision_date` (pierwsza data, w ktorej sygnal cenowy I fundamenty byly dostepne)."""
    if config.max_positions < 1:
        raise ValueError(f"max_positions musi byc >= 1, dostalem {config.max_positions}.")

    key_of = ticker_to_fundamental_key or {t: t.upper() for t in config.tickers}
    prices = daily_prices[config.tickers].sort_index()
    priced = prices.ffill()
    cost_rate = config.cost_bps / 10000.0

    cash = 1.0
    positions: Dict[str, Position] = {}
    trades: List[Trade] = []
    decisions: List[Dict[str, Any]] = []
    equity_records: List[tuple] = []

    decision_set = set(decision_dates)
    first_decision_date: Optional[pd.Timestamp] = None

    for date in prices.index:
        row_price = priced.loc[date]

        if date in decision_set:
            # --- 1) WYJSCIA (przed wejsciami, zeby zwolniony slot byl uzywalny od razu) ---
            for ticker in list(positions):
                position = positions[ticker]
                price = row_price.get(ticker)
                if price is None or pd.isna(price):
                    continue

                months_held = (date.year - position.entry_date.year) * 12 + (date.month - position.entry_date.month)
                gain = price / position.entry_price - 1.0

                exit_reason = None
                if gain >= config.exit_gain:
                    exit_reason = "target"
                elif months_held >= config.max_holding_months:
                    exit_reason = "timeout"

                if exit_reason is not None:
                    proceeds = position.shares * float(price)
                    cash += proceeds * (1.0 - cost_rate)
                    trades.append(
                        Trade(
                            ticker=ticker,
                            entry_date=position.entry_date,
                            entry_price=position.entry_price,
                            exit_date=date,
                            exit_price=float(price),
                            exit_reason=exit_reason,
                            gross_return=gain,
                            holding_days=(date - position.entry_date).days,
                        )
                    )
                    del positions[ticker]

            # --- 2) KANDYDACI: przeceniony (sygnal cenowy) AND zdrowy (fundamenty PIT) ---
            drawdown_row = drawdown.loc[date] if date in drawdown.index else None
            candidates: List[tuple] = []
            signal_available = False
            health_log: Dict[str, Any] = {}

            for ticker in config.tickers:
                if ticker in positions:
                    continue
                if drawdown_row is None:
                    continue
                dd = drawdown_row.get(ticker)
                if dd is None or pd.isna(dd):
                    continue

                health = check_health(panel, key_of[ticker], date, config)
                health_log[ticker] = {"drawdown": float(dd), "healthy": health.healthy, **health.reasons}

                # "Strategia jest realnie zdolna dzialac" = ma JEDNOCZESNIE sygnal cenowy (pelne
                # 52W okno) I opublikowane fundamenty tej spolki. Sam sygnal cenowy NIE wystarcza:
                # ceny siegaja 1994, a fundamenty zaczynaja sie 2005-2008 (DNP dopiero 2016), wiec
                # liczenie metryk od pierwszej daty z cenami dawaloby kilkanascie lat martwej
                # gotowki i CICHO rozwadnialo CAGR - dokladnie ten sam blad, ktory naprawiono w
                # `engine_v2` dla strategii laczonych (patrz CHANGELOG 2026-08-12 (2)).
                if panel.ttm(key_of[ticker], config.net_profit_metric, date) is not None:
                    signal_available = True

                if dd <= config.min_drawdown and health.healthy:
                    candidates.append((float(dd), ticker))

            if signal_available and first_decision_date is None:
                # Pierwsza data, w ktorej strategia MOGLA cokolwiek zrobic - stad liczymy metryki,
                # zeby nie rozwadniac ich okresem, w ktorym sygnal 52W jeszcze nie istnial.
                first_decision_date = date

            # --- 3) WEJSCIA: najbardziej przecenione pierwsze, equal weight ---
            candidates.sort()  # dd rosnaco = najbardziej przeceniony (najbardziej ujemny) pierwszy
            free_slots = config.max_positions - len(positions)
            if free_slots > 0 and candidates:
                equity_now = cash + sum(p.shares * float(row_price.get(p.ticker, 0.0) or 0.0) for p in positions.values())
                target_size = equity_now / config.max_positions
                for _, ticker in candidates[:free_slots]:
                    price = row_price.get(ticker)
                    if price is None or pd.isna(price) or price <= 0:
                        continue
                    spend = min(target_size, cash)
                    if spend <= 0:
                        break
                    shares = (spend * (1.0 - cost_rate)) / float(price)
                    cash -= spend
                    positions[ticker] = Position(
                        ticker=ticker, entry_date=date, entry_price=float(price), shares=shares
                    )

            decisions.append(
                {
                    "date": date,
                    "n_positions": len(positions),
                    "held": sorted(positions),
                    "candidates": [t for _, t in candidates],
                    "health": health_log,
                }
            )

        # --- wycena dzienna (mark-to-market) ---
        position_value = 0.0
        for position in positions.values():
            price = row_price.get(position.ticker)
            if price is not None and not pd.isna(price):
                position_value += position.shares * float(price)
        equity_records.append((date, cash + position_value))

    equity_curve = pd.DataFrame(equity_records, columns=["date", "equity"])

    return {
        "equity_curve": equity_curve,
        "trades": trades,
        "decisions": decisions,
        "first_decision_date": first_decision_date,
        "open_positions": positions,
    }
