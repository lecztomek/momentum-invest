"""
Testy DEFENSIVE SCORING - koncepcja v5 (50% QUALITY + 50% LOW_VOL).

Najwazniejsze punkty do pilnowania to KIERUNKI rankingu: dwie z czterech metryk maja odwrotny
kierunek niz intuicyjny ("wiecej = lepiej"), a odwrocenie ich myli caly ranking, nie psujac zadnego
innego testu:
  - `Debt / MarketCap` - NIZEJ = lepiej,
  - zmiennosc              - NIZEJ = lepiej.

Uruchomienie: .venv/bin/pytest value_engine/tests/test_defensive_scoring.py -v
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from value_engine.br_parser import ParsedReport, load_snapshots
from value_engine.defensive_scoring import (
    LOW_VOL_WEIGHT,
    QUALITY_WEIGHT,
    QualityInputs,
    build_scorer,
    compute_quality_inputs,
    realized_volatility,
    score_universe,
)
from value_engine.fundamentals import FundamentalPanel
from value_engine.market_cap import SharesEstimator, load_shares_outstanding
from value_engine.universe import load_industries, non_financial_tickers

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "value_engine" / "biznesradar_raw.sqlite3"
PL_DATA_DIR = REPO_ROOT / "data" / "pl"

_PERIODS = [f"{y}/Q{q} (x)" for y in (2017, 2018) for q in (1, 2, 3, 4)]
_DATES = [
    "2017-05-01", "2017-08-01", "2017-11-01", "2018-01-02",
    "2018-05-01", "2018-08-01", "2018-11-01", "2019-01-01",
]
_AS_OF = pd.Timestamp("2019-06-01")


def _panel(**metrics) -> FundamentalPanel:
    expanded = {
        name: (value if isinstance(value, list) else [value] * 8) for name, value in metrics.items()
    }
    return FundamentalPanel.from_reports(
        [
            ParsedReport(
                ticker="A",
                report_type="mixed",
                periodicity="quarterly",
                periods=_PERIODS,
                publication_dates=_DATES,
                metrics=expanded,
            )
        ]
    )


def _full_panel(net_income=25.0, ebit=40.0, equity=1000.0, debt=200.0, share_capital=1000.0):
    return _panel(
        IncomeNetProfit=net_income,
        IncomeEBIT=ebit,
        BalanceCapital=equity,
        BalanceCurrentBorrowings=debt,
        BalanceNoncurrentBorrowings=0.0,
        BalanceShareCapital=share_capital,
    )


# --- WSKAZNIKI QUALITY ---


def test_roe_and_roic_use_ttm_numerator():
    """ROE = zysk TTM / kapital wlasny (nie kwartalny!). 4 kwartaly x 25 = 100 TTM, kapital 1000
    -> 10%. ROIC = EBIT TTM 160 * (1 - 0.19) / (1000 + 200) = 10.8%."""
    panel = _full_panel()
    estimator = SharesEstimator(panel, {"A": 1_000_000.0})

    inputs = compute_quality_inputs(panel, estimator, "A", price=1.0, as_of=_AS_OF)

    assert inputs.roe == pytest.approx(100.0 / 1000.0)
    assert inputs.roic == pytest.approx(160.0 * 0.81 / 1200.0)
    assert inputs.available() == 3


def test_tax_rate_is_a_parameter_and_only_scales_roic():
    panel = _full_panel()
    estimator = SharesEstimator(panel, {"A": 1_000_000.0})

    default = compute_quality_inputs(panel, estimator, "A", 1.0, _AS_OF)
    no_tax = compute_quality_inputs(panel, estimator, "A", 1.0, _AS_OF, tax_rate=0.0)

    assert no_tax.roic == pytest.approx(default.roic / 0.81)
    assert no_tax.roe == pytest.approx(default.roe)


def test_negative_equity_invalidates_roe_and_roic_instead_of_flipping_sign():
    """DECYZJA nr 2 z docstringu modulu. Spolka po duzych stratach ma ujemny kapital wlasny; przy
    ujemnym mianowniku ROE spolki ZE STRATA wyszloby DODATNIE i wygladalaby na najrentowniejsza
    w rankingu. Lepiej brak wskaznika."""
    panel = _full_panel(net_income=-50.0, equity=-500.0)
    estimator = SharesEstimator(panel, {"A": 1_000_000.0})

    inputs = compute_quality_inputs(panel, estimator, "A", 1.0, _AS_OF)

    assert inputs.roe is None
    assert inputs.roic is None
    # Debt / MarketCap nie zalezy od kapitalu wlasnego, wiec zostaje policzone
    assert inputs.debt_to_market_cap is not None
    assert inputs.available() == 1


def test_debt_to_market_cap_uses_statement_units():
    """Sprawozdania sa w TYSIACACH, kapitalizacja w zlotych - bez przelicznika wskaznik byl by
    1000x za maly i cala metryka bylaby plaska w rankingu."""
    panel = _full_panel(debt=200.0)
    estimator = SharesEstimator(panel, {"A": 1_000_000.0})

    inputs = compute_quality_inputs(panel, estimator, "A", price=1.0, as_of=_AS_OF)

    assert inputs.market_cap == pytest.approx(1_000_000.0)
    assert inputs.debt_to_market_cap == pytest.approx(200 * 1000 / 1_000_000)  # 0.2


def test_debt_sums_current_and_noncurrent_borrowings():
    panel = _panel(
        IncomeNetProfit=25.0, IncomeEBIT=40.0, BalanceCapital=1000.0,
        BalanceCurrentBorrowings=100.0, BalanceNoncurrentBorrowings=300.0,
        BalanceShareCapital=1000.0,
    )
    estimator = SharesEstimator(panel, {"A": 1_000_000.0})

    inputs = compute_quality_inputs(panel, estimator, "A", 1.0, _AS_OF)

    assert inputs.debt_to_market_cap == pytest.approx(400 * 1000 / 1_000_000)


def test_no_market_cap_means_no_debt_ratio():
    panel = _full_panel()
    estimator = SharesEstimator(panel, {})  # brak kotwicy liczby akcji

    inputs = compute_quality_inputs(panel, estimator, "A", 1.0, _AS_OF)

    assert inputs.debt_to_market_cap is None
    assert inputs.roe is not None  # ROE nie potrzebuje kapitalizacji


def test_unpublished_fundamentals_give_nothing():
    panel = _full_panel()
    estimator = SharesEstimator(panel, {"A": 1_000_000.0})

    inputs = compute_quality_inputs(panel, estimator, "A", 1.0, pd.Timestamp("2017-01-01"))

    assert inputs.available() == 0


# --- ZMIENNOSC ---


def _prices(**series) -> pd.DataFrame:
    length = max(len(v) for v in series.values())
    index = pd.bdate_range("2015-01-01", periods=length)
    return pd.DataFrame({k: v for k, v in series.items()}, index=index)


def test_volatility_is_annualized():
    """Deterministyczna kontrola skali: zwroty +/-1% naprzemiennie. Odchylenie standardowe dziennych
    zwrotow razy sqrt(252) musi wyjsc ~16%, a nie ~1% (brak anualizacji) ani ~250% (podwojna)."""
    values = [100.0]
    for i in range(300):
        values.append(values[-1] * (1.01 if i % 2 == 0 else 0.99))
    prices = _prices(a=values)

    vol = realized_volatility(prices, prices.index[300], window_days=252)["a"]

    assert 0.13 < vol < 0.20, vol


def test_calm_stock_has_lower_volatility_than_wild_one():
    rng = np.random.default_rng(7)
    calm = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.005, 300)))
    wild = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.030, 300)))
    prices = _prices(calm=list(calm), wild=list(wild))

    vol = realized_volatility(prices, prices.index[299], window_days=252)

    assert vol["calm"] < vol["wild"]


def test_volatility_requires_full_window():
    """Bez tego swiezo notowana spolka dostawala by zmiennosc z kilku dni - a wiec czesto sztucznie
    niska - i LOW_VOL = 100 na starcie."""
    prices = _prices(a=[100.0 + i for i in range(100)])

    assert realized_volatility(prices, prices.index[99], window_days=252)["a"] is None
    assert realized_volatility(prices, prices.index[99], window_days=50)["a"] is not None


def test_volatility_window_ends_on_decision_day_inclusive():
    """Dzienna cena z dnia decyzyjnego JEST znana w dniu decyzyjnym, wiec okno moze sie na niej
    konczyc (inaczej niz kanarek, ktory operuje na zamknieciach miesiecznych)."""
    values = [100.0] * 260 + [100.0]
    values[-1] = 150.0  # skok wylacznie w dniu decyzyjnym
    prices = _prices(a=values)

    without_jump = realized_volatility(prices, prices.index[259], window_days=252)["a"]
    with_jump = realized_volatility(prices, prices.index[260], window_days=252)["a"]

    assert without_jump is None  # 260 sesji stalej ceny -> zerowe odchylenie
    assert with_jump is not None and with_jump > 0


def test_constant_price_is_excluded_not_treated_as_safest():
    prices = _prices(a=[100.0] * 300)

    assert realized_volatility(prices, prices.index[299], window_days=252)["a"] is None


def test_missing_date_returns_no_volatility():
    prices = _prices(a=[100.0 + i for i in range(300)])

    assert realized_volatility(prices, pd.Timestamp("2099-01-01"), window_days=252)["a"] is None


# --- SKLADANIE SCORE ---


def _quality(roe=0.10, roic=0.10, debt=0.5) -> QualityInputs:
    return QualityInputs(roe=roe, roic=roic, debt_to_market_cap=debt, market_cap=1.0)


def test_final_score_uses_spec_weights():
    scored = score_universe(
        ["dobra", "slaba"],
        quality_inputs={"dobra": _quality(0.30, 0.30, 0.1), "slaba": _quality(0.01, 0.01, 5.0)},
        vol_6m={"dobra": 0.15, "slaba": 0.60},
        vol_12m={"dobra": 0.15, "slaba": 0.60},
    )
    best = scored[0]

    assert QUALITY_WEIGHT + LOW_VOL_WEIGHT == pytest.approx(1.0)
    assert best.ticker == "dobra"
    assert best.quality == pytest.approx(100.0)
    assert best.low_vol == pytest.approx(100.0)
    assert best.final == pytest.approx(100.0)


def test_lower_debt_to_market_cap_scores_higher():
    """ODWROTNY KIERUNEK #1. Gdyby percentyl liczyl sie "wiecej = lepiej", najbardziej zadluzona
    spolka wygrywalaby ranking Quality."""
    scored = score_universe(
        ["male_dlugi", "duze_dlugi"],
        quality_inputs={"male_dlugi": _quality(debt=0.1), "duze_dlugi": _quality(debt=3.0)},
        vol_6m={"male_dlugi": 0.2, "duze_dlugi": 0.2},
        vol_12m={"male_dlugi": 0.2, "duze_dlugi": 0.2},
    )
    by_ticker = {s.ticker: s for s in scored}

    assert by_ticker["male_dlugi"].components["debt_to_market_cap"] == 100.0
    assert by_ticker["duze_dlugi"].components["debt_to_market_cap"] == 50.0
    assert by_ticker["male_dlugi"].quality > by_ticker["duze_dlugi"].quality


def test_lower_volatility_scores_higher():
    """ODWROTNY KIERUNEK #2 - rdzen calej koncepcji "defensive"."""
    scored = score_universe(
        ["spokojna", "dzika"],
        quality_inputs={"spokojna": _quality(), "dzika": _quality()},
        vol_6m={"spokojna": 0.10, "dzika": 0.80},
        vol_12m={"spokojna": 0.10, "dzika": 0.80},
    )

    assert [s.ticker for s in scored] == ["spokojna", "dzika"]
    assert scored[0].low_vol > scored[1].low_vol


