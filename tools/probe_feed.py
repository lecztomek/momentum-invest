"""
SONDA ZRODLA CEN - faza 0 planu backendu.

Pyta o jedno: czy dostawca oddaje komplet 17 instrumentow strategii i czy jego
liczby zgadzaja sie z plikami, ktore juz mamy w data/. Dostawca, ktory nie
odtworzy historii, ktorej ufamy, odpada - nie ma sensu budowac na nim pipeline'u.

Uruchamiana przez GitHub Actions, bo to jest srodowisko, w ktorym bedzie zyc:
inne IP, inne limity i inne blokady niz na dowolnym komputerze.

    python3 tools/probe_feed.py            # pelny raport
    python3 tools/probe_feed.py --years 2  # porownaj krotszy odcinek
"""
from __future__ import annotations

import argparse
import io
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# 5 instrumentow sygnalowych (US) + 12 wykonawczych (Londyn)
US = ["xlk", "ivv", "vt", "iau", "dbc"]
UK = ["cspx", "cndx", "eimi", "xres", "cmod", "igln",
      "ihya", "lqda", "dtla", "iues", "cbu0", "ibta"]

TOLERANCJA = 0.002   # 0.2% - mniejsze roznice to zaokraglenia, nie inne dane
UA = "momentum-invest-probe"


@dataclass
class Wynik:
    symbol: str
    pobrano: int = 0
    wspolnych: int = 0
    zgodnych: int = 0
    blad: str = ""
    najgorsza: tuple[str, float, float] | None = None
    braki: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.blad and self.wspolnych > 0 and self.zgodnych == self.wspolnych


def lokalne(symbol: str) -> dict[str, float]:
    """Ceny zamkniecia z plikow w repo - traktujemy je jako punkt odniesienia."""
    kand = list(DATA.glob(f"*/{symbol}.txt")) + list(DATA.glob(f"*/*/{symbol}.txt"))
    if not kand:
        return {}
    out: dict[str, float] = {}
    for line in kand[0].read_text().splitlines()[1:]:
        p = line.split(",")
        if len(p) < 8:
            continue
        d = p[2].strip("<>")
        out[f"{d[:4]}-{d[4:6]}-{d[6:8]}"] = float(p[7])
    return out


def ze_stooq(symbol: str, timeout: int) -> tuple[dict[str, float], str]:
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return {}, f"HTTP {e.code}"
    except Exception as e:                                  # noqa: BLE001
        return {}, f"{type(e).__name__}: {e}"
    if not raw.strip():
        return {}, "pusta odpowiedz"
    head = raw.splitlines()[0].lower()
    if "date" not in head:
        return {}, f"nie CSV: {raw.strip()[:60]!r}"
    out: dict[str, float] = {}
    for line in io.StringIO(raw).readlines()[1:]:
        p = line.strip().split(",")
        if len(p) >= 5 and p[4] not in ("", "N/A"):
            out[p[0]] = float(p[4])
    return out, ""


def sprawdz(symbol: str, lata: float, timeout: int) -> Wynik:
    w = Wynik(symbol)
    ref = lokalne(symbol)
    zdalne, blad = ze_stooq(symbol, timeout)
    if blad:
        w.blad = blad
        return w
    w.pobrano = len(zdalne)
    if not ref:
        w.blad = "brak pliku odniesienia w data/"
        return w
    granica = sorted(ref)[-1]
    start = f"{int(granica[:4]) - int(lata)}{granica[4:]}"
    wspolne = [d for d in ref if start <= d <= granica and d in zdalne]
    w.wspolnych = len(wspolne)
    najg = 0.0
    for d in wspolne:
        a, b = ref[d], zdalne[d]
        roz = abs(a - b) / a if a else 0.0
        if roz <= TOLERANCJA:
            w.zgodnych += 1
        elif roz > najg:
            najg, w.najgorsza = roz, (d, a, b)
    w.braki = [d for d in ref if start <= d <= granica and d not in zdalne][:5]
    return w


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=float, default=2)
    ap.add_argument("--timeout", type=int, default=30)
    a = ap.parse_args()

    print(f"SONDA ZRODLA CEN - stooq, porownanie {a.years:g} ostatnich lat z plikami w data/")
    print(f"tolerancja {TOLERANCJA * 100:.1f}%\n")
    print(f"{'symbol':12} {'pobrano':>8} {'wspolnych':>10} {'zgodnych':>9}  uwagi")
    print("-" * 78)

    wyniki = []
    for grupa, rynek in ((US, "us"), (UK, "uk")):
        for t in grupa:
            w = sprawdz(f"{t}.{rynek}", a.years, a.timeout)
            wyniki.append(w)
            uwaga = w.blad
            if not uwaga and w.najgorsza:
                d, x, y = w.najgorsza
                uwaga = f"rozbieznosc {d}: nasze {x} vs feed {y}"
            if not uwaga and w.braki:
                uwaga = f"brak {len(w.braki)}+ sesji, np. {w.braki[0]}"
            print(f"{w.symbol:12} {w.pobrano:>8} {w.wspolnych:>10} {w.zgodnych:>9}  {uwaga}")

    dobre = [w for w in wyniki if w.ok]
    print("-" * 78)
    print(f"\nkomplet: {len(dobre)}/{len(wyniki)} instrumentow zgadza sie w calosci")
    zle = [w for w in wyniki if not w.ok]
    if zle:
        print("\nproblemy:")
        for w in zle:
            print(f"  {w.symbol:10} {w.blad or f'{w.wspolnych - w.zgodnych} sesji sie nie zgadza'}")
    print("\nWERDYKT:", "ZRODLO NADAJE SIE" if not zle else "ZRODLO NIE PRZESZLO - nie budowac na nim pipeline'u")
    return 0 if not zle else 1


if __name__ == "__main__":
    sys.exit(main())
