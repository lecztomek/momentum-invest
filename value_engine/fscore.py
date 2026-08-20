"""
F-SCORE - klasyczny Piotroski F-Score 0-9 na danych ROCZNYCH point-in-time (koncepcja v7).

SPEC (user, odtworzenie polskiego badania):
  - uniwersum: spolki NIEfinansowe
  - raz w roku wybieramy **20% spolek z najwyzszym Book-to-Market**
  - dla nich liczymy F-Score 0-9
  - kupujemy tylko **F-Score 8-9**, equal weight, holding **12 miesiecy**
  - dane z roku `t` uzywane dopiero **6 miesiecy po koncu roku** (dane za 2020 -> portfel od
    1.07.2021 do 30.06.2022)

DZIEWIEC SYGNALOW (podzial Piotroskiego na trzy grupy):

    RENTOWNOSC
      1. ROA > 0                      zysk netto / aktywa (na poczatku roku)
      2. CFO > 0                      przeplywy operacyjne / aktywa
      3. dROA > 0                     ROA lepszy niz rok wczesniej
      4. ACCRUAL                      CFO/aktywa > ROA (zysk pokryty gotowka)

    DZWIGNIA / PLYNNOSC / ZRODLA FINANSOWANIA
      5. dLEVER < 0                   dlug dlugoterminowy / aktywa spada
      6. dLIQUID > 0                  current ratio rosnie
      7. EQ_OFFER                     BRAK emisji nowych akcji

    EFEKTYWNOSC OPERACYJNA
      8. dMARGIN > 0                  marza brutto rosnie
      9. dTURN > 0                    rotacja aktywow rosnie

DECYZJE, KTORYCH SPEC NIE PRZESADZAL (i dlaczego takie):

1. **Mianownik ROA/CFO to aktywa na POCZATKU roku** (czyli z konca roku t-1), tak jak u
   Piotroskiego. Uzycie aktywow na koniec roku zawyzalo by ROA spolkom, ktore skurczyly bilans.

2. **Brak emisji akcji sprawdzamy `BalanceShareCapital`** (kapital zakladowy), a nie liczba akcji -
   BiznesRadar podaje liczbe akcji TYLKO jako wartosc dzisiejsza (patrz `market_cap.py`). Kapital
   zakladowy jest szeregiem czasowym i rosnie dokladnie przy emisji. **Split go NIE zmienia** (rosnie
   liczba akcji, spada nominal), wiec nie daje falszywego alarmu - to wazna zaleta tej miary.

3. **Dwa raporty roczne musza byc PO SOBIE** (odstep 300-450 dni miedzy koncami okresow). Osiem z
   dziewieciu sygnalow to zmiana r/r; porownanie z raportem starszym o 2-3 lata nie jest sygnalem
   "poprawia sie r/r". Przy luce zwracamy `None` dla tych sygnalow, a nie 0 - inaczej spolka z luka
   w danych dostawalaby F-Score 1-2 za brak informacji.

4. **Brak sygnalu NIE jest liczony jako 0 punktow** - `score` sumuje spelnione warunki, a
   `available` mowi, ile z 9 dalo sie policzyc. Bramka "F-Score 8-9" wymaga `available == 9`,
   bo inaczej spolka z 7 dostepnymi sygnalami nigdy nie moglaby przejsc, a spolka z 9 dostepnymi
   konkurowalaby z niepelna na innej podstawie. To jest RESTRYKCYJNE i celowo takie: to bramka, nie
   ranking (inaczej niz `quality_scoring.py` w v6, gdzie brak skladnika jest pomijany w sredniej).

5. **Rok obrotowy czytany z etykiety okresu** (`fundamentals.parse_period_end`), nie zakladany na
   31 grudnia - LPP konczy rok w styczniu, SNT we wrzesniu. Regula "+6 miesiecy" liczy sie od
   FAKTYCZNEGO konca roku.

6. **`Book` to kapital wlasny z tego samego raportu rocznego**, a `Market` to kapitalizacja z dnia
   decyzyjnego (`market_cap.SharesEstimator`). Mieszanie ksiegowej wartosci z przeszlosci z biezaca
   cena jest standardem w liczeniu B/M i jest w pelni point-in-time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from value_engine.fundamentals import FundamentalPanel, Observation
from value_engine.scoring import percentile_scores

SIGNALS = (
    "roa_positive",
    "cfo_positive",
    "roa_improving",
    "accrual",
    "leverage_falling",
    "liquidity_rising",
    "no_equity_issuance",
    "margin_rising",
    "turnover_rising",
)

# Odstep miedzy koncami dwoch KOLEJNYCH lat obrotowych. Szeroko, bo spolka moze zmienic dlugosc roku
# obrotowego (realnie: SNT ma w danych rok konczacy sie w pazdzierniku 2018 i we wrzesniu 2019).
MIN_YEAR_GAP_DAYS = 300
MAX_YEAR_GAP_DAYS = 450


@dataclass
class FScore:
    ticker: str
    score: int  # liczba SPELNIONYCH warunkow (0-9)
    available: int  # ile warunkow dalo sie policzyc (0-9)
    passed: Dict[str, bool] = field(default_factory=dict)
    values: Dict[str, Optional[float]] = field(default_factory=dict)
    period_end: Optional[pd.Timestamp] = None
    previous_period_end: Optional[pd.Timestamp] = None
    publication_date: Optional[pd.Timestamp] = None

    @property
    def complete(self) -> bool:
        return self.available == len(SIGNALS)


DEFAULT_MIN_LAG_MONTHS = 6  # regula z paperu: dane za rok t uzywane od 1.07.t+1


def _known_annuals(
    panel: FundamentalPanel, ticker: str, metric: str, as_of: pd.Timestamp, min_lag_months: int
) -> List[Observation]:
    """Raporty roczne spelniajace OBA warunki naraz:

      (a) opublikowane najpozniej `as_of` - to gwarantuje panel point-in-time,
      (b) koniec roku obrotowego co najmniej `min_lag_months` przed `as_of` - to jest DODATKOWA,
          bardziej restrykcyjna regula z polskiego paperu.

    Oba, nie jedno z nich. (b) samo w sobie nie wystarcza, bo spolka moze opublikowac raport
    pozniej niz 6 miesiecy po koncu roku (zmierzone: maksymalne opoznienie w tych danych to 115
    dni, ale nic tego nie gwarantuje). (a) samo w sobie nie odtwarza paperu, bo spolka z rokiem
    obrotowym konczacym sie w kwietniu bylaby uzywana 2 miesiace po koncu roku."""
    cutoff = as_of - pd.DateOffset(months=min_lag_months)
    return [o for o in panel.history(ticker, metric, as_of) if o.period_end <= cutoff]


def _annual_pair(
    panel: FundamentalPanel,
    ticker: str,
    metric: str,
    as_of: pd.Timestamp,
    min_lag_months: int = DEFAULT_MIN_LAG_MONTHS,
) -> Tuple[Optional[Observation], Optional[Observation]]:
    """Dwa najswiezsze raporty roczne dostepne wg reguly `_known_annuals`, o ile sa PO SOBIE
    (patrz decyzja 3). Zwraca (rok t, rok t-1); gdy nie ma pary - (rok t, None)."""
    history = _known_annuals(panel, ticker, metric, as_of, min_lag_months)
    if not history:
        return None, None
    current = history[-1]
    if len(history) < 2:
        return current, None
    previous = history[-2]
    gap = (current.period_end - previous.period_end).days
    if not MIN_YEAR_GAP_DAYS <= gap <= MAX_YEAR_GAP_DAYS:
        return current, None
    return current, previous


def _ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def compute_fscore(
    panel: FundamentalPanel,
    ticker: str,
    as_of: pd.Timestamp,
    min_lag_months: int = DEFAULT_MIN_LAG_MONTHS,
) -> FScore:
    """F-Score z rocznego panelu point-in-time. `panel` MUSI byc zbudowany z raportow ROCZNYCH
    (`FundamentalPanel.from_reports(reports, periodicity="annual")`) - Piotroski jest zdefiniowany
    na danych rocznych, a mieszanie ich z kwartalnymi psuje wszystkie zmiany r/r."""

    def pair(metric: str) -> Tuple[Optional[Observation], Optional[Observation]]:
        return _annual_pair(panel, ticker, metric, as_of, min_lag_months)

    net_income, net_income_prev = pair("IncomeNetProfit")
    cashflow, cashflow_prev = pair("CashflowOperatingCashflow")
    assets, assets_prev = pair("BalanceTotalAssets")
    long_debt, long_debt_prev = pair("BalanceNoncurrentLiabilities")
    current_assets, current_assets_prev = pair("BalanceCurrentAssets")
    current_liabilities, current_liabilities_prev = pair("BalanceCurrentLiabilities")
    share_capital, share_capital_prev = pair("BalanceShareCapital")
    gross_profit, gross_profit_prev = pair("IncomeGrossProfit")
    revenues, revenues_prev = pair("IncomeRevenues")

    def value(observation: Optional[Observation]) -> Optional[float]:
        return None if observation is None else observation.value

    # Mianownik ROA/CFO: aktywa na POCZATKU roku (decyzja 1).
    assets_start = value(assets_prev)
    assets_start_prev = None
    if assets_prev is not None:
        history = _known_annuals(panel, ticker, "BalanceTotalAssets", as_of, min_lag_months)
        if len(history) >= 3:
            two_back = history[-3]
            gap = (assets_prev.period_end - two_back.period_end).days
            if MIN_YEAR_GAP_DAYS <= gap <= MAX_YEAR_GAP_DAYS:
                assets_start_prev = two_back.value

    roa = _ratio(value(net_income), assets_start)
    roa_prev = _ratio(value(net_income_prev), assets_start_prev)
    cfo_to_assets = _ratio(value(cashflow), assets_start)

    leverage = _ratio(value(long_debt), assets_start)
    leverage_prev = _ratio(value(long_debt_prev), assets_start_prev)

    current_ratio = _ratio(value(current_assets), value(current_liabilities))
    current_ratio_prev = _ratio(value(current_assets_prev), value(current_liabilities_prev))

    margin = _ratio(value(gross_profit), value(revenues))
    margin_prev = _ratio(value(gross_profit_prev), value(revenues_prev))

    asset_turnover = _ratio(value(revenues), assets_start)
    asset_turnover_prev = _ratio(value(revenues_prev), assets_start_prev)

    signals: Dict[str, Optional[bool]] = {
        "roa_positive": None if roa is None else roa > 0,
        "cfo_positive": None if cfo_to_assets is None else cfo_to_assets > 0,
        "roa_improving": None if roa is None or roa_prev is None else roa > roa_prev,
        "accrual": None if cfo_to_assets is None or roa is None else cfo_to_assets > roa,
        "leverage_falling": (
            None if leverage is None or leverage_prev is None else leverage < leverage_prev
        ),
        "liquidity_rising": (
            None
            if current_ratio is None or current_ratio_prev is None
            else current_ratio > current_ratio_prev
        ),
        "no_equity_issuance": (
            None
            if value(share_capital) is None or value(share_capital_prev) is None
            else value(share_capital) <= value(share_capital_prev)
        ),
        "margin_rising": None if margin is None or margin_prev is None else margin > margin_prev,
        "turnover_rising": (
            None
            if asset_turnover is None or asset_turnover_prev is None
            else asset_turnover > asset_turnover_prev
        ),
    }

    passed = {name: bool(flag) for name, flag in signals.items() if flag is not None}
    return FScore(
        ticker=ticker,
        score=sum(passed.values()),
        available=len(passed),
        passed=passed,
        values={
            "roa": roa,
            "roa_prev": roa_prev,
            "cfo_to_assets": cfo_to_assets,
            "leverage": leverage,
            "leverage_prev": leverage_prev,
            "current_ratio": current_ratio,
            "current_ratio_prev": current_ratio_prev,
            "margin": margin,
            "margin_prev": margin_prev,
            "asset_turnover": asset_turnover,
            "asset_turnover_prev": asset_turnover_prev,
        },
        period_end=None if net_income is None else net_income.period_end,
        previous_period_end=None if net_income_prev is None else net_income_prev.period_end,
        publication_date=None if net_income is None else net_income.publication_date,
    )


def book_to_market(
    panel: FundamentalPanel,
    ticker: str,
    market_cap: Optional[float],
    as_of: pd.Timestamp,
    statement_unit: float = 1000.0,
    min_lag_months: int = DEFAULT_MIN_LAG_MONTHS,
) -> Optional[float]:
    """B/M = kapital wlasny z ostatniego DOSTEPNEGO raportu rocznego / biezaca kapitalizacja.

    "Dostepny" wg tej samej reguly co F-Score (opublikowany ORAZ rok obrotowy zamkniety co najmniej
    `min_lag_months` wczesniej) - inaczej selekcja B/M widzialaby swiezsze dane niz sam F-Score.

    `statement_unit`: BiznesRadar podaje sprawozdania w TYSIACACH, a kapitalizacje w zlotych."""
    known = _known_annuals(panel, ticker, "BalanceCapital", as_of, min_lag_months)
    book = known[-1].value if known else None
    if book is None or market_cap in (None, 0) or market_cap < 0:
        return None
    return book * statement_unit / market_cap


VALUE_WEIGHT = 0.50
FSCORE_WEIGHT = 0.50


@dataclass
class CombinedScore:
    """Wynik rankingu v8: `FINAL = 50% percentyl(B/M) + 50% percentyl(F-Score)`."""

    ticker: str
    final: float
    value_percentile: float
    fscore_percentile: float
    book_to_market: float
    fscore: int


def combined_scores(
    ratios: Dict[str, float],
    scores: Dict[str, FScore],
    value_weight: float = VALUE_WEIGHT,
    fscore_weight: float = FSCORE_WEIGHT,
    require_complete_fscore: bool = True,
) -> List[CombinedScore]:
    """Ranking malejaco po `final`. Spolka wchodzi, gdy ma DODATNI B/M i F-Score.

    DWIE DECYZJE, KTORYCH SPEC NIE PRZESADZAL:

    1. **F-Score musi byc KOMPLETNY (9/9 dostepnych sygnalow)**, inaczej percentyl mieszalby liczby
       z roznych podstaw: `score=6` z szesciu dostepnych sygnalow to co innego niz `6` z dziewieciu.
       Realny koszt tej restrykcji jest maly - na tych danych 279 z 286 spolko-lat ma pelne 9/9.
    2. **Ujemny B/M (ujemny kapital wlasny) wyklucza spolke**, a nie daje jej najgorszego percentyla.
       Spolka z ujemnym kapitalem nie jest "najdrozsza", jest ta miara niewyceniana - a wrzucenie jej
       na dno rankingu B/M dawaloby jej mimo wszystko szanse na wejscie dzieki wysokiemu F-Score.

    Oba percentyle licza sie "wiecej = lepiej": wyzszy B/M = taniej, wyzszy F-Score = lepsza poprawa
    fundamentow."""
    usable = [
        ticker
        for ticker, ratio in ratios.items()
        if ratio is not None
        and ratio > 0
        and ticker in scores
        and (scores[ticker].complete or not require_complete_fscore)
    ]
    if not usable:
        return []

    value_percentiles = percentile_scores({t: ratios[t] for t in usable}, higher_is_better=True)
    fscore_percentiles = percentile_scores(
        {t: float(scores[t].score) for t in usable}, higher_is_better=True
    )

    out = [
        CombinedScore(
            ticker=ticker,
            final=value_weight * value_percentiles[ticker] + fscore_weight * fscore_percentiles[ticker],
            value_percentile=value_percentiles[ticker],
            fscore_percentile=fscore_percentiles[ticker],
            book_to_market=ratios[ticker],
            fscore=scores[ticker].score,
        )
        for ticker in usable
    ]
    # Przy remisie `final` decyduje wyzszy F-Score, potem wyzszy B/M - deterministycznie.
    out.sort(key=lambda s: (-s.final, -s.fscore, -s.book_to_market))
    return out


def top_book_to_market(
    values: Dict[str, float], fraction: float = 0.20, minimum: int = 1
) -> List[str]:
    """`fraction` spolek o najwyzszym B/M (najtansze ksiegowo). Ujemny B/M (kapital wlasny na
    minusie) jest ODRZUCANY, a nie sortowany - spolka z ujemnym kapitalem nie jest "tania", jest
    niewyceniana ta miara."""
    positive = {ticker: value for ticker, value in values.items() if value is not None and value > 0}
    if not positive:
        return []
    count = max(minimum, round(fraction * len(positive)))
    ordered = sorted(positive, key=lambda t: positive[t], reverse=True)
    return ordered[:count]


def annual_decision_dates(
    trading_days: Sequence[pd.Timestamp], month: int = 7, day: int = 1
) -> List[pd.Timestamp]:
    """Pierwsza sesja od 1 lipca kazdego roku - moment wejscia w portfel wg reguly z paperu
    ("dane za rok t uzywane od 1.07.t+1"). Sama regula opoznienia jest realizowana przez to, ze
    panel point-in-time i tak nie pokaze raportu przed jego publikacja; ta funkcja ustala tylko
    SIATKE dat, w ktorych portfel jest przebudowywany."""
    index = pd.DatetimeIndex(sorted(trading_days))
    out: List[pd.Timestamp] = []
    for year in range(index.min().year, index.max().year + 1):
        target = pd.Timestamp(year=year, month=month, day=day)
        candidates = index[index >= target]
        if len(candidates) and candidates[0] < target + pd.DateOffset(months=1):
            out.append(candidates[0])
    return out
