"""
Buduje przestrzen roboczą dla silnika: kopia danych z repo plus ceny wpisane
recznie, pobrane z Firestore.

Plikow w data/ NIE ruszamy. To sa dane dostawcy i maja zostac takie, jakie
przyszly - inaczej stracilibysmy mozliwosc odroznienia bledu zrodla od wlasnej
poprawki. Ceny reczne doklejaja sie wylacznie do kopii.

Wymaga zmiennej FIREBASE_SA z trescia klucza konta serwisowego. Bez niej
konczy sie spokojnie, budujac sama kopie danych z repo.

    python3 tools/sync_prices.py --out /tmp/workspace
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOGI = {"best17_a": "data/us", "gpm_uk": "data/uk"}
TRANSZE = (10, 25)              # musi zgadzac sie z tools/build_signals.py

# panel operuje na skrotach, silnik na nazwach plikow
TICKER = {
    "XLK": "xlk.us", "IVV": "ivv.us", "VT": "vt.us", "IAU": "iau.us", "DBC": "dbc.us",
    **{t: f"{t.lower()}.uk" for t in
       ["CSPX", "CNDX", "EIMI", "XRES", "CMOD", "IGLN", "IHYA", "LQDA", "DTLA", "IUES", "CBU0", "IBTA"]},
}


def z_firestore() -> list[dict]:
    sa = os.environ.get("FIREBASE_SA", "").strip()
    if not sa:
        print("FIREBASE_SA nie ustawione - pomijam ceny z bazy")
        return []
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError:
        print("brak firebase-admin - pomijam ceny z bazy", file=sys.stderr)
        return []
    cred = credentials.Certificate(json.loads(sa))
    firebase_admin.initialize_app(cred)
    wpisy = [d.to_dict() | {"id": d.id} for d in firestore.client().collection("price_entries").stream()]
    print(f"z bazy: {len(wpisy)} dni")
    return wpisy


def plik_tickera(katalog: Path, ticker: str) -> Path | None:
    for wzor in (f"{ticker}.txt", f"*/{ticker}.txt", f"*/*/{ticker}.txt"):
        trafienia = list(katalog.glob(wzor))
        if trafienia:
            return trafienia[0]
    return None


def dopisz(sciezka: Path, data: str, cena: float) -> bool:
    """Dopisuje jeden dzien. Nie rusza istniejacych wierszy - jesli dzien juz
    jest, zostawia go w spokoju i zglasza to wyzej."""
    linie = sciezka.read_text().splitlines()
    znacznik = data.replace("-", "")
    if any(f",{znacznik}," in w for w in linie):
        return False
    etykieta = sciezka.name.split(".txt")[0].upper()
    linie.append(f"{etykieta},D,{znacznik},000000,{cena},{cena},{cena},{cena},0,0")
    naglowek, reszta = linie[0], sorted(linie[1:], key=lambda w: w.split(",")[2])
    sciezka.write_text("\n".join([naglowek, *reszta]) + "\n")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    ws = Path(a.out).resolve()
    if ws.exists():
        shutil.rmtree(ws)
    (ws / "strategies_v2").mkdir(parents=True)
    shutil.copytree(ROOT / "data", ws / "data")
    print(f"kopia danych w {ws / 'data'}")

    dopisane = pominiete = 0
    for wpis in sorted(z_firestore(), key=lambda w: w.get("date", "")):
        data, ceny = wpis.get("date"), wpis.get("px") or {}
        if not data or not ceny:
            continue
        brak = [t for t in TICKER if t not in ceny]
        if brak:
            print(f"POMIJAM {data}: brakuje {len(brak)} cen ({', '.join(brak[:4])}…). "
                  "Sygnal z niekompletnego dnia bylby bledny.", file=sys.stderr)
            pominiete += 1
            continue
        for skrot, wartosc in ceny.items():
            nazwa = TICKER.get(skrot)
            if not nazwa:
                continue
            p = plik_tickera(ws / "data", nazwa)
            if p and dopisz(p, data, float(wartosc)):
                dopisane += 1
    print(f"dopisanych notowan: {dopisane}, pominietych dni: {pominiete}")

    # Kopie konfiguracji wskazujace na kopie danych. Kopiujemy DOKLADNIE te strategie,
    # ktorych uzywa build_signals.py: obie nogi w wariancie kazdej transzy plus
    # polaczone specy (te maja sciezki wzgledne, wiec wystarczy, ze leza obok).
    for noga, podkatalog in NOGI.items():
        for dzien in TRANSZE:
            kat = f"{noga}_day{dzien}"
            cel = ws / "strategies_v2" / kat
            shutil.copytree(ROOT / "strategies_v2" / kat, cel)
            spec = json.loads((cel / "strategy_spec.json").read_text())
            spec["base_params"]["data_loader"]["data_dir"] = str(ws / podkatalog)
            (cel / "strategy_spec.json").write_text(json.dumps(spec, indent=4))
            print(f"{kat}: dane z {ws / podkatalog}")
    for dzien in TRANSZE:
        kat = f"gpm_uk_best17_a_day{dzien}"
        shutil.copytree(ROOT / "strategies_v2" / kat, ws / "strategies_v2" / kat)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
