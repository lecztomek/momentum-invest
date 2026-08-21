"""
REVERSAL - sygnal i bramka koncepcji v9 "Large-Cap Overreaction Reversal".

SPEC (user): duze i plynne spolki GPW point-in-time; trigger = zwrot miesieczny <= -20%; filtr
jakosci (rentowna, bez distressu); filtr informacji (odrzucamy spadki po profit warningu, emisji
ratunkowej, problemach z plynnoscia, trwalym zalamaniu wynikow); kupno na poczatku kolejnego
miesiaca; max 4 spolki equal weight; holding 3 / 6 / 12 miesiecy testowany osobno; exit tylko po
holdingu albo przy fundamental fail; przy >4 kandydatach wybieramy NAJWIEKSZE spadki.

BRAMKA - dokladnie osiem warunkow ze spec:

    1. kapital wlasny > 0
    2. zysk netto TTM > 0
    3. CFO TTM > 0
    4. dlug / aktywa < 60%
    5. dlug / aktywa nie wzrosl o wiecej niz 10 pp r/r
    6. przychody TTM nie spadly o wiecej niz 20% r/r
    7. EBIT TTM nie spadl o wiecej niz 40% r/r
    8. liczba akcji nie wzrosla o wiecej niz 10% r/r  (proxy emisji ratunkowej)

CZEGO NIE DA SIE ZROBIC I DLACZEGO - to najwazniejsze zastrzezenie tej koncepcji:

**"Filtr informacji" jest realizowany WYLACZNIE przez powyzsze proxy fundamentalne, bo nie mamy
danych o komunikatach.** W repo nie ma ESPI ani newsow - tylko sprawozdania z BiznesRadaru. Skutek
jest strukturalny, nie techniczny: **raport przychodzi z opoznieniem 35-115 dni** (zmierzone w
`fundamentals.py`), wiec profit warning ogloszony w trakcie miesiaca, ktory wywolal spadek, NIE JEST
jeszcze widoczny w liczbach w momencie zakupu. Bramka odrzuca spadki spolek, ktorych JUZ
OPUBLIKOWANE wyniki sa zle - a nie tych, o ktorych zla wiadomosc wlasnie wyszla. To jest dokladnie
ta czesc spec, ktorej te dane nie potrafia zrealizowac, i wynik trzeba czytac z ta swiadomoscia.

BRAK DANYCH = WARUNEK NIESPELNIONY. Tak samo jak w `scoring.py`: to BRAMKA, nie ranking, wiec
konserwatywnie nie wpuszczamy spolki, o ktorej nie wiemy. Inaczej spolka bez opublikowanych
fundamentow przechodzilaby filtr distressu na samym braku informacji - a przy triggerze "-20% w
miesiac" to wlasnie takie spolki sa najgrozniejsze.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from value_engine.fundamentals import FundamentalPanel

GATE_CONDITIONS = (
    "equity_positive",
    "net_income_positive",
    "cashflow_positive",
    "debt_ratio_below_limit",
    "debt_ratio_not_jumping",
    "revenue_not_collapsing",
    "ebit_not_collapsing",
    "no_rescue_issuance",
)

_DEBT_METRICS = ("BalanceCurrentBorrowings", "BalanceNoncurrentBorrowings")


@dataclass
class GateResult:
    """Wynik bramki z rozbiciem na warunki - zeby dalo sie pokazac, KTORY filtr odrzucil spolke,
    a nie tylko ze odrzucil. To jest glowna diagnostyka tej koncepcji: jesli jakis warunek nie
    odrzuca nigdy, znaczy ze go w praktyce nie ma."""

    passed: Dict[str, bool] = field(default_factory=dict)
    values: Dict[str, Optional[float]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(self.passed.get(name, False) for name in GATE_CONDITIONS)

    def failures(self) -> List[str]:
        return [name for name in GATE_CONDITIONS if not self.passed.get(name, False)]


def _sum_debt(panel: FundamentalPanel, ticker: str, as_of: pd.Timestamp, shift: int = 0) -> Optional[float]:
    values = []
    for metric in _DEBT_METRICS:
        value = (
            panel.latest(ticker, metric, as_of)
            if shift == 0
            else panel.value_shifted(ticker, metric, as_of, shift)
        )
        if value is not None:
            values.append(value)
    return sum(values) if values else None


def evaluate_gate(
    panel: FundamentalPanel,
    ticker: str,
    as_of: pd.Timestamp,
    max_debt_ratio: float = 0.60,
    max_debt_ratio_jump: float = 0.10,
    max_revenue_drop: float = 0.20,
    max_ebit_drop: float = 0.40,
    max_share_issuance: float = 0.10,
) -> GateResult:
    """Osiem warunkow ze spec, wylacznie na danych opublikowanych do `as_of`.

    DLUG = zadluzenie OPROCENTOWANE (`Borrowings` biezace + dlugoterminowe), bez leasingu - ta sama
    definicja co w calym module (uzasadnienie IFRS 16 w `scoring.py`). Przy tej definicji prog 60%
    jest luzny; raport z backtestu pokazuje, ile razy kazdy warunek realnie odrzucil spolke, zeby
    bylo widac, ktore filtry cokolwiek robia.

    LICZBA AKCJI mierzona `BalanceShareCapital` (kapital zakladowy), bo BiznesRadar podaje liczbe
    akcji tylko jako wartosc DZISIEJSZA. Kapital zakladowy rosnie przy emisji, a **split go nie
    zmienia** - wiec jako proxy emisji ratunkowej jest lepszy niz liczba akcji."""
    equity = panel.latest(ticker, "BalanceCapital", as_of)
    net_income = panel.ttm(ticker, "IncomeNetProfit", as_of)
    cashflow = panel.ttm(ticker, "CashflowOperatingCashflow", as_of)
    assets = panel.latest(ticker, "BalanceTotalAssets", as_of)
    assets_before = panel.value_shifted(ticker, "BalanceTotalAssets", as_of, shift=4)
    debt = _sum_debt(panel, ticker, as_of)
    debt_before = _sum_debt(panel, ticker, as_of, shift=4)
    revenue = panel.ttm(ticker, "IncomeRevenues", as_of)
    revenue_before = panel.ttm_shifted(ticker, "IncomeRevenues", as_of)
    ebit = panel.ttm(ticker, "IncomeEBIT", as_of)
    ebit_before = panel.ttm_shifted(ticker, "IncomeEBIT", as_of)
    share_capital = panel.latest(ticker, "BalanceShareCapital", as_of)
    share_capital_before = panel.value_shifted(ticker, "BalanceShareCapital", as_of, shift=4)

    debt_ratio = debt / assets if debt is not None and assets not in (None, 0) else None
    debt_ratio_before = (
        debt_before / assets_before
        if debt_before is not None and assets_before not in (None, 0)
        else None
    )

    passed = {
        "equity_positive": equity is not None and equity > 0,
        "net_income_positive": net_income is not None and net_income > 0,
        "cashflow_positive": cashflow is not None and cashflow > 0,
        "debt_ratio_below_limit": debt_ratio is not None and debt_ratio < max_debt_ratio,
        "debt_ratio_not_jumping": (
            debt_ratio is not None
            and debt_ratio_before is not None
            and debt_ratio - debt_ratio_before <= max_debt_ratio_jump
        ),
        # "nie spadlo wiecej niz 20%" przy UJEMNEJ bazie nie ma sensu, wiec baza <= 0 = warunek
        # niespelniony (spolka, ktora rok temu miala ujemne przychody/EBIT, nie jest "zdrowa").
        "revenue_not_collapsing": (
            revenue is not None
            and revenue_before is not None
            and revenue_before > 0
            and revenue / revenue_before - 1.0 >= -max_revenue_drop
        ),
        "ebit_not_collapsing": (
            ebit is not None
            and ebit_before is not None
            and ebit_before > 0
            and ebit / ebit_before - 1.0 >= -max_ebit_drop
        ),
        "no_rescue_issuance": (
            share_capital is not None
            and share_capital_before is not None
            and share_capital_before > 0
            and share_capital / share_capital_before - 1.0 <= max_share_issuance
        ),
    }
    values = {
        "equity": equity,
        "net_income_ttm": net_income,
        "cashflow_ttm": cashflow,
        "debt_ratio": debt_ratio,
        "debt_ratio_year_ago": debt_ratio_before,
        "revenue_change": (
            None if revenue is None or not revenue_before else revenue / revenue_before - 1.0
        ),
        "ebit_change": None if ebit is None or not ebit_before else ebit / ebit_before - 1.0,
        "share_capital_change": (
            None
            if share_capital is None or not share_capital_before
            else share_capital / share_capital_before - 1.0
        ),
    }
    return GateResult(passed=passed, values=values)


def monthly_returns(
    prices: pd.DataFrame, decision_dates: Sequence[pd.Timestamp]
) -> Dict[pd.Timestamp, Dict[str, float]]:
    """Zwrot miedzy POPRZEDNIA i BIEZACA data decyzyjna, per spolka.

    Liczony na siatce dat decyzyjnych (pierwsza sesja miesiaca), a nie jako "ostatnie 21 sesji" -
    dzieki temu "spadek miesieczny" jest dokladnie tym, co strategia widzi w momencie decyzji, bez
    nakladania sie okien. Spolka bez ceny na ktorymkolwiek koncu nie ma zwrotu (a nie zwrot 0)."""
    priced = prices.ffill()
    dates = [d for d in decision_dates if d in priced.index]
    out: Dict[pd.Timestamp, Dict[str, float]] = {}
    for previous, current in zip(dates, dates[1:]):
        before, after = priced.loc[previous], priced.loc[current]
        row: Dict[str, float] = {}
        for ticker in priced.columns:
            start, end = before.get(ticker), after.get(ticker)
            if pd.notna(start) and pd.notna(end) and float(start) > 0:
                row[ticker] = float(end) / float(start) - 1.0
        out[current] = row
    return out


def find_candidates(
    returns: Dict[str, float],
    investable: Sequence[str],
    panel: FundamentalPanel,
    as_of: pd.Timestamp,
    trigger: float = -0.20,
    ticker_to_fundamental_key: Optional[Dict[str, str]] = None,
    **gate_kwargs,
) -> Tuple[List[Tuple[str, float]], Dict[str, GateResult], List[str]]:
    """Zwraca `(kandydaci posortowani od NAJWIEKSZEGO spadku, wyniki bramki, tickery z triggerem)`.

    Kolejnosc: najpierw trigger cenowy, potem bramka - i tylko dla tych, ktore przeszly trigger.
    Odwrotna kolejnosc dawalaby te same wyniki, ale liczylaby bramke dla calego uniwersum co
    miesiac bez potrzeby."""
    key_of = ticker_to_fundamental_key or {t: t.upper() for t in investable}
    triggered = [
        ticker for ticker in investable if returns.get(ticker) is not None and returns[ticker] <= trigger
    ]
    gates = {
        ticker: evaluate_gate(panel, key_of[ticker], as_of, **gate_kwargs) for ticker in triggered
    }
    candidates = [(ticker, returns[ticker]) for ticker in triggered if gates[ticker].ok]
    # Przy >4 kandydatach wybieramy NAJWIEKSZE spadki - sortujemy rosnaco po zwrocie.
    candidates.sort(key=lambda pair: pair[1])
    return candidates, gates, triggered
