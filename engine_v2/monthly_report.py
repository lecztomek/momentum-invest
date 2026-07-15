"""
MONTHLY REPORT - user: "czy mamy plik z decyzjami miesiecznymi zwrotem z kazdego miesiaca maxdd
wagi tam powinny byc - generalnie taki przebieg". Odpowiedz: NIE mielismy - `results/<nazwa>.json`
trzyma tylko zbiorcze metryki (CAGR/MaxDD/Sharpe/Calmar...), nigdzie nie bylo pelnego,
miesiac-po-miesiacu ledgera (decyzja/waga/zwrot/drawdown per okres rebalansu). Ten skrypt buduje
taki ledger jako CSV, dla JEDNEJ strategii (pojedynczej albo laczonej) na raz - ta sama logika
liczenia final_portfolio/equity_curve co `run_one.py`/`generate_results.py` (podatek/koszty wg
wlasnego `test_spec.json` danej strategii, dla laczonych ten sam zalozony 19% co
`generate_results.py`), wiec liczby zgadzaja sie z opublikowanymi metrykami.

Kolumny CSV (jeden wiersz = jeden okres rebalansu, domyslnie miesiac):
  date, gross_return, net_return, turnover, operations, signal_changed, trade_cost,
  equity (PO podatku, startuje od 1.0), drawdown (biezacy spadek od dotychczasowego szczytu,
  zawsze <=0, PROBKOWANY na dni rebalansu), w_<ticker> (waga uzyta per aktywo w tym okresie, 0.0
  gdy nie trzymane; w__CASH jesli czesc portfela w gotowce).

  UWAGA: `drawdown` jest probkowany TYLKO na dni rebalansu (koniec/poczatek okresu), nie na kazdy
  dzien sesyjny - MIN tej kolumny moze byc PLYTSZY niz oficjalny MaxDD w `results/<nazwa>.json`,
  jesli najgorszy dzien wypadl W TRAKCIE okresu (nie akurat na rebalans). Skrypt wypisuje OBIE
  wartosci na koniec, zeby to bylo jawne.

Uruchomienie (z korzenia repo):
  .venv/bin/python3 -m engine_v2.monthly_report gpm_mid_10
  # zapisuje do results/monthly/gpm_mid_10.csv

Budowanie samego ledgera (`build_monthly_ledger`) zyje w `engine_v2/monthly_ledger.py` (2026-07-15)
- ten skrypt jest jedynie CLI-owym opakowaniem tamtej logiki (uruchamia strategie z pelnym
  podatkiem/kosztem wg jej WLASNEGO `test_spec.json`, jak `generate_results.py`). Dla NOWYCH
  strategii, ktore chca to zamiast tego wbudowane w sam pipeline (bez recznego odpalania), patrz
  blok `reporting` (`engine_v2/blocks/reporting/monthly_csv_export.py`) +
  `pipeline.run_strategy_pipeline_with_reporting()` - inny kontrakt (podatek jako WLASNY parametr
  bloku, nie odczyt `test_spec.json`), ale ta sama logika ledgera pod spodem.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Tuple

import pandas as pd

from engine_v2.annual_tax import apply_annual_tax
from engine_v2.backtest_engine import daily_equity_curve
from engine_v2.blocks.data_loader import REGISTRY as DATA_LOADER_REGISTRY
from engine_v2.combined_pipeline import run_combined_pipeline
from engine_v2.combined_spec import CombinedSpec
from engine_v2.generate_results import _COMBINED_ANNUAL_TAX_RATE, _DEMO_DIRS, STRATEGIES_DIR
from engine_v2.monthly_ledger import build_monthly_ledger
from engine_v2.pipeline import run_strategy_pipeline
from engine_v2.run_spec import RunSpec
from engine_v2.run_spec_runner import _load_daily_prices, _tax_adjusted_equity_curve
from engine_v2.spec import StrategySpec
from engine_v2.test_spec import TestSpec

RESULTS_DIR = STRATEGIES_DIR.parent / "results"


def _available_strategies() -> list:
    names = []
    for d in sorted(STRATEGIES_DIR.iterdir()):
        if not d.is_dir() or d.name in _DEMO_DIRS:
            continue
        if (d / "run_spec.json").exists() or (d / "combined_spec.json").exists():
            names.append(d.name)
    return names


def _final_portfolio_and_equity_single(strategy_dir: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    strategy_spec = StrategySpec.load(strategy_dir / "strategy_spec.json")
    test_spec = TestSpec.load(strategy_dir / "test_spec.json")

    final_portfolio = run_strategy_pipeline(strategy_spec)
    equity_curve = daily_equity_curve(final_portfolio, _load_daily_prices(strategy_spec), {})
    equity_curve, _ = _tax_adjusted_equity_curve(equity_curve, final_portfolio, test_spec)
    return final_portfolio, equity_curve


def _final_portfolio_and_equity_combined(combined_dir: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    combined_spec = CombinedSpec.load(combined_dir / "combined_spec.json")
    final_portfolio = run_combined_pipeline(combined_spec, combined_dir)

    universe: set = set()
    for rel_path in combined_spec.strategy_spec_paths:
        universe |= set(StrategySpec.load(combined_dir / rel_path).universe)

    loader_fn = DATA_LOADER_REGISTRY["stooq_csv"]
    daily_prices = loader_fn(sorted(universe), {"data_dir": "data/us", "frequency": "daily"}).prices

    equity_curve = daily_equity_curve(final_portfolio, daily_prices, {})
    equity_curve = apply_annual_tax(equity_curve, _COMBINED_ANNUAL_TAX_RATE)
    return final_portfolio, equity_curve


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("name", nargs="?", help="Nazwa folderu w strategies_v2/ (np. gpm_mid_10)")
    parser.add_argument("--out", help="Sciezka wyjsciowego CSV (domyslnie results/monthly/<nazwa>.csv)")
    args = parser.parse_args()

    available = _available_strategies()
    if not args.name:
        parser.print_usage()
        print("Dostepne strategie:")
        for n in available:
            print(f"  {n}")
        sys.exit(1)
    if args.name not in available:
        print(f"Nieznana strategia '{args.name}'.\n\nDostepne:")
        for n in available:
            print(f"  {n}")
        sys.exit(1)

    strategy_dir = STRATEGIES_DIR / args.name
    if (strategy_dir / "run_spec.json").exists():
        final_portfolio, equity_curve = _final_portfolio_and_equity_single(strategy_dir)
    else:
        final_portfolio, equity_curve = _final_portfolio_and_equity_combined(strategy_dir)

    ledger = build_monthly_ledger(final_portfolio, equity_curve)

    out_path = Path(args.out) if args.out else RESULTS_DIR / "monthly" / f"{args.name}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(out_path, index=False)

    daily_equity = equity_curve.sort_values("date")["equity"]
    true_daily_maxdd = float((daily_equity / daily_equity.cummax() - 1.0).min())

    print(f"Zapisano {len(ledger)} okresow do {out_path}")
    print(f"drawdown w kolumnie 'drawdown' (probkowany NA DATY rebalansu): min = {ledger['drawdown'].min():.2%}")
    print(
        f"prawdziwy MaxDD (najgorszy pojedynczy DZIEN w calej historii, jak w results/<nazwa>.json): "
        f"{true_daily_maxdd:.2%}"
    )
    if abs(true_daily_maxdd - ledger["drawdown"].min()) > 1e-9:
        print(
            "(roznica: najgorszy dzien wypadl W TRAKCIE miesiaca, nie akurat na dzien rebalansu - "
            "kolumna 'drawdown' pokazuje tylko punkty rebalansu, nie kazdy dzien)"
        )


if __name__ == "__main__":
    main()