def test_volatility_is_average_of_6m_and_12m():
    """Spec: `VOL = srednia(vol_6m, vol_12m)`. Test rozdziela te dwa okna: spolka spokojna w 6M ale
    dzika w 12M nie moze wygladac na defensywna."""
    scored = score_universe(
        ["mieszana", "stabilna"],
        quality_inputs={"mieszana": _quality(), "stabilna": _quality()},
        vol_6m={"mieszana": 0.10, "stabilna": 0.25},
        vol_12m={"mieszana": 0.90, "stabilna": 0.25},
    )
    by_ticker = {s.ticker: s for s in scored}

    assert by_ticker["mieszana"].volatility == pytest.approx(0.50)
    assert by_ticker["stabilna"].volatility == pytest.approx(0.25)
    assert by_ticker["stabilna"].low_vol > by_ticker["mieszana"].low_vol


def test_company_without_both_volatility_windows_is_excluded():
    scored = score_universe(
        ["pelna", "bez_12m"],
        quality_inputs={"pelna": _quality(), "bez_12m": _quality()},
        vol_6m={"pelna": 0.2, "bez_12m": 0.2},
        vol_12m={"pelna": 0.2, "bez_12m": None},
    )

    assert [s.ticker for s in scored] == ["pelna"]


def test_company_with_too_few_quality_metrics_is_excluded():
    """Spolka z jedna metryka mialaby QUALITY liczony z innej podstawy niz reszta - percentyl 100
    z jednego wskaznika nie znaczy tego samego co srednia trzech."""
    scored = score_universe(
        ["pelna", "kaleka"],
        quality_inputs={"pelna": _quality(), "kaleka": QualityInputs(roe=0.5)},
        vol_6m={"pelna": 0.2, "kaleka": 0.2},
        vol_12m={"pelna": 0.2, "kaleka": 0.2},
        min_quality_metrics=2,
    )

    assert [s.ticker for s in scored] == ["pelna"]


