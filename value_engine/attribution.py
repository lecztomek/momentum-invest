"""
ATTRIBUTION - co LACZY spolki, ktore rosly? Badanie przekrojowe, NIE strategia.

User: "zawsze podawalem reguly i testowalismy strategie a moze trzeba zrobic research co maja
wspolnego fundamentalnie spolki ktore rosly w danym okresie".

To odwrocenie kierunku: dotad braliśmy regule i mierzyliśmy jej wynik. Tu bierzemy WYNIK (zwrot w
okresie) i pytamy, czym te spolki rozniły sie od reszty. Modul liczy dwie rozne rzeczy i mieszanie
ich jest najlatwiejszym sposobem oszukania samego siebie:

**(A) CECHY EX-ANTE** - jakie wskazniki mialy te spolki na POCZATKU okresu, czyli z raportow
publicznie znanych PRZED wzrostem. To jedyna czesc, ktora ma znaczenie dla strategii: gdyby jakas
cecha ex-ante systematycznie oddzielala zwyciezcow, dalaby sie handlowac. Mierzone przekrojowym
**IC (Information Coefficient)** = korelacja rangowa Spearmana miedzy cecha a zwrotem forward, liczona
OSOBNO w kazdym okresie. Interesuje nas nie jedno IC, a ROZKLAD IC po okresach: sredni poziom,
odsetek okresow z tym samym znakiem i t-stat. Cecha, ktora dziala w polowie okresow, jest bezuzyteczna
niezaleznie od tego, jak wysokie IC ma na calej probce.

**(B) CO SIE STALO W TRAKCIE** - jak zmienily sie fundamenty W OKRESIE wzrostu. Ta czesc jest z
definicji obciazona wiedza o przyszlosci i **nie da sie jej handlowac** - ale odpowiada na pytanie,
ktorego cala reszta repo nie zadala: czy cena na GPW w ogole chodzi za fundamentami. Zwrot rozkladamy
na trzy skladniki (dekompozycja zwrotu):

    (1 + zwrot_ceny) ~ (1 + wzrost_zysku) * (1 + zmiana_mnoznika) / (1 + rozwodnienie)

Jesli zwyciezcy rosli glownie przez WZROST ZYSKU, to sygnal do szukania jest sygnalem wzrostowym
(ktorego nie testowalismy w zadnej z koncepcji v2-v8). Jesli glownie przez ZMIANE MNOZNIKA
(re-rating), to zaden screen fundamentalny nie mial szans ich znalezc, bo w momencie decyzji nie bylo
tego w liczbach.

WSZYSTKIE CECHY EX-ANTE SA POINT-IN-TIME (panel filtruje po dacie publikacji). Zwroty forward sa
oczywiscie z przyszlosci - o to w tym badaniu chodzi.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from value_engine.fscore import compute_fscore
from value_engine.fundamentals import FundamentalPanel
from value_engine.market_cap import SharesEstimator

_STATEMENT_UNIT = 1000.0  # sprawozdania w tysiacach, kapitalizacja w zlotych
DEFAULT_TAX_RATE = 0.19

# Kolejnosc = kolejnosc w raportach. Klucz -> czy WYZSZA wartosc jest "lepsza" wg klasycznej teorii;
# sluzy tylko do czytania tabel, nie wchodzi do zadnego rankingu.
EX_ANTE_FEATURES: Dict[str, str] = {
    "log_market_cap": "rozmiar (log kapitalizacji)",
    "earnings_yield": "E/P - zysk TTM / kapitalizacja",
    "book_to_price": "B/P - kapital wlasny / kapitalizacja",
    "sales_to_price": "S/P - przychody TTM / kapitalizacja",
    "fcf_yield": "FCF/kapitalizacja",
    "roe": "ROE TTM",
    "roa": "ROA TTM",
    "roic": "ROIC TTM",
    "ebit_margin": "marza EBIT TTM",
    "cfo_to_assets": "CFO TTM / aktywa",
    "accruals": "(zysk - CFO) / aktywa",
    "debt_to_assets": "dlug oprocentowany / aktywa",
    "current_ratio": "aktywa obrotowe / zobowiazania biezace",
    "revenue_growth": "wzrost przychodow TTM r/r",
    "ebit_growth": "wzrost EBIT TTM r/r",
    "earnings_growth": "wzrost zysku TTM r/r",
    "share_capital_growth": "wzrost kapitalu zakladowego r/r (emisje)",
    "fscore": "Piotroski F-Score 0-9",
    "momentum_12m": "zwrot ceny za 12M (bez ostatniego miesiaca)",
}


@dataclass
class Features:
    ticker: str
    values: Dict[str, Optional[float]]


def _spearman(left: pd.Series, right: pd.Series) -> float:
    """Korelacja rangowa policzona jako Pearson NA RANGACH. Repo ma tylko pandas i numpy, a
    `Series.corr(method="spearman")` wymaga scipy - nie dokladamy zaleznosci dla jednej formuly.
    Remisy usredniane, tak jak wszedzie w tym module (`rank()` domyslnie robi 'average')."""
    ranked_left, ranked_right = left.rank(), right.rank()
    if ranked_left.std(ddof=0) == 0 or ranked_right.std(ddof=0) == 0:
        return float("nan")
    return float(ranked_left.corr(ranked_right))


def _ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _growth(now: Optional[float], before: Optional[float]) -> Optional[float]:
    """Wzrost r/r. None gdy baza jest <= 0 - wzrost z ujemnego zysku nie ma interpretacji
    ("poprawa ze -100 do -50" to nie -50% ani +50%), a wrzucenie tego do korelacji rangowej
    przesuwalo by cala cecha."""
    if now is None or before is None or before <= 0:
        return None
    return now / before - 1.0


def _sum_debt(panel: FundamentalPanel, ticker: str, as_of: pd.Timestamp) -> Optional[float]:
    values = [
        panel.latest(ticker, metric, as_of)
        for metric in ("BalanceCurrentBorrowings", "BalanceNoncurrentBorrowings")
    ]
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def company_features(
    panel: FundamentalPanel,
    annual_panel: FundamentalPanel,
    estimator: SharesEstimator,
    ticker: str,
    as_of: pd.Timestamp,
    price: Optional[float],
    prices: Optional[pd.DataFrame] = None,
    price_column: Optional[str] = None,
    tax_rate: float = DEFAULT_TAX_RATE,
) -> Features:
    """Wszystkie cechy ex-ante jednej spolki na jedna date, WYLACZNIE z danych opublikowanych do
    `as_of`. `panel` kwartalny (TTM), `annual_panel` tylko do F-Score (Piotroski jest roczny)."""
    market_cap = estimator.market_cap(ticker, price, as_of)
    revenue = panel.ttm(ticker, "IncomeRevenues", as_of)
    revenue_before = panel.ttm_shifted(ticker, "IncomeRevenues", as_of)
    ebit = panel.ttm(ticker, "IncomeEBIT", as_of)
    ebit_before = panel.ttm_shifted(ticker, "IncomeEBIT", as_of)
    net_income = panel.ttm(ticker, "IncomeNetProfit", as_of)
    net_income_before = panel.ttm_shifted(ticker, "IncomeNetProfit", as_of)
    cashflow = panel.ttm(ticker, "CashflowOperatingCashflow", as_of)
    capex = panel.ttm(ticker, "CashflowCapex", as_of)
    assets = panel.latest(ticker, "BalanceTotalAssets", as_of)
    equity = panel.latest(ticker, "BalanceCapital", as_of)
    current_assets = panel.latest(ticker, "BalanceCurrentAssets", as_of)
    current_liabilities = panel.latest(ticker, "BalanceCurrentLiabilities", as_of)
    share_capital = panel.latest(ticker, "BalanceShareCapital", as_of)
    share_capital_before = panel.value_shifted(ticker, "BalanceShareCapital", as_of, shift=4)
    debt = _sum_debt(panel, ticker, as_of)

    equity_usable = equity if equity is not None and equity > 0 else None
    scale = _STATEMENT_UNIT
    free_cash_flow = None if cashflow is None else cashflow + (capex or 0.0)  # capex jest ujemny

    momentum = None
    if prices is not None and price_column is not None and price_column in prices.columns:
        series = prices[price_column]
        history = series[series.index <= as_of].dropna()
        if len(history) >= 273:  # 252 sesje + pominiety ostatni miesiac
            momentum = float(history.iloc[-21] / history.iloc[-273] - 1.0)

    fscore = compute_fscore(annual_panel, ticker, as_of)

    import math

    values: Dict[str, Optional[float]] = {
        "log_market_cap": None if market_cap in (None, 0) else math.log(market_cap),
        "earnings_yield": None if market_cap is None else _ratio(net_income, market_cap / scale),
        "book_to_price": None if market_cap is None else _ratio(equity, market_cap / scale),
        "sales_to_price": None if market_cap is None else _ratio(revenue, market_cap / scale),
        "fcf_yield": None if market_cap is None else _ratio(free_cash_flow, market_cap / scale),
        "roe": _ratio(net_income, equity_usable),
        "roa": _ratio(net_income, assets),
        "roic": (
            None
            if ebit is None or equity_usable is None
            else _ratio(ebit * (1.0 - tax_rate), equity_usable + (debt or 0.0))
        ),
        "ebit_margin": _ratio(ebit, revenue),
        "cfo_to_assets": _ratio(cashflow, assets),
        "accruals": (
            None
            if net_income is None or cashflow is None or assets in (None, 0)
            else (net_income - cashflow) / assets
        ),
        "debt_to_assets": _ratio(debt, assets),
        "current_ratio": _ratio(current_assets, current_liabilities),
        "revenue_growth": _growth(revenue, revenue_before),
        "ebit_growth": _growth(ebit, ebit_before),
        "earnings_growth": _growth(net_income, net_income_before),
        "share_capital_growth": _growth(share_capital, share_capital_before),
        "fscore": float(fscore.score) if fscore.complete else None,
        "momentum_12m": momentum,
    }
    return Features(ticker=ticker, values=values)


def forward_return(
    prices: pd.DataFrame, ticker: str, start: pd.Timestamp, end: pd.Timestamp
) -> Optional[float]:
    """Zwrot ceny miedzy dwiema datami. None, gdy brakuje ktorejkolwiek ceny - spolka bez ceny na
    koncu okresu (delisting, zawieszenie) NIE jest liczona jako 0%, bo nie wiemy, ile bylo warte
    wyjscie. To jest jednoczesnie granica tego badania: **spolek, ktore zniknely, nie ma w danych**."""
    if ticker not in prices.columns:
        return None
    series = prices[ticker].dropna()
    before = series[series.index <= start]
    after = series[series.index <= end]
    if before.empty or after.empty or after.index[-1] <= before.index[-1]:
        return None
    first, last = float(before.iloc[-1]), float(after.iloc[-1])
    return None if first <= 0 else last / first - 1.0


def information_coefficients(
    panels: Tuple[FundamentalPanel, FundamentalPanel],
    estimator: SharesEstimator,
    prices: pd.DataFrame,
    universe: Dict[pd.Timestamp, List[str]],
    horizon_months: int,
    min_companies: int = 10,
    ticker_to_fundamental_key: Optional[Dict[str, str]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Dla kazdej daty w `universe`: liczy cechy ex-ante i zwrot forward na `horizon_months`, a
    potem korelacje rangowa (Spearman) cecha-zwrot W TYM PRZEKROJU.

    Zwraca `(ic_per_date, summary)`. Spearman, nie Pearson: rozklady wskaznikow maja grube ogony
    (E/P przy zysku bliskim zera, wzrost przychodow po akwizycji), a korelacja liniowa mierzylaby
    wtedy glownie jeden outlier."""
    quarterly, annual = panels
    key_of = ticker_to_fundamental_key or {t: t.upper() for t in prices.columns}
    priced = prices.ffill()
    records: List[Dict[str, float]] = []
    sample_sizes: List[Tuple[pd.Timestamp, int]] = []

    for date in sorted(universe):
        investable = universe[date]
        if len(investable) < min_companies:
            continue
        end = date + pd.DateOffset(months=horizon_months)
        if end > prices.index.max():
            continue

        rows = []
        for ticker in investable:
            forward = forward_return(prices, ticker, date, end)
            if forward is None:
                continue
            price = priced.loc[date].get(ticker)
            features = company_features(
                quarterly, annual, estimator, key_of[ticker], date,
                None if pd.isna(price) else float(price),
                prices=priced, price_column=ticker,
            )
            row = dict(features.values)
            row["forward_return"] = forward
            rows.append(row)

        if len(rows) < min_companies:
            continue
        frame = pd.DataFrame(rows)
        sample_sizes.append((date, len(frame)))
        entry: Dict[str, float] = {"date": date, "n": len(frame)}
        for feature in EX_ANTE_FEATURES:
            pair = frame[[feature, "forward_return"]].dropna()
            if len(pair) >= min_companies:
                entry[feature] = _spearman(pair[feature], pair["forward_return"])
        records.append(entry)

    if not records:
        # Brak choc jednego przekroju z wystarczajaca liczba spolek - zwracamy puste ramki, a nie
        # wywalamy sie na `set_index("date")` na pustym DataFrame.
        return pd.DataFrame(), pd.DataFrame()

    ic = pd.DataFrame(records).set_index("date")
    summary_rows = []
    for feature in EX_ANTE_FEATURES:
        if feature not in ic.columns:
            continue
        series = ic[feature].dropna()
        if series.empty:
            continue
        # t-stat sredniego IC (test, czy sredni IC rozni sie od zera) - klasyczne t = mean / (sd/sqrt(n))
        t_stat = series.mean() / (series.std(ddof=1) / (len(series) ** 0.5)) if series.std(ddof=1) else float("nan")
        summary_rows.append(
            {
                "cecha": feature,
                "okresow": len(series),
                "sredni_IC": series.mean(),
                "mediana_IC": series.median(),
                "dodatnich": (series > 0).mean(),
                "t_stat": t_stat,
            }
        )
    summary = pd.DataFrame(summary_rows).set_index("cecha").sort_values("sredni_IC", ascending=False)
    return ic, summary


