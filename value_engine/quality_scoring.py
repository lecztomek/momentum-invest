"""
QUALITY SCORING - scoring koncepcji v6 "czysta jakosc". BEZ Value i BEZ Momentum.

User: "Idea: kupujemy najlepsze jakosciowo firmy, nie najtansze."

SKLADNIKI (spec: "ROE / ROIC, CFO / Assets, CFO > Net Income, niski lub nierosnacy dlug"):

    ciagle (percentyl w obrebie uniwersum, 0-100):
        roe            = zysk netto TTM / kapital wlasny                     (wyzej lepiej)
        roic           = EBIT TTM * (1 - podatek) / (dlug + kapital wlasny)  (wyzej lepiej)
        cfo_to_assets  = CFO TTM / aktywa ogolem                             (wyzej lepiej)
        debt_to_assets = dlug oprocentowany / aktywa ogolem                  (NIZEJ lepiej)

    binarne (0 albo 100):
        cfo_ge_net_income  = CFO TTM >= zysk netto TTM
        debt_not_rising    = dlug/aktywa <= dlug/aktywa rok wczesniej

    FINAL = srednia arytmetyczna wszystkich DOSTEPNYCH skladnikow

DECYZJE, KTORYCH SPEC NIE PRZESADZAL:

1. **Mieszanie percentyli z kryteriami binarnymi.** Spec wymienia szesc rzeczy jednym tchem, ale
   cztery z nich sa ciagle, a dwie to warunki "tak/nie". Ciagle ida na percentyle (jak wszedzie w
   tym repo), binarne na 0/100 - dzieki temu wszystkie skladniki sa w tej samej skali i mozna je
   usrednic. Waga: po 1/6 kazdy, wiec kryteria binarne wazą razem 1/3. Alternatywa (binarne jako
   BRAMKA, nie skladnik score) jest inna strategia, nie inne wagi - nie mieszamy tego w jednym
   przebiegu.

2. **"Niski LUB nierosnacy dlug"** - spec daje alternatywe, my liczymy OBA jako osobne skladniki
   (poziom jako percentyl, trend jako flaga). Wybranie tylko jednego wyrzucalo by informacje, ktora
   spec wprost wymienia.

3. **Brak danych = skladnik POMINIETY w sredniej, nie zero.** Inaczej spolka, ktorej BiznesRadar nie
   pokazuje np. przeplywow, dostawalaby kare za brak informacji, a nie za jakosc. Zabezpieczenie
   przed "score z jednego skladnika": `min_components` (domyslnie 4 z 6) - ponizej progu spolka
   wypada z rankingu, bo jej score nie jest porownywalny z reszta.
   UWAGA: to inna konwencja niz `scoring.py` (v2), gdzie brak danych = kryterium NIESPELNIONE. Tam
   QUALITY byl BRAMKA (>= 50 wpuszcza), wiec konserwatywne bylo NIE wpuszczac. Tu QUALITY jest
   RANKINGIEM, wiec konserwatywne jest nie porownywac niepelnych score.

4. **Ujemny kapital wlasny uniewaznia ROE i ROIC** (zwracamy None) - przy ujemnym mianowniku spolka
   z ogromna STRATA wygladalaby na najbardziej rentowna. Tak samo jak w `defensive_scoring.py`.

5. **Dlug BEZ leasingu** - jak wszedzie w tym module. Uzasadnienie IFRS 16 w `scoring.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import pandas as pd

from value_engine.fundamentals import FundamentalPanel
from value_engine.scoring import percentile_scores

DEFAULT_TAX_RATE = 0.19  # CIT w Polsce

CONTINUOUS_METRICS = ("roe", "roic", "cfo_to_assets", "debt_to_assets")
BINARY_CRITERIA = ("cfo_ge_net_income", "debt_not_rising")
COMPONENTS = CONTINUOUS_METRICS + BINARY_CRITERIA
# Jedyna metryka, w ktorej NIZSZA wartosc jest lepsza - odwrocenie kierunku rankingu.
LOWER_IS_BETTER = ("debt_to_assets",)

_DEBT_METRICS = ("BalanceCurrentBorrowings", "BalanceNoncurrentBorrowings")


@dataclass
class QualityInputs:
    """Surowe wskazniki jednej spolki na jedna date. `None` = nie wiemy."""

    roe: Optional[float] = None
    roic: Optional[float] = None
    cfo_to_assets: Optional[float] = None
    debt_to_assets: Optional[float] = None
    cfo_ge_net_income: Optional[bool] = None
    debt_not_rising: Optional[bool] = None

    def available(self) -> int:
        return sum(1 for name in COMPONENTS if getattr(self, name) is not None)


@dataclass
class QualityScore:
    ticker: str
    final: float
    percentile: float  # pozycja w rankingu, 0-100 (100 = najlepsza) - na tym stoi histereza
    inputs: QualityInputs
    components: Dict[str, float] = field(default_factory=dict)


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


def compute_quality_inputs(
    panel: FundamentalPanel,
    ticker: str,
    as_of: pd.Timestamp,
    tax_rate: float = DEFAULT_TAX_RATE,
) -> QualityInputs:
    """Wszystkie szesc skladnikow z danych POINT-IN-TIME (`panel` widzi tylko to, co opublikowano
    do `as_of`). Nie potrzebuje ceny ani kapitalizacji - v6 nie ma czynnika Value."""
    net_income = panel.ttm(ticker, "IncomeNetProfit", as_of)
    cashflow = panel.ttm(ticker, "CashflowOperatingCashflow", as_of)
    ebit = panel.ttm(ticker, "IncomeEBIT", as_of)
    equity = panel.latest(ticker, "BalanceCapital", as_of)
    assets = panel.latest(ticker, "BalanceTotalAssets", as_of)
    assets_before = panel.value_shifted(ticker, "BalanceTotalAssets", as_of, shift=4)
    debt = _sum_debt(panel, ticker, as_of)
    debt_before = _sum_debt(panel, ticker, as_of, shift=4)

    # Ujemny kapital wlasny odwracalby znak - patrz decyzja nr 4 w docstringu modulu.
    equity_usable = equity if equity is not None and equity > 0 else None

    roe = None if net_income is None or equity_usable is None else net_income / equity_usable

    roic = None
    if ebit is not None and equity_usable is not None:
        invested_capital = equity_usable + (debt or 0.0)
        if invested_capital > 0:
            roic = ebit * (1.0 - tax_rate) / invested_capital

    cfo_to_assets = None
    if cashflow is not None and assets not in (None, 0):
        cfo_to_assets = cashflow / assets

    debt_to_assets = None
    if debt is not None and assets not in (None, 0):
        debt_to_assets = debt / assets

    debt_to_assets_before = None
    if debt_before is not None and assets_before not in (None, 0):
        debt_to_assets_before = debt_before / assets_before

    return QualityInputs(
        roe=roe,
        roic=roic,
        cfo_to_assets=cfo_to_assets,
        debt_to_assets=debt_to_assets,
        cfo_ge_net_income=(
            None if cashflow is None or net_income is None else cashflow >= net_income
        ),
        debt_not_rising=(
            None
            if debt_to_assets is None or debt_to_assets_before is None
            else debt_to_assets <= debt_to_assets_before
        ),
    )


def score_universe(
    tickers: Sequence[str],
    inputs: Dict[str, QualityInputs],
    min_components: int = 4,
) -> List[QualityScore]:
    """Ranking malejaco po `final`. `percentile` to pozycja W TYM rankingu (100 = najlepsza) i
    wlasnie na niej stoi histereza v6 ("trzymamy, dopoki nie spadnie ponizej 40-50 percentyla")."""
    usable = [
        ticker
        for ticker in tickers
        if ticker in inputs and inputs[ticker].available() >= min_components
    ]
    if not usable:
        return []

    percentiles: Dict[str, Dict[str, float]] = {}
    for metric in CONTINUOUS_METRICS:
        present = {
            t: getattr(inputs[t], metric) for t in usable if getattr(inputs[t], metric) is not None
        }
        percentiles[metric] = percentile_scores(present, higher_is_better=metric not in LOWER_IS_BETTER)

    scored: List[QualityScore] = []
    for ticker in usable:
        parts = {m: percentiles[m][ticker] for m in CONTINUOUS_METRICS if ticker in percentiles[m]}
        for criterion in BINARY_CRITERIA:
            value = getattr(inputs[ticker], criterion)
            if value is not None:
                parts[criterion] = 100.0 if value else 0.0
        scored.append(
            QualityScore(
                ticker=ticker,
                final=sum(parts.values()) / len(parts),
                percentile=0.0,  # uzupelniane ponizej, gdy znamy caly ranking
                inputs=inputs[ticker],
                components=parts,
            )
        )

    scored.sort(key=lambda s: s.final, reverse=True)
    ranks = percentile_scores({s.ticker: s.final for s in scored}, higher_is_better=True)
    for score in scored:
        score.percentile = ranks[score.ticker]
    return scored
