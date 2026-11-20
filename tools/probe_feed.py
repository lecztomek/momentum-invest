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
import datetime
import io
import json
import re
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
    waluta: str = ""
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


def _pobierz(url: str, timeout: int) -> tuple[str, str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace"), ""
    except urllib.error.HTTPError as e:
        try:
            tresc = e.read().decode("utf-8", "replace")[:200].replace("\n", " ")
        except Exception:                                   # noqa: BLE001
            tresc = ""
        return "", f"HTTP {e.code} {tresc}".strip()
    except Exception as e:                                  # noqa: BLE001
        return "", f"{type(e).__name__}: {e}"


def ze_stooq(symbol: str, timeout: int) -> tuple[dict[str, float], str]:
    raw, blad = _pobierz(f"https://stooq.com/q/d/l/?s={symbol}&i=d", timeout)
    if blad:
        return {}, blad
    if not raw.strip():
        return {}, "pusta odpowiedz"
    if "date" not in raw.splitlines()[0].lower():
        # zamiast CSV przychodzi strona - wyciagamy z niej cokolwiek czytelnego
        tekst = re.sub(r"<[^>]+>", " ", raw)
        tekst = re.sub(r"\s+", " ", tekst).strip()
        return {}, f"nie CSV: {tekst[:120]!r}"
    out: dict[str, float] = {}
    for line in io.StringIO(raw).readlines()[1:]:
        p = line.strip().split(",")
        if len(p) >= 5 and p[4] not in ("", "N/A"):
            out[p[0]] = float(p[4])
    return out, ""


def _yahoo_symbol(symbol: str) -> str:
    baza, rynek = symbol.rsplit(".", 1)
    return baza.upper() if rynek == "us" else f"{baza.upper()}.L"


def ze_yahoo(symbol: str, timeout: int) -> tuple[dict[str, float], str]:
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{_yahoo_symbol(symbol)}?range=3y&interval=1d")
    raw, blad = _pobierz(url, timeout)
    if blad:
        return {}, blad
    try:
        j = json.loads(raw)
    except ValueError:
        tekst = re.sub(r"<[^>]+>", " ", raw)
        return {}, f"nie JSON: {re.sub(chr(92) + 's+', ' ', tekst)[:120]!r}"
    res = (j.get("chart") or {}).get("result")
    if not res:
        err = ((j.get("chart") or {}).get("error") or {})
        return {}, f"brak danych: {err.get('description') or err.get('code') or raw[:80]}"
    r0 = res[0]
    czasy = r0.get("timestamp") or []
    zamkn = ((r0.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    waluta = (r0.get("meta") or {}).get("currency", "?")
    out: dict[str, float] = {}
    for ts, c in zip(czasy, zamkn):
        if c is None:
            continue
        out[datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")] = float(c)
    if not out:
        return {}, "zero notowan"
    return out, f"__waluta__{waluta}"


ZRODLA = {"stooq": ze_stooq, "yahoo": ze_yahoo}


def sprawdz(symbol: str, zrodlo: str, lata: float, timeout: int) -> Wynik:
    w = Wynik(symbol)
    ref = lokalne(symbol)
    zdalne, blad = ZRODLA[zrodlo](symbol, timeout)
    if blad.startswith("__waluta__"):
        w.waluta, blad = blad[10:], ""
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
    ap.add_argument("--sources", default="stooq,yahoo")
    a = ap.parse_args()

    symbole = [f"{t}.us" for t in US] + [f"{t}.uk" for t in UK]
    podsumowanie = {}

    for zrodlo in a.sources.split(","):
        print(f"\n{'=' * 78}\nZRODLO: {zrodlo}  -  porownanie {a.years:g} ostatnich lat z plikami w data/"
              f", tolerancja {TOLERANCJA * 100:.1f}%\n")
        print(f"{'symbol':12} {'pobrano':>8} {'wspoln':>7} {'zgodnych':>9} {'wal':>5}  uwagi")
        print("-" * 78)
        wyniki = []
        for s in symbole:
            w = sprawdz(s, zrodlo, a.years, a.timeout)
            wyniki.append(w)
            uwaga = w.blad
            if not uwaga and w.najgorsza:
                d, x, y = w.najgorsza
                uwaga = f"rozbieznosc {d}: nasze {x} vs feed {y}"
            if not uwaga and w.braki:
                uwaga = f"brak {len(w.braki)}+ sesji, np. {w.braki[0]}"
            print(f"{w.symbol:12} {w.pobrano:>8} {w.wspolnych:>7} {w.zgodnych:>9} {w.waluta:>5}  {uwaga[:90]}")
        dobre = [w for w in wyniki if w.ok]
        podsumowanie[zrodlo] = (len(dobre), len(wyniki))
        print("-" * 78)
        print(f"{zrodlo}: {len(dobre)}/{len(wyniki)} instrumentow zgadza sie w calosci")

    print(f"\n{'=' * 78}\nPODSUMOWANIE")
    for zrodlo, (d, n) in podsumowanie.items():
        print(f"  {zrodlo:8} {d}/{n}  {'NADAJE SIE' if d == n else 'nie przechodzi'}")
    zwyciezca = [z for z, (d, n) in podsumowanie.items() if d == n]
    print("\nWERDYKT:", f"budujemy na: {zwyciezca[0]}" if zwyciezca
          else "zadne zrodlo nie przeszlo - potrzebny dostawca z kluczem API")
    return 0 if zwyciezca else 1


if __name__ == "__main__":
    sys.exit(main())
