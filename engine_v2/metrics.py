"""
METRICS - "compute_metrics".

Liczy standardowe metryki wydajnosci z dziennej krzywej equity (BACKTEST ENGINE) + tabeli
FINAL PORTFOLIO (potrzebnej tylko do turnover). Kolejny "mechaniczny" krok jak FINAL PORTFOLIO /
BACKTEST ENGINE - zwykla funkcja, nie registry (nie ma sensownych "wielu implementacji CAGR").

Nazwy kluczy w wyniku odpowiadaja polom `acceptance_spec.Criteria` (bez prefiksu min_/max_), zeby
przyszly VALIDATION mogl je bezposrednio porownac z progami.

Samodzielna implementacja - nie importuje niczego z `engine/` (starego kodu).

Kontrakt: (equity_curve: pd.DataFrame, final_portfolio: pd.DataFrame, params: dict) -> Dict[str, float]

equity_curve: kolumny date, equity (z backtest_engine.daily_equity_curve).
final_portfolio: kolumny date, turnover, ... (z final_portfolio.build_final_portfolio) - potrzebne
                  tylko do annual_turnover.

params:
    trading_days_per_year (int, opcjonalnie, domyslnie 252)
    risk_free_rate (float, opcjonalnie, domyslnie 0.0) - roczna stopa wolna od ryzyka, do Sharpe

UWAGA: `min_pct_positive_rolling_windows` z AcceptanceSpec.Criteria NIE jest tu liczone - wymaga
dodatkowego parametru (dlugosc okna), ktory nie jest jeszcze nigdzie zdefiniowany. Dolaczymy gdy
bedzie realna potrzeba (np. przy budowie VALIDATION).
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd


def _cagr(equity: pd.Series, dates: pd.Series) -> float:
    total_days = (dates.iloc[-1] - dates.iloc[0]).days
    if total_days <= 0:
        return 0.0
    years = total_days / 365.25
    return (equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0


def _max_drawdown(equity: pd.Series) -> float:
    drawdown = equity / equity.cummax() - 1.0
    return float(drawdown.min())


def _sharpe(equity: pd.Series, trading_days_per_year: int, risk_free_rate: float) -> float:
    daily_returns = equity.pct_change().dropna()
    if daily_returns.std() == 0:
        return 0.0
    daily_rf = (1.0 + risk_free_rate) ** (1.0 / trading_days_per_year) - 1.0
    excess = daily_returns - daily_rf
    return float(excess.mean() / daily_returns.std() * (trading_days_per_year ** 0.5))


def _monthly_equity(equity_curve: pd.DataFrame) -> pd.Series:
    series = equity_curve.set_index("date")["equity"]
    return series.resample("ME").last()


def _max_consecutive_negative_months(monthly_returns: pd.Series) -> int:
    longest = current = 0
    for r in monthly_returns:
        current = current + 1 if r < 0 else 0
        longest = max(longest, current)
    return longest


def _max_time_underwater_months(monthly_equity: pd.Series) -> int:
    underwater = monthly_equity < monthly_equity.cummax()
    longest = current = 0
    for flag in underwater:
        current = current + 1 if flag else 0
        longest = max(longest, current)
    return longest


def _annual_turnover(final_portfolio: pd.DataFrame) -> float:
    dates = final_portfolio["date"]
    years = (dates.max() - dates.min()).days / 365.25
    if years <= 0:
        return 0.0
    return float(final_portfolio["turnover"].sum() / years)


def compute_metrics(
    equity_curve: pd.DataFrame, final_portfolio: pd.DataFrame, params: Dict[str, Any]
) -> Dict[str, float]:
    if equity_curve.empty:
        raise ValueError("compute_metrics: pusta equity_curve.")

    trading_days_per_year = int(params.get("trading_days_per_year", 252))
    risk_free_rate = float(params.get("risk_free_rate", 0.0))

    equity_curve = equity_curve.sort_values("date")
    equity = equity_curve["equity"].reset_index(drop=True)
    dates = equity_curve["date"].reset_index(drop=True)

    cagr = _cagr(equity, dates)
    max_drawdown = _max_drawdown(equity)
    sharpe = _sharpe(equity, trading_days_per_year, risk_free_rate)
    calmar = cagr / abs(max_drawdown) if max_drawdown != 0 else float("inf")

    monthly_equity = _monthly_equity(equity_curve)
    monthly_returns = monthly_equity.pct_change().dropna()

    return {
        "cagr": cagr,
        "max_drawdown": max_drawdown,
        "sharpe": sharpe,
        "calmar": calmar,
        "annual_turnover": _annual_turnover(final_portfolio),
        "max_consecutive_negative_months": _max_consecutive_negative_months(monthly_returns),
        "max_time_underwater_months": _max_time_underwater_months(monthly_equity),
    }