def test_quality_averages_only_available_metrics():
    """Spolka z 2 z 3 metryk (progiem `min_quality_metrics`) dostaje srednia z TYCH dwoch, a nie
    sume podzielona przez 3 - inaczej brak danych byl by karany jak zerowy percentyl."""
    scored = score_universe(
        ["dwie", "trzy"],
        quality_inputs={"dwie": QualityInputs(roe=0.5, roic=0.5), "trzy": _quality(0.5, 0.5, 0.5)},
        vol_6m={"dwie": 0.2, "trzy": 0.2},
        vol_12m={"dwie": 0.2, "trzy": 0.2},
        min_quality_metrics=2,
    )
    by_ticker = {s.ticker: s for s in scored}

    assert set(by_ticker["dwie"].components) == {"roe", "roic"}
    assert by_ticker["dwie"].quality == pytest.approx(
        sum(by_ticker["dwie"].components.values()) / 2
    )


def test_scored_list_is_sorted_descending():
    scored = score_universe(
        ["a", "b", "c"],
        quality_inputs={t: _quality(roe=v) for t, v in [("a", 0.1), ("b", 0.3), ("c", 0.2)]},
        vol_6m={"a": 0.3, "b": 0.2, "c": 0.1},
        vol_12m={"a": 0.3, "b": 0.2, "c": 0.1},
    )

    assert [s.final for s in scored] == sorted([s.final for s in scored], reverse=True)


