"""
UK MAPPING - "US decyduje o WSZYSTKIM" replikacja finalnych wag na brytyjskie odpowiedniki ETF.

User: "będzie to ostateczny test - dane dogram za chwilę [...] bardzo prosto - usa decyduje o
wszystkim na uk zwykly mapping". Filozofia: CALA logika (sygnaly, selekcja, wagi, execution,
histereza) liczy sie WYLACZNIE na danych USA (dokladnie ten sam FINAL PORTFOLIO co zawsze) - UK
strona NIE ma wlasnej logiki decyzyjnej, tylko REPLIKUJE juz wyliczone wagi 1:1 na brytyjskie
tickery (ten sam procent kapitalu, inny instrument/gielda/waluta wykonania). Realny test tego,
czy strategia da sie faktycznie wdrozyc na koncie UK (np. XTB) instrumentami dostepnymi tam,
zamiast tylko na papierze na danych USA.

Mechanizm (2 kroki, oba samodzielne funkcje w tym module):

1. `remap_final_portfolio(final_portfolio, ticker_mapping)` - dla kazdego okresu, kazdy
   ticker USA z niezerowa waga jest zastapiony jego odpowiednikiem UK z `ticker_mapping`. Jesli
   dany ticker USA NIE MA mapowania (np. VT w `best17_a` - service jako "signal only", uzywany
   WYLACZNIE jako kanarek/rebound-benchmark, celowo bez brytyjskiego odpowiednika w mapowaniu
   dostarczonym przez usera) - jego waga trafia w `_CASH` zamiast zgadywac zastepczy instrument,
   a ten okres jest oznaczony jako "mismatch" w diagnostyce (nie ukryte, jawnie policzone -
   dokladnie to mierzy `AcceptanceSpec.UkMappingAcceptance.max_weights_mismatch_months_pct`).
   Zwraca (uk_final_portfolio, diagnostics).

2. `compare_us_vs_uk(...)` - liczy METRICS niezaleznie na obu krzywych equity (US i UK, kazda na
   WLASNYCH, dziennych cenach - `daily_equity_curve`/`compute_metrics` bez zmian, uk_final_portfolio
   ma po prostu inne klucze tickerow w `weights_used_json`) i porownuje: korelacje MIESIECZNYCH
   zwrotow (resampling do miesiecznych punktow zamiast probowac dopasowac dokladne dni handlowe -
   kalendarze gield USA/UK sie ROZNIA, wiec dzienne daty nigdy nie beda idealnie wyrownane),
   najwiekszy pojedynczy rozjazd miesieczny, oraz gap CAGR/MaxDD miedzy wersjami.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu). Nie laduje
UK-owych cen samodzielnie - to robi wywolujacy (ten sam `stooq_csv` loader co dla USA, wskazany
na inny `data_dir`, np. "data/uk" - format plikow juz przygotowany identyczny jak "data/us",
patrz docstring `engine_v2/blocks/data_loader/csv_loader.py`).

Kontrakt:
    load_ticker_mapping(path: Path) -> Dict[str, str]
    remap_final_portfolio(final_portfolio: pd.DataFrame, ticker_mapping: Dict[str, str])
        -> Tuple[pd.DataFrame, Dict[str, Any]]
    compare_us_vs_uk(us_final_portfolio, us_equity_curve, uk_final_portfolio, uk_equity_curve)
        -> Dict[str, Any]
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

import pandas as pd

from engine_v2.acceptance_spec import UkMappingAcceptance
from engine_v2.metrics import compute_metrics


def load_ticker_mapping(path: Path) -> Dict[str, str]:
    with Path(path).open("r", encoding="utf-8-sig") as f:
        raw = json.load(f)
    return {str(k).strip().lower(): str(v).strip().lower() for k, v in raw.items()}


def remap_final_portfolio(
    final_portfolio: pd.DataFrame, ticker_mapping: Dict[str, str]
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if final_portfolio.empty:
        raise ValueError("remap_final_portfolio: pusty final_portfolio.")

    remapped_rows = []
    mismatch_dates = []
    unmapped_tickers_used = set()

    for _, row in final_portfolio.iterrows():
        weights = json.loads(row["weights_used_json"])
        new_weights: Dict[str, float] = {}
        row_has_mismatch = False

        for ticker, weight in weights.items():
            if ticker == "_CASH":
                new_weights["_CASH"] = new_weights.get("_CASH", 0.0) + weight
                continue
            if abs(weight) <= 1e-12:
                continue  # zerowa waga - nie ma znaczenia, gdzie "trafia"

            uk_ticker = ticker_mapping.get(ticker)
            if uk_ticker is None:
                new_weights["_CASH"] = new_weights.get("_CASH", 0.0) + weight
                row_has_mismatch = True
                unmapped_tickers_used.add(ticker)
            else:
                new_weights[uk_ticker] = new_weights.get(uk_ticker, 0.0) + weight

        remapped_rows.append(new_weights)
        if row_has_mismatch:
            mismatch_dates.append(row["date"])

    uk_final_portfolio = final_portfolio.copy()
    uk_final_portfolio["weights_used_json"] = [json.dumps(w) for w in remapped_rows]

    total_periods = len(final_portfolio)
    diagnostics = {
        "total_periods": total_periods,
        "mismatch_periods": len(mismatch_dates),
        "mismatch_pct": (len(mismatch_dates) / total_periods) if total_periods else 0.0,
        "mismatch_dates": mismatch_dates,
        "unmapped_tickers_used": sorted(unmapped_tickers_used),
    }
    return uk_final_portfolio, diagnostics


def _monthly_returns(equity_curve: pd.DataFrame) -> pd.Series:
    """Miesieczne punkty (pierwszy dostepny dzien handlowy kazdego miesiaca) -> zwrot okresowy.
    Resampling zamiast probowac dopasowac dokladne dni handlowe - kalendarze gield USA/UK sie
    ROZNIA (inne swieta), wiec dzienne daty final_portfolio nigdy nie beda idealnie wyrownane
    miedzy obiema krzywymi."""
    monthly = equity_curve.set_index("date")["equity"].sort_index().resample("MS").first().dropna()
    return monthly.pct_change().dropna()


def compare_us_vs_uk(
    us_final_portfolio: pd.DataFrame,
    us_equity_curve: pd.DataFrame,
    uk_final_portfolio: pd.DataFrame,
    uk_equity_curve: pd.DataFrame,
) -> Dict[str, Any]:
    us_metrics = compute_metrics(us_equity_curve, us_final_portfolio, {})
    uk_metrics = compute_metrics(uk_equity_curve, uk_final_portfolio, {})

    us_returns = _monthly_returns(us_equity_curve)
    uk_returns = _monthly_returns(uk_equity_curve)
    common = us_returns.index.intersection(uk_returns.index)
    us_common = us_returns.loc[common]
    uk_common = uk_returns.loc[common]

    monthly_return_correlation = float(us_common.corr(uk_common)) if len(common) > 1 else float("nan")
    max_single_month_return_diff = float((us_common - uk_common).abs().max()) if len(common) else float("nan")

    return {
        "us_metrics": us_metrics,
        "uk_metrics": uk_metrics,
        "n_common_months": int(len(common)),
        "monthly_return_correlation": monthly_return_correlation,
        "max_single_month_return_diff": max_single_month_return_diff,
        "cagr_gap": uk_metrics["cagr"] - us_metrics["cagr"],
        "max_drawdown_gap": uk_metrics["max_drawdown"] - us_metrics["max_drawdown"],
    }


def check_uk_mapping_criteria(
    comparison: Dict[str, Any], mismatch_pct: float, criteria: UkMappingAcceptance
) -> Dict[str, bool]:
    """Porownuje wynik `compare_us_vs_uk` (+ `mismatch_pct` z `remap_final_portfolio`) z progami
    `AcceptanceSpec.uk_mapping` - ta sama konwencja co `acceptance_check.check_criteria` (tylko
    faktycznie ustawione, nie-None progi sa sprawdzane). Gap'y CAGR/MaxDD sprawdzane na WARTOSCI
    BEZWZGLEDNEJ - "jak daleko UK odjechalo od US", niezaleznie od kierunku (mapowanie moze
    wypasc lepiej ALBO gorzej niz oryginal, oba sa "rozjazdem" wart odnotowania)."""
    results: Dict[str, bool] = {}

    if criteria.max_weights_mismatch_months_pct is not None:
        results["max_weights_mismatch_months_pct"] = mismatch_pct <= criteria.max_weights_mismatch_months_pct
    if criteria.min_monthly_return_correlation is not None:
        results["min_monthly_return_correlation"] = (
            comparison["monthly_return_correlation"] >= criteria.min_monthly_return_correlation
        )
    if criteria.max_single_month_return_diff is not None:
        results["max_single_month_return_diff"] = (
            comparison["max_single_month_return_diff"] <= criteria.max_single_month_return_diff
        )
    if criteria.max_cagr_gap_vs_us is not None:
        results["max_cagr_gap_vs_us"] = abs(comparison["cagr_gap"]) <= criteria.max_cagr_gap_vs_us
    if criteria.max_drawdown_gap_vs_us is not None:
        results["max_drawdown_gap_vs_us"] = abs(comparison["max_drawdown_gap"]) <= criteria.max_drawdown_gap_vs_us

    return results
