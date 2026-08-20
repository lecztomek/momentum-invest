"""
RUN QUALITY VALUE - odpalenie koncepcji "quality value GPW" end-to-end + benchmarki.

  .venv/bin/python3 -m value_engine.run_quality_value
  .venv/bin/python3 -m value_engine.run_quality_value --max-holding-months 36 --show-trades
  .venv/bin/python3 -m value_engine.run_quality_value --sweep

BENCHMARK DO `REL` (relative weakness) jest WTYKOWY:
  - jesli istnieje `data/pl/wig20.txt` (format stooq) - uzywamy WIG20, zgodnie ze spec;
  - w przeciwnym razie fallback: rownowazona srednia calego uniwersum, z JAWNYM ostrzezeniem.
Fallback jest sensownym zamiennikiem (mierzy "slabosc wzgledem swojej grupy"), ale NIE jest tym
samym co WIG20 - stad ostrzezenie w kazdym uruchomieniu, zeby nie zniknelo z wnioskow.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from engine_v2.blocks.data_loader import REGISTRY as DATA_LOADER_REGISTRY
from engine_v2.metrics import compute_metrics
from value_engine.br_parser import load_snapshots
from value_engine.fundamentals import FundamentalPanel
from value_engine.quality_value_backtest import QualityValueConfig, run_quality_value_backtest
from value_engine.signals import month_start_decision_dates

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "value_engine" / "biznesradar_raw.sqlite3"
PL_DATA_DIR = REPO_ROOT / "data" / "pl"
BENCHMARK_TICKER = "wig20"


def discover_tickers() -> List[str]:
    """Uniwersum = wszystkie pliki cen w `data/pl` poza plikiem benchmarku.

    PUSTE PLIKI SA POMIJANE. Przy duzym uniwersum scraper realnie zapisuje pliki zerowej dlugosci
    (zlapane: `rex1.txt`, `rob2.txt`) - spolka bez ani jednej sesji nie jest inwestowalna, a
    `pd.read_csv` wywala sie na niej bledem "No columns to parse from file"."""
    return sorted(
        path.stem
        for path in PL_DATA_DIR.glob("*.txt")
        if path.stem != BENCHMARK_TICKER and path.stat().st_size > 0
    )


def load_prices(tickers: List[str]) -> pd.DataFrame:
    return DATA_LOADER_REGISTRY["stooq_csv"](tickers, {"data_dir": str(PL_DATA_DIR), "frequency": "daily"}).prices


def load_benchmark(prices: pd.DataFrame) -> Tuple[pd.Series, bool]:
    """Zwraca (seria benchmarku, czy to prawdziwy WIG20)."""
    if (PL_DATA_DIR / f"{BENCHMARK_TICKER}.txt").exists():
        series = load_prices([BENCHMARK_TICKER])[BENCHMARK_TICKER]
        return series.reindex(prices.index).ffill(), True

    # fallback: rownowazony indeks z uniwersum (znormalizowany na pierwszej wspolnej dacie)
    normalized = prices / prices.apply(lambda column: column.dropna().iloc[0] if column.notna().any() else pd.NA)
    return normalized.mean(axis=1, skipna=True), False


def build_inputs() -> Tuple[pd.DataFrame, pd.Series, bool, FundamentalPanel, List[pd.Timestamp], List[str]]:
    tickers = discover_tickers()
    prices = load_prices(tickers)
    benchmark, is_real_wig20 = load_benchmark(prices)
    panel = FundamentalPanel.from_reports(load_snapshots(DB_PATH))
    return prices, benchmark, is_real_wig20, panel, month_start_decision_dates(prices), tickers


def metrics_of(equity: pd.Series) -> Dict[str, float]:
    frame = pd.DataFrame({"date": equity.index, "equity": equity.values})
    return compute_metrics(frame, pd.DataFrame({"date": frame["date"], "turnover": 0.0}), {})


def summarize(result: dict, label: str, max_positions: int, verbose: bool = True) -> Optional[Dict[str, float]]:
    equity_curve = result["equity_curve"]
    start = result["first_decision_date"]
    if start is None:
        print(f"{label}: strategia nigdy nie miala kompletnych sygnalow - brak wyniku.")
        return None
    equity_curve = equity_curve[equity_curve["date"] >= start].reset_index(drop=True)
    metrics = metrics_of(pd.Series(equity_curve["equity"].values, index=equity_curve["date"]))

    trades = result["trades"]
    exposure = pd.Series(
        {d["date"]: d["n_positions"] for d in result["decisions"] if d["date"] >= start}
    )
    if verbose:
        wins = [t for t in trades if t.gross_return > 0]
        reasons: Dict[str, int] = {}
        for trade in trades:
            reasons[trade.exit_reason] = reasons.get(trade.exit_reason, 0) + 1
        print(f"\n=== {label} ===")
        print(f"okno: {equity_curve['date'].min().date()} -> {equity_curve['date'].max().date()}")
        print(
            f"CAGR {metrics['cagr']*100:6.2f}%  MaxDD {metrics['max_drawdown']*100:7.2f}%  "
            f"Sharpe {metrics['sharpe']:5.3f}  Calmar {metrics['calmar']:5.3f}"
        )
        avg = sum(t.gross_return for t in trades) / len(trades) if trades else 0.0
        print(
            f"transakcji: {len(trades)}  zyskownych: {len(wins)} ({len(wins)/len(trades)*100 if trades else 0:.0f}%)  "
            f"sredni zwrot: {avg*100:+.2f}%"
        )
        print(
            f"ekspozycja: {exposure.mean():.2f}/{max_positions} pozycji "
            f"({exposure.mean()/max_positions*100:.0f}%)  powody wyjscia: {reasons}"
        )
    metrics["exposure"] = exposure.mean() / max_positions
    metrics["n_trades"] = len(trades)
    return metrics


def benchmark_metrics(prices: pd.DataFrame, start: pd.Timestamp, exposure: float) -> None:
    """Dwa odniesienia: pelny buy&hold uniwersum i buy&hold SKALOWANY do tej samej sredniej
    ekspozycji co strategia (czyli "ta sama ilosc ryzyka, zero timingu i selekcji") - to drugie
    jest najuczciwszym testem, czy sygnal wnosi cokolwiek."""
    window = prices[prices.index >= start]
    normalized = window / window.apply(lambda c: c.dropna().iloc[0] if c.notna().any() else pd.NA)
    equal_weight = normalized.mean(axis=1, skipna=True)
    equal_weight = equal_weight / equal_weight.iloc[0]

    full = metrics_of(equal_weight)
    scaled = metrics_of((1.0 + equal_weight.pct_change().fillna(0.0) * exposure).cumprod())

    print(f"\n{'odniesienie':44} {'CAGR':>8} {'MaxDD':>9} {'Sharpe':>7} {'Calmar':>7}")
    print(f"{'buy&hold uniwersum (100%)':44} {full['cagr']*100:7.2f}% {full['max_drawdown']*100:8.2f}% {full['sharpe']:7.3f} {full['calmar']:7.3f}")
    print(
        f"{'buy&hold skalowany do %.0f%%, zero timingu' % (exposure*100):44} "
        f"{scaled['cagr']*100:7.2f}% {scaled['max_drawdown']*100:8.2f}% {scaled['sharpe']:7.3f} {scaled['calmar']:7.3f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-holding-months", type=int, default=24)
    parser.add_argument("--replace-margin", type=float, default=10.0)
    parser.add_argument("--min-drawdown", type=float, default=0.25)
    parser.add_argument("--min-quality", type=float, default=50.0)
    parser.add_argument("--max-positions", type=int, default=4)
    parser.add_argument("--rebalance-to-target", action="store_true")
    parser.add_argument("--show-trades", action="store_true")
    parser.add_argument("--sweep", action="store_true")
    args = parser.parse_args()

    prices, benchmark, is_real_wig20, panel, decision_dates, tickers = build_inputs()
    print(f"uniwersum: {len(tickers)} spolek: {' '.join(tickers)}")
    if not is_real_wig20:
        print(
            "UWAGA: brak `data/pl/wig20.txt` - REL liczony wzgledem ROWNOWAZONEJ SREDNIEJ UNIWERSUM,\n"
            "       nie wzgledem WIG20. Sensowny zamiennik, ale NIE to samo co spec."
        )

    def run(**overrides) -> dict:
        config = QualityValueConfig(
            tickers=tickers,
            max_positions=overrides.get("max_positions", args.max_positions),
            min_drawdown=overrides.get("min_drawdown", args.min_drawdown),
            min_quality=overrides.get("min_quality", args.min_quality),
            replace_margin=overrides.get("replace_margin", args.replace_margin),
            max_holding_months=overrides.get("max_holding_months", args.max_holding_months),
            rebalance_to_target=overrides.get("rebalance_to_target", args.rebalance_to_target),
        )
        return run_quality_value_backtest(prices, benchmark, panel, decision_dates, config)

    if args.sweep:
        print(f"\n{'wariant':44} {'CAGR':>8} {'MaxDD':>9} {'Sharpe':>7} {'Calmar':>7} {'n':>4} {'expo':>6}")
        print("-" * 90)
        variants = [
            ("bazowa (24m, margin 10)", {}),
            ("max holding 36m", {"max_holding_months": 36}),
            ("max holding 12m", {"max_holding_months": 12}),
            ("margin podmiany 0 (zawsze lepszy)", {"replace_margin": 0.0}),
            ("margin podmiany 20", {"replace_margin": 20.0}),
            ("bramka dd >= 15%", {"min_drawdown": 0.15}),
            ("bramka dd >= 35%", {"min_drawdown": 0.35}),
            ("QUALITY >= 75", {"min_quality": 75.0}),
            ("QUALITY >= 0 (bez bramki jakosci)", {"min_quality": 0.0}),
            ("rebalans do 25% co miesiac", {"rebalance_to_target": True}),
            ("max 2 pozycje", {"max_positions": 2}),
            ("max 6 pozycji", {"max_positions": 6}),
        ]
        base_exposure = None
        for label, overrides in variants:
            result = run(**overrides)
            metrics = summarize(
                result, label, overrides.get("max_positions", args.max_positions), verbose=False
            )
            if metrics is None:
                continue
            if base_exposure is None:
                base_exposure = metrics["exposure"]
            print(
                f"{label:44} {metrics['cagr']*100:7.2f}% {metrics['max_drawdown']*100:8.2f}% "
                f"{metrics['sharpe']:7.3f} {metrics['calmar']:7.3f} {metrics['n_trades']:4.0f} {metrics['exposure']*100:5.0f}%"
            )
        result = run()
        benchmark_metrics(prices, result["first_decision_date"], base_exposure or 1.0)
        return

    result = run()
    metrics = summarize(
        result,
        f"bazowa: dd>={args.min_drawdown:.0%}, QUALITY>={args.min_quality:.0f}, max {args.max_holding_months}m",
        args.max_positions,
    )
    if metrics:
        benchmark_metrics(prices, result["first_decision_date"], metrics["exposure"])

    if args.show_trades:
        print("\ntransakcje:")
        for trade in result["trades"]:
            print(
                f"  {trade.ticker:4} {trade.entry_date.date()} @{trade.entry_price:9.2f} (score {trade.entry_score:5.1f}) -> "
                f"{trade.exit_date.date()} @{trade.exit_price:9.2f}  {trade.gross_return*100:+7.2f}%  "
                f"{trade.exit_reason:16} ({trade.holding_days}d)"
            )


if __name__ == "__main__":
    main()
