"""
Testy MARKET CAP - odtwarzanie liczby akcji i kapitalizacji point-in-time.

Uruchomienie: .venv/bin/pytest value_engine/tests/test_market_cap.py -v
"""

from pathlib import Path

import pandas as pd
import pytest

from value_engine.br_parser import ParsedReport, load_snapshots
from value_engine.fundamentals import FundamentalPanel
from value_engine.market_cap import (
    SharesEstimator,
    load_reported_market_cap,
    load_shares_outstanding,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "value_engine" / "biznesradar_raw.sqlite3"
PL_DATA_DIR = REPO_ROOT / "data" / "pl"

_PERIODS = [f"{y}/Q{q} (x)" for y in (2017, 2018) for q in (1, 2, 3, 4)]
_DATES = [
    "2017-05-01", "2017-08-01", "2017-11-01", "2018-01-02",
    "2018-05-01", "2018-08-01", "2018-11-01", "2019-01-01",
]


def _panel(share_capital) -> FundamentalPanel:
    values = share_capital if isinstance(share_capital, list) else [share_capital] * 8
    return FundamentalPanel.from_reports(
        [
            ParsedReport(
                ticker="A",
                report_type="balance",
                periodicity="quarterly",
                periods=_PERIODS,
                publication_dates=_DATES,
                metrics={"BalanceShareCapital": values},
            )
        ]
    )


def test_implied_shares_equals_today_when_share_capital_flat():
    # 1 000 tys. PLN kapitalu zakladowego, 1 000 000 akcji -> nominal 1 PLN
    estimator = SharesEstimator(_panel(1000.0), {"A": 1_000_000.0})

    shares = estimator.implied_shares("A", pd.Timestamp("2019-06-01"))

    assert shares == pytest.approx(1_000_000.0)


def test_implied_shares_scales_down_before_issuance():
    """Kapital zakladowy podwoil sie w 2018 -> przed emisja bylo o polowe mniej akcji. Bez tej
    korekty historyczna kapitalizacja bylaby zawyzona 2x, a wiec P/E i P/BV bledne."""
    estimator = SharesEstimator(_panel([500.0] * 4 + [1000.0] * 4), {"A": 1_000_000.0})

    before = estimator.implied_shares("A", pd.Timestamp("2017-12-01"))
    after = estimator.implied_shares("A", pd.Timestamp("2019-06-01"))

    assert before == pytest.approx(500_000.0)
    assert after == pytest.approx(1_000_000.0)


def test_implied_shares_is_point_in_time():
    """Liczba akcji zmienia sie dopiero od DATY PUBLIKACJI raportu, ktory pokazuje nowy kapital."""
    estimator = SharesEstimator(_panel([500.0] * 7 + [1000.0]), {"A": 1_000_000.0})

    assert estimator.implied_shares("A", pd.Timestamp("2018-12-31")) == pytest.approx(500_000.0)
    assert estimator.implied_shares("A", pd.Timestamp("2019-01-01")) == pytest.approx(1_000_000.0)


def test_implied_shares_rejects_implausible_denomination_change():
    """Zmiana wartosci nominalnej (inna niz split) lamie metode. Zamiast zwracac bledna liczbe,
    estimator zwraca None - lepiej nie miec wskaznika niz miec zly. Realny przypadek: dla ALE
    iloraz kapitalu zakladowego najstarszy/najnowszy to 0.024 (40-krotny SPADEK)."""
    estimator = SharesEstimator(_panel([10.0] * 4 + [1000.0] * 4), {"A": 1_000_000.0}, max_shares_ratio_jump=20.0)

    # 100x mniejszy kapital zakladowy -> 100x mniej akcji, poza dopuszczalnym skokiem
    assert estimator.implied_shares("A", pd.Timestamp("2017-12-01")) is None
    assert estimator.implied_shares("A", pd.Timestamp("2019-06-01")) == pytest.approx(1_000_000.0)


def test_market_cap_multiplies_price_by_implied_shares():
    estimator = SharesEstimator(_panel(1000.0), {"A": 1_000_000.0})

    assert estimator.market_cap("A", 25.0, pd.Timestamp("2019-06-01")) == pytest.approx(25_000_000.0)


def test_market_cap_is_none_for_missing_or_invalid_price():
    estimator = SharesEstimator(_panel(1000.0), {"A": 1_000_000.0})
    as_of = pd.Timestamp("2019-06-01")

    assert estimator.market_cap("A", None, as_of) is None
    assert estimator.market_cap("A", 0.0, as_of) is None
    assert estimator.market_cap("A", float("nan"), as_of) is None


def test_market_cap_is_none_for_unknown_ticker():
    estimator = SharesEstimator(_panel(1000.0), {"A": 1_000_000.0})

    assert estimator.market_cap("NIEZNANA", 25.0, pd.Timestamp("2019-06-01")) is None


# --- na prawdziwych danych ---


def _skip_if_no_data():
    if not DB_PATH.exists() or not PL_DATA_DIR.exists():
        pytest.skip("Brak bazy albo data/pl")


def test_real_data_shares_and_market_cap_extracted_for_whole_universe():
    _skip_if_no_data()

    shares = load_shares_outstanding(DB_PATH)
    market_caps = load_reported_market_cap(DB_PATH)

    assert len(shares) >= 20, f"wyciagnieto akcje tylko dla {len(shares)} spolek"
    assert len(market_caps) >= 20
    assert all(value > 0 for value in shares.values())


def test_real_data_shares_match_biznesradar_market_cap():
    """WERYFIKACJA CALEJ METODY na prawdziwych danych: `ostatnia cena * liczba akcji` musi zgadzac
    sie z `Kapitalizacja` podana przez BiznesRadar. Roznica do kilku procent jest oczekiwana
    (strona pobrana 2026-08-19, ostatnie zamkniecie 2026-08-18).

    Ten test zlapal realny blad regexa: wzorzec `Kapitalizacja:.*?<span[^>]*>` przeskakiwal zwykly
    `<td>` i zwracal NASTEPNY wiersz tabeli, czyli Enterprise Value (dla LWB 314 mln zamiast 755
    mln), co dawalo ilorazy od 0.46 do 2.38."""
    _skip_if_no_data()
    from engine_v2.blocks.data_loader import REGISTRY as LOADER_REGISTRY

    shares = load_shares_outstanding(DB_PATH)
    market_caps = load_reported_market_cap(DB_PATH)
    tickers = sorted(set(shares) & set(market_caps))
    prices = LOADER_REGISTRY["stooq_csv"](
        [t.lower() for t in tickers], {"data_dir": str(PL_DATA_DIR), "frequency": "daily"}
    ).prices

    mismatches = []
    for ticker in tickers:
        series = prices[ticker.lower()].dropna()
        if series.empty:
            continue
        computed = shares[ticker] * float(series.iloc[-1])
        ratio = computed / market_caps[ticker]
        if not 0.95 < ratio < 1.05:
            mismatches.append((ticker, round(ratio, 3)))

    assert not mismatches, f"kapitalizacja nie zgadza sie dla: {mismatches}"


def test_real_data_cd_projekt_historical_shares_are_much_lower_than_today():
    """CDR ma dzis ~100 mln akcji, ale kapital zakladowy wzrosl ~10x od 2008 - odtworzona
    historyczna liczba akcji MUSI byc wyraznie mniejsza, inaczej historyczne P/E i P/BV byly by
    zawyzone o rzad wielkosci."""
    _skip_if_no_data()

    panel = FundamentalPanel.from_reports(load_snapshots(DB_PATH))
    shares = load_shares_outstanding(DB_PATH)
    estimator = SharesEstimator(panel, shares)

    old = estimator.implied_shares("CDR", pd.Timestamp("2010-01-01"))
    today = estimator.implied_shares("CDR", pd.Timestamp("2026-08-01"))

    assert old is not None and today is not None
    assert old < today / 3, f"odtworzona liczba akcji CDR w 2010 ({old:,.0f}) vs dzis ({today:,.0f})"
    assert today == pytest.approx(shares["CDR"], rel=0.01)