def decompose_returns(
    quarterly: FundamentalPanel,
    estimator: SharesEstimator,
    prices: pd.DataFrame,
    universe: Dict[pd.Timestamp, List[str]],
    horizon_months: int,
    quantiles: int = 5,
    ticker_to_fundamental_key: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """CZESC (B): dla kazdej spolko-okresu liczy zwrot ceny ORAZ to, co stalo sie z fundamentami W
    TYM SAMYM okresie, a nastepnie grupuje po kwantylach zwrotu.

    Dekompozycja: cena = (zysk / akcje) * mnoznik, wiec
        wzrost ceny = wzrost zysku na akcje * zmiana mnoznika (P/E).
    Liczymy tylko dla spolek z DODATNIM zyskiem na oba konce okresu - inaczej P/E i wzrost zysku sa
    nieokreslone. To zaweza probke i trzeba o tym pamietac przy czytaniu tabeli."""
    key_of = ticker_to_fundamental_key or {t: t.upper() for t in prices.columns}
    priced = prices.ffill()
    rows = []

    for date in sorted(universe):
        end_target = date + pd.DateOffset(months=horizon_months)
        if end_target > prices.index.max():
            continue
        sessions = prices.index[prices.index <= end_target]
        if sessions.empty:
            continue
        end = sessions[-1]

        for ticker in universe[date]:
            price_return = forward_return(prices, ticker, date, end)
            if price_return is None:
                continue
            key = key_of[ticker]
            start_price = priced.loc[date].get(ticker)
            end_price = priced.loc[end].get(ticker)
            earnings_start = quarterly.ttm(key, "IncomeNetProfit", date)
            earnings_end = quarterly.ttm(key, "IncomeNetProfit", end)
            revenue_start = quarterly.ttm(key, "IncomeRevenues", date)
            revenue_end = quarterly.ttm(key, "IncomeRevenues", end)
            shares_start = estimator.implied_shares(key, date)
            shares_end = estimator.implied_shares(key, end)

            row = {"date": date, "ticker": ticker, "price_return": price_return}
            if None not in (earnings_start, earnings_end) and earnings_start > 0 and earnings_end > 0:
                row["earnings_growth"] = earnings_end / earnings_start - 1.0
                if None not in (shares_start, shares_end) and shares_start > 0 and shares_end > 0:
                    row["dilution"] = shares_end / shares_start - 1.0
                    eps_start = earnings_start / shares_start
                    eps_end = earnings_end / shares_end
                    row["eps_growth"] = eps_end / eps_start - 1.0
                    if pd.notna(start_price) and pd.notna(end_price):
                        pe_start = float(start_price) / (eps_start * _STATEMENT_UNIT)
                        pe_end = float(end_price) / (eps_end * _STATEMENT_UNIT)
                        row["multiple_change"] = pe_end / pe_start - 1.0
            if None not in (revenue_start, revenue_end) and revenue_start > 0:
                row["revenue_growth"] = revenue_end / revenue_start - 1.0
            rows.append(row)

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    # Kwantyle liczone W OBREBIE DATY - inaczej porownywalibysmy zwroty z roznych rezimow rynkowych.
    frame["bucket"] = frame.groupby("date")["price_return"].transform(
        lambda s: pd.qcut(s.rank(method="first"), quantiles, labels=False, duplicates="drop") + 1
    )
    return frame