def test_empty_universe_gives_empty_ranking():
    assert score_universe([], {}, {}, {}) == []


# --- INTEGRACJA: scorer w formacie silnika ---


def test_build_scorer_matches_engine_signature():
    """`build_scorer` musi zwracac dokladnie to, czego oczekuje `run_factor_backtest(scorer=...)`:
    liste malejaco po `.final`, z polem `.ticker`. Dzieki temu v5 uzywa mechaniki slotow v4."""
    panel = _full_panel()
    estimator = SharesEstimator(panel, {"A": 1_000_000.0})
    index = pd.bdate_range("2018-01-01", periods=400)
    rng = np.random.default_rng(3)
    prices = pd.DataFrame(
        {
            "a": 100.0 * np.exp(np.cumsum(rng.normal(0, 0.005, 400))),
            "b": 100.0 * np.exp(np.cumsum(rng.normal(0, 0.030, 400))),
        },
        index=index,
    )
    # obie spolki maja te same fundamenty (jeden panel), wiec decyduje LOW_VOL
    scorer = build_scorer(panel, estimator, ticker_to_fundamental_key={"a": "A", "b": "A"})

    scored = scorer(index[399], ["a", "b"], prices)

    assert [s.ticker for s in scored] == ["a", "b"]
    assert all(hasattr(s, "final") for s in scored)


# --- na prawdziwych danych ---


