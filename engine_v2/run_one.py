"""
RUN ONE - user: "Chce miec skrypt jak w starym engine gdzie wybieram ktora odpalic i tylko ona
idzie" (w odroznieniu od `generate_results.py`, ktory zawsze przelicza WSZYSTKIE ~50 strategii).

Uruchamia DOKLADNIE JEDNA strategie (pojedyncza `run_spec.json` albo laczona `combined_spec.json`)
z `strategies_v2/<nazwa>/` i wypisuje metryki na ekran. Reuzywa TA SAMA logike liczenia co
`generate_results.py` (`_generate_single`/`_generate_combined`) - wynik jest identyczny z tym co
trafiloby do `results/<nazwa>.json`, ale metryki (`payload`) NIC nie zapisuja na dysk (to celowo
osobny krok - `generate_results.py` albo reczne `_write_result`, po to zeby przypadkowe odpalenie
tego skryptu nie nadpisywalo zamrozonych wynikow w repo).

Miesieczny ledger (user: "Jak tak samo monthly przeciez w calym przebiegu powinien sie
generowac" - po tym jak `monthly_report.py` byl osobnym, recznym krokiem) JEST zapisywany
domyslnie, do `results/monthly/<nazwa>.csv`, jako CZESC KAZDEGO uruchomienia `run_one` - wylacz
`--skip-monthly`, jesli akurat nie jest potrzebny (np. szybki podglad samych metryk). To JEDYNA
rzecz z tego skryptu, ktora faktycznie zapisuje plik - i robi to celowo (w odroznieniu od
`payload`/metryk), bo miesieczny ledger nie jest "zamrozonym wynikiem" jak `results/<nazwa>.json`
(nie ma go w recenzji/regresji), tylko biezacym podgladem do przegladania.

Uruchomienie (z korzenia repo):
  .venv/bin/python3 -m engine_v2.run_one gpm_mid_10
  .venv/bin/python3 -m engine_v2.run_one gpm_mid_10 --skip-monthly
  .venv/bin/python3 -m engine_v2.run_one --list
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Dict, List

from engine_v2.generate_results import (
    _DEMO_DIRS,
    STRATEGIES_DIR,
    _generate_combined,
    _generate_single,
)
from engine_v2.monthly_report import (
    RESULTS_DIR,
    _final_portfolio_and_equity_combined,
    _final_portfolio_and_equity_single,
    build_monthly_ledger,
)


def _available_strategies() -> List[str]:
    names = []
    for d in sorted(STRATEGIES_DIR.iterdir()):
        if not d.is_dir() or d.name in _DEMO_DIRS:
            continue
        if (d / "run_spec.json").exists() or (d / "combined_spec.json").exists():
            names.append(d.name)
    return names


def _print_available(names: List[str]) -> None:
    print("Dostepne strategie (strategies_v2/<nazwa>):")
    for n in names:
        print(f"  {n}")


def _print_metrics(name: str, payload: Dict[str, Any]) -> None:
    metrics = payload.get("metrics")
    pre_tax = payload.get("metrics_pre_tax")
    print(f"\n=== {name} ({payload.get('mode', 'final')}) ===")
    if metrics:
        print(
            f"CAGR {metrics['cagr']:.2%}  MaxDD {metrics['max_drawdown']:.2%}  "
            f"Sharpe {metrics['sharpe']:.3f}  Calmar {metrics['calmar']:.3f}  "
            f"Turnover/rok {metrics['annual_turnover']:.2f}"
        )
    else:
        print("(brak 'metrics' w wyniku - sprawdz mode w run_spec.json)")
    if pre_tax:
        print(
            f"przed podatkiem: CAGR {pre_tax['cagr']:.2%}  MaxDD {pre_tax['max_drawdown']:.2%}  "
            f"Sharpe {pre_tax['sharpe']:.3f}  Calmar {pre_tax['calmar']:.3f}"
        )


def _write_monthly_ledger(name: str, strategy_dir) -> None:
    if (strategy_dir / "run_spec.json").exists():
        final_portfolio, equity_curve = _final_portfolio_and_equity_single(strategy_dir)
    else:
        final_portfolio, equity_curve = _final_portfolio_and_equity_combined(strategy_dir)

    ledger = build_monthly_ledger(final_portfolio, equity_curve)
    out_path = RESULTS_DIR / "monthly" / f"{name}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(out_path, index=False)
    print(f"\nMiesieczny ledger ({len(ledger)} okresow) zapisany do {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("name", nargs="?", help="Nazwa folderu w strategies_v2/ (np. gpm_mid_10)")
    parser.add_argument("--list", action="store_true", help="Wypisz dostepne strategie i zakoncz")
    parser.add_argument(
        "--skip-monthly", action="store_true", help="Nie zapisuj results/monthly/<nazwa>.csv (domyslnie zapisywany)"
    )
    args = parser.parse_args()

    available = _available_strategies()

    if args.list:
        _print_available(available)
        sys.exit(0)

    if not args.name:
        parser.print_usage()
        _print_available(available)
        sys.exit(1)

    if args.name not in available:
        print(f"Nieznana strategia '{args.name}'.\n")
        _print_available(available)
        sys.exit(1)

    strategy_dir = STRATEGIES_DIR / args.name
    if (strategy_dir / "run_spec.json").exists():
        payload = _generate_single(strategy_dir)
    else:
        payload = _generate_combined(strategy_dir)

    _print_metrics(args.name, payload)

    if not args.skip_monthly:
        _write_monthly_ledger(args.name, strategy_dir)


if __name__ == "__main__":
    main()
