"""
Wystawia do web/data/performance.json HISTORIE STRATEGII - miesiac po miesiacu.

Liczy ja silnik, nie panel. Portfel to dwie rowne transze (10-tego i 25-tego),
wiec zwrot okresu to srednia zwrotow obu - dokladnie tak, jak traktuje "sleeve"
combiner w `combined_pipeline.py`: kazda transza jedzie swoj wlasny, pelny
pipeline, a kapital dzieli sie miedzy nie po polowie.

Zwroty sa PO KOSZTACH TRANSAKCYJNYCH (40 bps siedzi w bloku `execution` obu
strategii) i PRZED PODATKIEM. Sa tez w WALUCIE NOTOWAN - silnik liczy je ze
stosunku cen, nie przelicza niczego na zlote, wiec nazywanie tego "PLN" byloby
nieprawda.

Transza nie konczy miesiaca tam, gdzie kalendarz: okres transzy 10-tego biegnie
od 10-tego do 10-tego. Etykieta miesiaca mowi, KTOREGO miesiaca jest ten okres,
nie ze pokrywa go co do dnia.

    python3 tools/build_performance.py
    python3 tools/build_performance.py --specs /tmp/ws/strategies_v2
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # import silnika z korzenia repo
sys.path.insert(0, str(Path(__file__).resolve().parent))         # wspolne narzedzia

import pandas as pd

from engine_v2.backtest_engine import daily_equity_curve
from engine_v2.combined_pipeline import (find_combined_valid_window_start,
                                          load_combined_daily_prices, run_combined_pipeline)
from engine_v2.combined_spec import CombinedSpec
from engine_v2.metrics import compute_metrics
from engine_v2.pipeline import _lookup
from engine_v2.spec import StrategySpec
from engine_v2.period_anchor import nth_trading_day_dates
from wspolne import zapisz_jesli_zmiana

ROOT = Path(__file__).resolve().parent.parent
WYJSCIE = ROOT / "web" / "data" / "performance.json"
TRANSZE = (10, 25)              # musi zgadzac sie z tools/build_signals.py
MIESIECY_MIKSU = 24

# Benchmark: UK-listowane ETF-y klasy Acc, te same, ktore user realnie kupuje.
# NIE surowe spy.us/vt.us z data/us - tamte sa bez reinwestycji dywidend (patrz
# docstring dividend_adjusted_csv_loader), wiec zanizalyby benchmark o cala stope
# dywidendy i porownanie wychodzilo by za ladnie dla strategii.
BENCHMARKI = [
    {"key": "cspx", "ticker": "cspx.uk", "label": "S&P 500", "note": "CSPX, Acc"},
    {"key": "vwra", "ticker": "vwra.uk", "label": "Świat", "note": "VWRA, Acc"},
]

# Klasa aktywa wprost z mapowania, ktore repo juz ma (uk_ticker_mapping.json przy
# strategiach) - nie zgadujemy, co to za ETF: cspx=SPY, cndx=QQQ, eimi=VWO,
# xres=VNQ (REIT), iues=XLE (energia), ihya=HYG, lqda=LQD, dtla=TLT, cbu0=IEF,
# ibta=SHY, igln=GLD, cmod=DBC, iuit=XLK, vwra=VT.
KLASY = [["Tech", "--s1"], ["Akcje pozostałe", "--s2"], ["Surowce", "--s3"],
         ["Złoto", "--s4"], ["Obligacje", "--s5"], ["Gotówka", "--s6"]]
KLASA = {
    "xlk.us": 0, "iuit.uk": 0, "cndx.uk": 0,
    "ivv.us": 1, "vt.us": 1, "cspx.uk": 1, "vwra.uk": 1, "eimi.uk": 1, "iues.uk": 1, "xres.uk": 1,
    "dbc.us": 2, "cmod.uk": 2, "icom.uk": 2,
    "iau.us": 3, "igln.uk": 3,
    "ihya.uk": 4, "lqda.uk": 4, "dtla.uk": 4, "cbu0.uk": 4, "ibta.uk": 4,
    "_CASH": 5,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--specs", help="katalog z kopiami strategii (np. z sync_prices.py)")
    ap.add_argument("--od", default="2008", help="pierwszy rok historii")
    a = ap.parse_args()

    baza = Path(a.specs) if a.specs else ROOT / "strategies_v2"
    zwroty, wagi, krzywe, obroty = {}, {}, {}, {}
    for dzien in TRANSZE:
        kat = baza / f"gpm_uk_best17_a_day{dzien}"
        cs = CombinedSpec.load(kat / "combined_spec.json")
        pf = run_combined_pipeline(cs, kat)
        s = pf.set_index("date")["net_return"]

        # POCZATEK: dopiero stamtad obie nogi naprawde handluja. Wczesniej combiner
        # trzyma brakujaca noge w gotowce (gpm_uk ma dane dopiero od 2018), wiec
        # liczby z tamtego okresu nie sa wynikiem TEGO portfela - silnik liczy swoje
        # metryki tak samo, patrz find_combined_valid_window_start.
        poczatek = find_combined_valid_window_start(cs, kat)

        # KONIEC: zwrot okresu potrzebuje DWOCH kursow - z dnia rebalansu i z dnia
        # nastepnego rebalansu. Brakuje ktoregos, silnik konczy z gross_return 0, co
        # wyglada jak "miesiac na zero", a jest "miesiac nieznany". Takiego okresu nie
        # publikujemy, tak samo jak nie publikujemy z niego sygnalu.
        dzienne = load_combined_daily_prices(cs, kat)
        daty = nth_trading_day_dates(dzienne.index, dzien)
        finalne = {e for e in s.index if e in daty.index and daty[e].day >= dzien}
        kolejne = list(s.index)
        pelne = [e for i, e in enumerate(kolejne)
                 if e >= poczatek and e in finalne
                 and i + 1 < len(kolejne) and kolejne[i + 1] in finalne]
        zwroty[dzien] = s.loc[pelne]
        wagi[dzien] = pf.set_index("date")["weights_used_json"].loc[pelne]

        # Metryki (CAGR, MaxDD, Sharpe) licza sie z DZIENNEJ krzywej kapitalu, nie z
        # miesiecznych zwrotow - inaczej obsuniecie w srodku miesiaca znika i MaxDD
        # wychodzi plytsze niz bylo naprawde.
        okno = pf[pf["date"].isin(pelne)]
        kr = daily_equity_curve(okno, dzienne, {"execution_day_of_month": dzien})
        kr = kr[(kr["date"] >= daty[pelne[0]]) & (kr["date"] <= daty[pelne[-1]])]
        krzywe[dzien] = kr.set_index("date")["equity"]
        obroty[dzien] = okno.set_index("date")["turnover"]
        print(f"transza {dzien:2}: {len(pf)} okresow silnika -> {len(pelne)} publikowanych, "
              f"{pelne[0].date()} .. {pelne[-1].date()} (obie nogi realne od {poczatek.date()})")

    # Portfel = polowa kapitalu w kazdej transzy. Okres, ktorego ktoras transza
    # jeszcze nie ma (inna rozgrzewka), liczymy po tej, ktora go ma - udawanie
    # zera byloby wymyslaniem wyniku.
    wspolny = sorted(set().union(*(s.index for s in zwroty.values())))
    seria = pd.Series(
        [pd.Series([zwroty[d].get(x) for d in TRANSZE]).dropna().mean() for x in wspolny],
        index=pd.DatetimeIndex(wspolny),
    ).dropna()
    seria = seria[seria.index.year >= int(a.od)]

    miesieczne: dict[str, list] = {}
    for data, r in seria.items():
        rok = str(data.year)
        miesieczne.setdefault(rok, [None] * 12)[data.month - 1] = round(float(r) * 100, 2)

    # Miks klas aktywow STRATEGII (nie portfela usera) - srednia obu transz, bo
    # kazda ma polowe kapitalu. Udzialy sumuja sie do 100 metoda najwiekszych
    # reszt, zeby kolumna nie wygladala na blad danych.
    mies_miksu = [x for x in wspolny if all(x in wagi[d].index for d in TRANSZE)][-MIESIECY_MIKSU:]
    miks = []
    for x in mies_miksu:
        udzial = [0.0] * len(KLASY)
        for d in TRANSZE:
            for ticker, w in json.loads(wagi[d][x]).items():
                if w > 1e-9:
                    udzial[KLASA[ticker]] += w / len(TRANSZE)
        setne = [u * 100 for u in udzial]
        calosc = [int(v) for v in setne]
        reszta = 100 - sum(calosc)
        for i in sorted(range(len(setne)), key=lambda i: -(setne[i] - calosc[i]))[:max(0, reszta)]:
            calosc[i] += 1
        miks.append(calosc)

    # Kapital portfela = polowa w kazdej transzy. Skladamy DZIENNE krzywe obu i
    # dopiero z tego liczymy metryki - ta sama funkcja silnika, co w raportach.
    dni = sorted(set().union(*(k.index for k in krzywe.values())))
    znorm = [k.reindex(dni).ffill().bfill() / k.iloc[0] for k in krzywe.values()]
    kapital = sum(znorm) / len(znorm)
    equity = pd.DataFrame({"date": dni, "equity": kapital.values})
    obrot = pd.DataFrame({"date": wspolny,
                          "turnover": [pd.Series([obroty[d].get(x) for d in TRANSZE]).dropna().mean()
                                       for x in wspolny]})
    metryki = compute_metrics(equity, obrot, {})
    metryki["multiple"] = float(kapital.iloc[-1] / kapital.iloc[0])
    metryki["from"] = dni[0].strftime("%Y-%m-%d")
    metryki["to"] = dni[-1].strftime("%Y-%m-%d")

    # Krzywa obsuniecia do wykresu - probkowana tygodniowo, zeby plik nie puchl,
    # ale liczona z DZIENNEJ krzywej, wiec dolki sa prawdziwe.
    szczyt = kapital.cummax()
    obs = (kapital / szczyt - 1) * 100
    tyg = obs.resample("W").min().dropna()

    # --- benchmarki: kup i trzymaj w tym samym oknie co strategia --------
    spec_uk = StrategySpec.load(baza / f"gpm_uk_day{TRANSZE[0]}" / "strategy_spec.json")
    loader = _lookup("data_loader", spec_uk.blocks["data_loader"])
    cleaner = _lookup("data_cleaner", spec_uk.blocks["data_cleaner"])
    bench_params = {**spec_uk.base_params.get("data_loader", {}), "frequency": "daily"}

    benchmarki = []
    for b in BENCHMARKI:
        md = loader([b["ticker"]], bench_params)
        ceny = cleaner(md, spec_uk.base_params.get("data_cleaner", {})).prices[b["ticker"]]
        ceny = ceny.reindex(dni).ffill()
        ceny = ceny.loc[ceny.first_valid_index():].dropna()
        if len(ceny) < 60:
            print(f"benchmark {b['key']}: za malo danych w oknie, pomijam")
            continue
        kr = ceny / ceny.iloc[0]
        eq = pd.DataFrame({"date": kr.index, "equity": kr.values})
        m = compute_metrics(eq, pd.DataFrame({"date": kr.index, "turnover": 0.0}), {})
        m["multiple"] = float(kr.iloc[-1])
        benchmarki.append({**b, "from": kr.index[0].strftime("%Y-%m-%d"),
                           "to": kr.index[-1].strftime("%Y-%m-%d"),
                           "pelne_okno": kr.index[0] == dni[0],
                           "metrics": {k: (round(v, 6) if isinstance(v, float) else v)
                                       for k, v in m.items()},
                           "_krzywa": kr})
        print(f"benchmark {b['key']:5}: {kr.index[0].date()} .. {kr.index[-1].date()}, "
              f"CAGR {m['cagr']*100:5.2f}%, MaxDD {m['max_drawdown']*100:6.2f}%, x{kr.iloc[-1]:.2f}")

    # Wspolna, tygodniowa os do wykresu. Benchmark, ktory zaczyna sie pozniej,
    # startuje od wartosci STRATEGII z tamtego dnia - inaczej jego krzywa wisialaby
    # w powietrzu i nie dalo by sie porownac ksztaltu.
    os_tyg = kapital.resample("W").last().dropna()
    porownanie = {"dates": [x.strftime("%Y-%m-%d") for x in os_tyg.index],
                  "strategy": [round(float(v), 4) for v in os_tyg]}
    for b in benchmarki:
        kr = b.pop("_krzywa")
        # Tygodniowa os konczy sie w niedziele, a notowania sa w dni handlowe -
        # samo reindex zgubiloby KAZDY punkt, wiec najpierw unia indeksow i ffill.
        kr_w = kr.reindex(kr.index.union(os_tyg.index)).ffill().reindex(os_tyg.index)
        skala = float(kapital.asof(kr.index[0]))
        porownanie[b["key"]] = [None if pd.isna(v) else round(float(v) * skala, 4) for v in kr_w]

    laczny = float((seria + 1).prod())
    lat = len(seria) / 12
    wynik = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "engine_v2 / " + " + ".join(f"gpm_uk_best17_a_day{d}" for d in TRANSZE),
        "currency": "waluta notowan",
        "net_of_costs": True,
        "pre_tax": True,
        "note": "polowa kapitalu w transzy 10-tego, polowa w 25-tego; okres transzy "
                "biegnie od jej dnia do jej dnia, nie od 1-szego do 1-szego",
        "months": int(len(seria)),
        "monthly": {rok: miesieczne[rok] for rok in sorted(miesieczne)},
        "metrics": {k: (round(v, 6) if isinstance(v, float) else v) for k, v in metryki.items()},
        "positive_months": round(float((seria > 0).mean()) * 100, 1),
        "drawdown": {"dates": [x.strftime("%Y-%m-%d") for x in tyg.index],
                     "dd": [round(float(v), 2) for v in tyg]},
        "benchmarks": benchmarki,
        "compare": porownanie,
        "classes": KLASY,
        "mix_months": [x.strftime("%Y-%m") for x in mies_miksu],
        "mix": miks,
    }
    zapisz_jesli_zmiana(WYJSCIE, wynik)
    print(f"\n{WYJSCIE.relative_to(ROOT)}: {len(seria)} miesiecy, {seria.index.min().date()} .. "
          f"{seria.index.max().date()}, mnoznik x{laczny:.2f}, CAGR {(laczny ** (1 / lat) - 1) * 100:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