def test_real_data_quality_metrics_are_in_plausible_ranges():
    """Kontrola zdrowia rozsadku na realnych spolkach. Blad w jednostkach (tysiace vs zlote) albo w
    mianowniku przesuwa CALY rozklad, wiec test patrzy na MEDIANE, a nie na kazda wartosc osobno.

    DLACZEGO NIE PROG NA KAZDEJ SPOLCE: w szerszym uniwersum sa realne skrajnosci, ktore NIE sa
    bledem parsera (sprawdzone recznie na surowych szeregach):
      - **ATT** (Grupa Azoty): kapital wlasny scisniety do 348 mln przy stracie TTM 5.0 mld, wiec
        ROE = **-1444%** jest arytmetycznie poprawne dla spolki na granicy wyplacalnosci,
      - **SNT** (Synektik): rok obrotowy konczy sie we WRZESNIU, a w 2026/Q2 byl jednorazowy zysk
        296 mln przy EBIT 54 mln - ROE 244% tez jest prawdziwe.
    Percentylowy ranking jest na to odporny (liczy sie KOLEJNOSC, nie wielkosc), wiec te wartosci
    nie psuja scoringu - ale unieważnialy poprzedni, ciasny prog +/-150%."""
    if not DB_PATH.exists():
        pytest.skip("Brak bazy")
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY

    panel = FundamentalPanel.from_reports(load_snapshots(DB_PATH))
    shares = load_shares_outstanding(DB_PATH)
    estimator = SharesEstimator(panel, shares)
    tickers = non_financial_tickers(sorted(shares), load_industries(DB_PATH))
    prices = LOADER_REGISTRY["stooq_csv"](
        [t.lower() for t in tickers],
        {"data_dir": str(PL_DATA_DIR), "frequency": "daily"},
    ).prices
    as_of = pd.Timestamp("2026-08-01")

    roe_values, debt_values = [], []
    for ticker in tickers:
        series = prices[ticker.lower()][prices.index <= as_of].dropna()
        if series.empty:
            continue
        inputs = compute_quality_inputs(panel, estimator, ticker, float(series.iloc[-1]), as_of)
        if inputs.roe is not None:
            roe_values.append(inputs.roe)
        if inputs.debt_to_market_cap is not None:
            debt_values.append(inputs.debt_to_market_cap)

    assert len(roe_values) >= 15
    assert len(debt_values) >= 15

    # Typowa duza spolka GPW: ROE kilka-kilkanascie procent, dlug rzedu kilkudziesieciu procent
    # kapitalizacji. Blad jednostek (x1000) albo pomyleniu mianownika przesuwa mediane o rzedy
    # wielkosci, wiec to te progi lapia realny blad.
    roe_median = float(pd.Series(roe_values).median())
    debt_median = float(pd.Series(debt_values).median())
    assert 0.0 < roe_median < 0.40, f"mediana ROE = {roe_median:.2%}"
    assert 0.0 <= debt_median < 1.0, f"mediana Debt/MarketCap = {debt_median:.2f}"

    # Luzny bezpiecznik na skrajnosciach: x1000 dalo by tysiace, nie dziesiatki.
    for value in roe_values:
        assert -50.0 < value < 50.0, f"ROE = {value:.2%}"
    for value in debt_values:
        assert 0.0 <= value < 100.0, f"Debt/MarketCap = {value:.2f}"


def test_real_data_volatility_is_in_plausible_ranges():
    """Roczna zmiennosc duzej spolki GPW to typowo 20-60%; ponizej 5% albo powyzej 300% oznacza
    blad (np. brak anualizacji albo liczenie na cenach zamiast na zwrotach)."""
    if not PL_DATA_DIR.exists():
        pytest.skip("Brak danych PL")
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY

    tickers = ["dnp", "kgh", "pkn", "cdr", "opl"]
    prices = LOADER_REGISTRY["stooq_csv"](
        tickers, {"data_dir": str(PL_DATA_DIR), "frequency": "daily"}
    ).prices
    date = prices.index[prices.index <= pd.Timestamp("2026-08-01")][-1]

    vol = realized_volatility(prices.ffill(), date, window_days=252)
    present = {t: v for t, v in vol.items() if v is not None}

    assert len(present) == len(tickers)
    for ticker, value in present.items():
        assert 0.05 < value < 3.0, f"{ticker}: zmiennosc {value:.1%}"


def test_real_data_financials_are_excluded():
    """Dla banku/windykatora `Debt/MarketCap` mierzy skale biznesu, nie ryzyko, wiec spec mowi "na
    poczatek non-financials".

    Test sprawdza WLASNOSC, nie konkretna liste: kazda odsiana spolka musi miec branze z
    `FINANCIAL_INDUSTRIES`, a zadna pozostawiona nie moze. Wczesniej byla tu zaszyta lista `{"KRU"}`
    (jedyna finansowa przy 41 spolkach) - przy 403 spolkach jest ich 31 i taki test lamalby sie przy
    kazdym poszerzeniu danych, nic przy tym nie sprawdzajac."""
    if not DB_PATH.exists():
        pytest.skip("Brak bazy")
    from value_engine.universe import FINANCIAL_INDUSTRIES, _normalize

    industries = load_industries(DB_PATH)
    all_tickers = sorted(industries)
    blocked = {_normalize(name) for name in FINANCIAL_INDUSTRIES}

    kept = non_financial_tickers(all_tickers, industries)
    dropped = set(all_tickers) - set(kept)

    assert dropped, "przy tym zbiorze musi byc co najmniej jedna spolka finansowa"
    for ticker in dropped:
        assert _normalize(industries[ticker]) in blocked, f"{ticker}: {industries[ticker]}"
    for ticker in kept:
        assert _normalize(industries.get(ticker, "")) not in blocked, ticker
    # banki musza byc wsrod odsianych - kontrola, ze lista branz w ogole cos lapie
    assert any(_normalize(industries[t]) == "banki" for t in dropped)
