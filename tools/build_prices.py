"""
Wystawia do web/data/prices.json CENY, Z KTORYCH POLICZONY JEST SYGNAL.

To nie jest swieze pobranie z dostawcy i nie ma nim byc. Ekran "Ceny" sluzy do
jednego: sprawdzenia, czy liczby, na ktorych pracowal silnik, zgadzaja sie z tym,
co user widzi u brokera. Zeby to mialo sens, musza to byc DOKLADNIE te same ceny,
ktore wzial silnik - wiec czytamy je tym samym loaderem i tym samym kotwiczeniem
dnia (`nth_trading_day_prices`), co liczy strategia danej transzy.

KAZDA NOGA MA WLASNY KALENDARZ. Noga US nie ma sesji w Memorial Day, noga UK w
swoje swieta - wiec "25-ty albo pierwsza sesja po nim" wypada im czasem w innym
dniu. Nie usredniamy tego i nie zgadujemy: kolumna dostaje date, w ktorej OBIE
nogi maja juz kurs (pozniejsza z dwoch), a kazda cena niesie `asof` - dzien, z
ktorego naprawde pochodzi. Panel pokazuje to przy cenie, kiedy sie rozjezdza.

Okres bez sesji na/po dniu transzy pomijamy tak samo jak w build_signals.py:
anchor cofa sie wtedy do ostatniej dostepnej sesji, a taka cena nie jest cena
z dnia rebalansu.

    python3 tools/build_prices.py
    python3 tools/build_prices.py --specs /tmp/ws/strategies_v2 --dni 14
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # import silnika z korzenia repo
sys.path.insert(0, str(Path(__file__).resolve().parent))         # TICKER z sync_prices

import pandas as pd

from engine_v2.period_anchor import nth_trading_day_dates, nth_trading_day_prices
from engine_v2.pipeline import _lookup
from engine_v2.spec import StrategySpec
from sync_prices import TICKER
from wspolne import zapisz_jesli_zmiana

ROOT = Path(__file__).resolve().parent.parent
WYJSCIE = ROOT / "web" / "data" / "prices.json"
TRANSZE = (10, 25)              # musi zgadzac sie z tools/build_signals.py
NOGI = {"us": "best17_a", "uk": "gpm_uk"}

RYNEK = {t: ("US" if n.endswith(".us") else "UK") for t, n in TICKER.items()}


def cena(x) -> float | None:
    return None if pd.isna(x) else round(float(x), 4 if float(x) < 20 else 2)


def noga_dnia(baza: Path, katalog: str, dzien: int):
    """Ceny wykonania jednej nogi, zakotwiczone tak jak kotwiczy je silnik.

    `MarketData.prices` jest ZAWSZE dzienne, niezaleznie od `frequency` strategii
    (patrz docstring csv_loader i _run_phase_a) - dzien wykonania wybiera dopiero
    `nth_trading_day_prices`. Bierzemy wiec DWIE wersje tego samego dnia:
      notowane - z surowych danych: NaN znaczy "tego dnia nie bylo sesji dla tego
                 tickera" (np. swieto tylko na jednej z gield),
      uzyte    - po data_cleanerze, czyli liczba, z ktora silnik naprawde pracowal
                 (cleaner interpoluje takie dziury liniowo).
    Panel pokazuje notowanie, a gdy go nie ma - mowi wprost, ze to interpolacja."""
    spec = StrategySpec.load(baza / f"{katalog}_day{dzien}" / "strategy_spec.json")
    loader = _lookup("data_loader", spec.blocks["data_loader"])
    params = spec.base_params.get("data_loader", {})

    surowe = loader(spec.universe, params)
    czyste = _lookup("data_cleaner", spec.blocks["data_cleaner"])(
        surowe, spec.base_params.get("data_cleaner", {}))

    return {
        "notowane": nth_trading_day_prices(surowe.prices, dzien),
        "uzyte": nth_trading_day_prices(czyste.prices, dzien),
        "daty": nth_trading_day_dates(surowe.prices.index, dzien),
        "koniec": surowe.prices.index.max(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dni", type=int, default=14, help="ile ostatnich dat rebalansu wystawic")
    ap.add_argument("--specs", help="katalog z kopiami strategii (np. z sync_prices.py)")
    a = ap.parse_args()

    baza = Path(a.specs) if a.specs else ROOT / "strategies_v2"
    serie: dict[str, dict] = {}
    ostatnia_sesja = None

    for dzien in TRANSZE:
        nogi = {rynek: noga_dnia(baza, katalog, dzien) for rynek, katalog in NOGI.items()}
        for g in nogi.values():
            ostatnia_sesja = g["koniec"] if ostatnia_sesja is None else max(ostatnia_sesja, g["koniec"])

        def n(t):                      # noga, ktora wycenia ten instrument
            return nogi[RYNEK[t].lower()]

        wspolne = sorted(set(nogi["us"]["daty"].index) & set(nogi["uk"]["daty"].index))
        okresy = [e for e in wspolne if all(g["daty"][e].day >= dzien for g in nogi.values())][-a.dni:]

        brak = sorted(t for t, nazwa in TICKER.items() if nazwa not in n(t)["notowane"].columns)
        if brak:
            raise SystemExit(f"transza {dzien}: brak w danych tickerow {brak}")

        serie[str(dzien)] = {
            "dates": [max(g["daty"][e] for g in nogi.values()).strftime("%Y-%m-%d") for e in okresy],
            # notowanie z sesji; null = tego dnia nie bylo sesji dla tego tickera
            "px": {t: [cena(n(t)["notowane"].at[e, nazwa]) for e in okresy]
                   for t, nazwa in TICKER.items()},
            # liczba, z ktora pracowal silnik - rozni sie od px tylko tam, gdzie px jest null
            "used": {t: [cena(n(t)["uzyte"].at[e, nazwa]) for e in okresy]
                     for t, nazwa in TICKER.items()},
            "asof": {t: [n(t)["daty"][e].strftime("%Y-%m-%d") for e in okresy] for t in TICKER},
        }
        s = serie[str(dzien)]
        rozne = sum(1 for t in TICKER for i, d in enumerate(s["asof"][t]) if d != s["dates"][i])
        puste = sum(1 for t in TICKER for x in s["px"][t] if x is None)
        print(f"transza {dzien:2}: {len(okresy)} dat, {s['dates'][0]} .. {s['dates'][-1]}, "
              f"kurs z innego dnia niz kolumna: {rozne}, bez notowania (interpolacja): {puste}")

    wynik = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "feed": {
            "source": "repo + wpisy reczne",
            "fetched": ostatnia_sesja.strftime("%Y-%m-%d"),
        },
        "instruments": [[t, RYNEK[t]] for t in TICKER],
        "series": serie,
    }
    zapisz_jesli_zmiana(WYJSCIE, wynik)
    print(f"\n{WYJSCIE.relative_to(ROOT)}: {len(TICKER)} instrumentow, "
          f"ostatnia sesja w danych {wynik['feed']['fetched']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
