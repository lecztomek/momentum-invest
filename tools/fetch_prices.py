"""
Dociaga brakujace notowania z Yahoo Finance i DOKLEJA je do data/.

Dlaczego to nie jest zwykle "pobierz i zapisz": pliki w data/ pochodza ze stooq,
a Yahoo nie podaje tych samych liczb. Rozne moga byc: waluta (GBX vs GBP, sto
razy), korekta o dywidendy, a czasem to po prostu inny instrument o podobnym
tickerze. Doklejenie takiej serii "na styk" robi w szeregu sztuczny skok, a
silnik liczy momentum ze STOSUNKU cen - jeden falszywy skok o 1% przeklada sie
wprost na sygnal.

Dlatego kazdy ticker przechodzi przez trzy sita, zanim cokolwiek zostanie
zapisane:

  1. ZWROTY. Na wspolnym oknie (domyslnie 90 dni, ktore JUZ sa w data/)
     porownujemy dzienne zwroty. Roznica waluty czy korekty o dywidendy nie
     zmienia zwrotow, wiec jesli te sie nie zgadzaja, to nie jest ten sam
     instrument i symbol leci.
  2. STALOSC KURSU PRZELICZENIA. Stosunek poziomow Yahoo/stooq musi byc staly
     przez cale okno. Staly = da sie przeliczyc jedna liczba. Dryfujacy =
     Yahoo koryguje o cos, czego stooq nie koryguje (dywidendy), i doklejanie
     takiej serii zafalszowaloby historie.
  3. KOMPLET DNI. Yahoo musi miec wszystkie sesje, ktore ma stooq w oknie - brak
     sesji w zrodle oznacza dziury w przyszlych danych.

Dopiero to, co przeszlo, dokleja sie PRZESKALOWANE do ostatniej ceny ze stooq,
zeby szereg byl ciagly. Istniejacych wierszy nie ruszamy nigdy.

Dopisany wiersz ma cene zamkniecia w czterech polach OHLC i zerowy wolumen -
tak samo jak ceny wpisywane recznie przez sync_prices.py. Silnik czyta wylacznie
CLOSE, wiec to nie zmienia wyniku, ale warto wiedziec, ze te pola nie sa
prawdziwym otwarciem i maksimum sesji.

    python3 tools/fetch_prices.py                 # tylko sprawdza, nic nie zapisuje
    python3 tools/fetch_prices.py --zapisz        # dokleja to, co przeszlo sita
    python3 tools/fetch_prices.py --okno 120      # dluzsze okno porownania
    python3 tools/fetch_prices.py --zrodlo plik.json   # bez sieci, do testow
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAPA = Path(__file__).resolve().parent / "yahoo_symbols.json"
API = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={od}&period2={do}&interval=1d"

# Progi sit. Celowo ciasne - lepiej odrzucic ticker i powiedziec o tym, niz
# dokleic serie, ktora "mniej wiecej pasuje".
MAX_ROZNICA_ZWROTU = 0.003      # 0,3 pp na pojedynczej sesji
MAX_SREDNIA_ROZNICA = 0.0005    # 0,05 pp srednio
MAX_DRYF_KURSU = 0.002          # 0,2% rozrzutu stosunku poziomow


def wczytaj_stooq(sciezka: Path) -> dict[str, float]:
    out = {}
    for w in sciezka.read_text().splitlines()[1:]:
        p = w.split(",")
        if len(p) > 7:
            out[p[2]] = float(p[7])
    return out


def pobierz_yahoo(symbol: str, od: dt.date, do: dt.date) -> dict[str, float]:
    url = API.format(sym=symbol,
                     od=int(dt.datetime.combine(od, dt.time()).timestamp()),
                     do=int(dt.datetime.combine(do, dt.time()).timestamp()))
    req = urllib.request.Request(url, headers={"User-Agent": "market-data-client/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        dane = json.loads(r.read())
    wynik = dane["chart"]["result"][0]
    # close, nie adjclose - stooq tez podaje surowe zamkniecie
    zamkniecia = wynik["indicators"]["quote"][0]["close"]
    out = {}
    for ts, c in zip(wynik["timestamp"], zamkniecia):
        if c is None:
            continue
        out[dt.datetime.utcfromtimestamp(ts).strftime("%Y%m%d")] = float(c)
    return out


def sprawdz(nasze: dict[str, float], obce: dict[str, float], okno: int):
    """Czy obca seria to ten sam instrument, tylko w innej skali?
    Zwraca (ok, kurs_przeliczenia, powod_odrzucenia)."""
    dni = sorted(nasze)[-okno:]
    brak = [d for d in dni if d not in obce]
    if len(brak) > len(dni) * 0.02:
        return False, None, f"zrodlo nie ma {len(brak)} z {len(dni)} sesji z okna"
    wspolne = [d for d in dni if d in obce]
    if len(wspolne) < 30:
        return False, None, f"za malo wspolnych sesji ({len(wspolne)})"

    rozn, stosunki = [], []
    for a, b in zip(wspolne, wspolne[1:]):
        rozn.append(abs((obce[b] / obce[a] - 1) - (nasze[b] / nasze[a] - 1)))
    for d in wspolne:
        stosunki.append(obce[d] / nasze[d])

    naj = max(rozn)
    sred = sum(rozn) / len(rozn)
    sr_stos = sum(stosunki) / len(stosunki)
    dryf = (max(stosunki) - min(stosunki)) / sr_stos

    if naj > MAX_ROZNICA_ZWROTU:
        return False, None, f"zwroty sie rozjezdzaja, najgorsza sesja {naj*100:.2f} pp"
    if sred > MAX_SREDNIA_ROZNICA:
        return False, None, f"zwroty sie rozjezdzaja, srednio {sred*100:.3f} pp"
    if dryf > MAX_DRYF_KURSU:
        return False, None, (f"stosunek poziomow dryfuje o {dryf*100:.2f}% - zrodlo koryguje "
                             "o cos, czego stooq nie koryguje")
    return True, sr_stos, None


def dopisz(sciezka: Path, nowe: dict[str, float]) -> int:
    linie = sciezka.read_text().splitlines()
    sa = {w.split(",")[2] for w in linie[1:] if len(w.split(",")) > 2}
    etykieta = sciezka.name.split(".txt")[0].upper()
    dodane = 0
    for d in sorted(nowe):
        if d in sa:
            continue
        c = round(nowe[d], 4)
        linie.append(f"{etykieta},D,{d},000000,{c},{c},{c},{c},0,0")
        dodane += 1
    if dodane:
        naglowek, reszta = linie[0], sorted(linie[1:], key=lambda w: w.split(",")[2])
        sciezka.write_text("\n".join([naglowek, *reszta]) + "\n")
    return dodane


DANE = ROOT / "data"


def plik_tickera(ticker: str) -> Path | None:
    """Pliki leza raz plasko, raz w podkatalogu gieldy (data/us/nyse/...) -
    szukamy tak samo jak sync_prices.py, zeby oba narzedzia widzialy to samo."""
    kat = DANE / ("us" if ticker.endswith(".us") else "uk")
    for wzor in (f"{ticker}.txt", f"*/{ticker}.txt", f"*/*/{ticker}.txt"):
        trafienia = sorted(kat.glob(wzor))
        if trafienia:
            return trafienia[0]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zapisz", action="store_true", help="dokleja; bez tego tylko sprawdza")
    ap.add_argument("--okno", type=int, default=90, help="ile ostatnich sesji porownac")
    ap.add_argument("--zrodlo", help="plik JSON zamiast sieci (do testow)")
    ap.add_argument("--dane", help="katalog z danymi zamiast data/ (do testow)")
    a = ap.parse_args()

    global DANE
    if a.dane:
        DANE = Path(a.dane).resolve()

    mapa = {k: v for k, v in json.loads(MAPA.read_text()).items() if not k.startswith("_")}
    zrodlo = json.loads(Path(a.zrodlo).read_text()) if a.zrodlo else None
    dzis = dt.date.today()

    print(f"{'ticker':10} {'symbol':10} {'nowych':>7}  status")
    print("-" * 78)
    gotowe = odrzucone = brak_symbolu = 0
    for ticker, symbol in sorted(mapa.items()):
        p = plik_tickera(ticker)
        if p is None:
            print(f"{ticker:10} {'-':10} {'':>7}  brak pliku w data/")
            continue
        if not symbol:
            brak_symbolu += 1
            print(f"{ticker:10} {'?':10} {'':>7}  brak symbolu w yahoo_symbols.json")
            continue

        nasze = wczytaj_stooq(p)
        ostatni = max(nasze)
        od = dt.date(int(ostatni[:4]), int(ostatni[4:6]), int(ostatni[6:])) - dt.timedelta(days=a.okno * 2)
        try:
            obce = zrodlo[symbol] if zrodlo else pobierz_yahoo(symbol, od, dzis)
        except Exception as e:                       # noqa: BLE001 - chcemy KAZDY blad przy tickerze
            odrzucone += 1
            print(f"{ticker:10} {symbol:10} {'':>7}  nie pobrano: {type(e).__name__}: {e}")
            continue

        ok, kurs, powod = sprawdz(nasze, obce, a.okno)
        if not ok:
            odrzucone += 1
            print(f"{ticker:10} {symbol:10} {'':>7}  ODRZUCONY: {powod}")
            continue

        nowe = {d: obce[d] / kurs for d in obce if d > ostatni}
        skala = "" if abs(kurs - 1) < 1e-9 else f", przeliczone /{kurs:.4f}"
        if not a.zapisz:
            gotowe += 1
            print(f"{ticker:10} {symbol:10} {len(nowe):>7}  do doklejenia{skala}")
            continue
        n = dopisz(p, nowe)
        gotowe += 1
        print(f"{ticker:10} {symbol:10} {n:>7}  dopisane{skala}")

    print("-" * 78)
    print(f"przeszlo sita: {gotowe}, odrzuconych: {odrzucone}, bez symbolu: {brak_symbolu}")
    if not a.zapisz:
        print("\nTo byl tylko podglad. Zeby naprawde dokleic: --zapisz")
    elif gotowe:
        print("\nTeraz: python3 tools/build_signals.py && python3 tools/build_prices.py "
              "&& python3 tools/build_performance.py")
    return 0 if not odrzucone else 1


if __name__ == "__main__":
    raise SystemExit(main())
