"""
Zamienia wyjscie silnika na web/data/signals.json - plik, ktory czyta strona.

Strona nic nie liczy. Liczy silnik w Pythonie, a tu tylko tlumaczymy jego wynik
na ksztalt, ktorego oczekuje front: wagi na walory wykonawcze, tryb kazdej nogi,
historia zmian i diagnostyka (ranking, kanarek, bramki).

Kapital stoi w DWOCH transzach - 10-tego i 25-tego - wiec liczymy dwie osobne
pary strategii (best17_a_day{N} + gpm_uk_day{N}) i publikujemy dwa sygnaly.
Transze nie moga isc w jednym combined_spec: `fixed_capital_weights` dla daty,
ktorej dana skladowa nie ma, wstawia PELNA GOTOWKE, wiec zmieszanie dnia 10 i 25
dawaloby portfel, ktory dwa razy w miesiacu "sprzedaje" polowe samego siebie.

Diagnostyka liczy sie TYMI SAMYMI funkcjami silnika, co sygnal - nie wlasnymi
kopiami wzorow - zeby nie dalo sie jej rozjechac ze skladem.

    python3 tools/build_signals.py
    python3 tools/build_signals.py --okresow 16
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # import silnika z korzenia repo
sys.path.insert(0, str(Path(__file__).resolve().parent))         # wspolne narzedzia

import pandas as pd

from engine_v2.combined_pipeline import load_combined_daily_prices
from engine_v2.combined_spec import CombinedSpec
from engine_v2.period_anchor import nth_trading_day_dates
from engine_v2.pipeline import _lookup, _run_phase_a, run_strategy_pipeline
from engine_v2.spec import StrategySpec
from wspolne import zapisz_jesli_zmiana

ROOT = Path(__file__).resolve().parent.parent
WYJSCIE = ROOT / "web" / "data" / "signals.json"
NOGI = {"best17": "best17_a", "gpm": "gpm_uk"}
TRANSZE = (10, 25)          # dni rebalansu: polowa kapitalu na kazdy
MIESIECY_KANARKA = 24

# Sygnaly best17 licza sie na tickerach US, ale kupujesz odpowiedniki z Londynu.
WYKONANIE = {"xlk.us": "IUIT", "ivv.us": "CSPX", "vt.us": "VWRA",
             "iau.us": "IGLN", "dbc.us": "CMOD"}


def wykonawczy(t: str) -> str:
    return WYKONANIE.get(t) or t.split(".")[0].upper()


def wagi(wiersz) -> dict[str, float]:
    surowe = json.loads(wiersz["weights_used_json"])
    out: dict[str, float] = {}
    for t, w in surowe.items():
        if t == "_CASH" or w <= 1e-9:
            continue
        k = wykonawczy(t)
        out[k] = round(out.get(k, 0.0) + w, 10)
    return out


def pp(x: float) -> str:
    """Roznica w punktach procentowych, ze znakiem - tak jak pokazuje ja strona."""
    return ("+" if x >= 0 else "−") + f"{abs(x):.2f}".replace(".", ",") + " pp"


def proc(x: float) -> str:
    return ("+" if x >= 0 else "−") + f"{abs(x):.2f}".replace(".", ",") + "%"


def zdatnosc_na_dzien(spec: StrategySpec, market_data, wskazniki, d):
    """Zdatnosc kazdego tickera na dzien `d`, ale FILTR PO FILTRZE.

    Silnik laczy maski filtrow przez AND. Jesli ktorys filtr nie ma wiersza na dana
    date (np. bramka 3m liczy sie z ceny Z DNIA REBALANSU, a tego notowania jeszcze
    nie ma), cale AND dla tej daty schodzi do False - czyli KAZDY walor wyglada na
    odciety, nawet ten, ktorego wlasne warunki sa spelnione. W sygnale to daje CASH.
    Tu rozdzielamy jedno od drugiego: `False` to realne odciecie, `None` to brak
    danych, ktory dopiero zdecyduje."""
    stan: dict[str, object] = {t: True for t in spec.universe}
    for _key, cfg in spec.base_params.get("asset_filters", {}).items():
        cfg = dict(cfg)
        maska = _lookup("asset_filters", cfg.pop("impl"))(market_data, wskazniki, cfg)
        zakres = cfg.get("assets") or cfg.get("target_assets") or spec.universe
        if zakres == "all":
            zakres = spec.universe
        if d not in maska.index:
            for t in zakres:
                if stan.get(t) is True:
                    stan[t] = None
            continue
        wiersz = maska.loc[d]
        for t in spec.universe:
            v = wiersz.get(t)
            if v is None or v != v:          # NaN
                if stan.get(t) is True:
                    stan[t] = None
            elif not bool(v):
                stan[t] = False
    return stan


def diagnostyka_best17(spec: StrategySpec, data: str, wagi_exec: dict[str, float]) -> dict:
    """Ranking, kanarek i bramki - policzone TYMI SAMYMI funkcjami silnika, ktore
    produkuja sygnal (_run_phase_a -> te same wskazniki, te same filtry z rejestru).
    Nic nie jest tu liczone drugi raz "po swojemu", wiec diagnostyka nie moze
    rozjechac sie ze skladem."""
    market_data, wskazniki, _score, _tw = _run_phase_a(spec)

    filtry = spec.base_params.get("asset_filters", {})
    kanarki = filtry["canary"]["canary_assets"]
    prog_kanarka = filtry["canary"]["bad_threshold"] * 100
    klucz_kanarka = filtry["canary"]["indicator_key"]
    # Bramki aktywowe: pojedynczy ticker, prog na wlasnym momentum (iau_gate, dbc_gate).
    bramki = {cfg["assets"][0]: cfg for k, cfg in filtry.items()
              if k.endswith("_gate") and cfg["impl"] == "indicator_positive"
              and len(cfg.get("assets", [])) == 1}
    prog_bramki = next(iter(bramki.values()))["threshold"] * 100 if bramki else 1.0

    d = pd.Timestamp(data)
    klucz_score = next(iter(spec.base_params["asset_scoring"]["weights"]))
    score_wiersz = wskazniki[klucz_score].loc[d]
    stan = zdatnosc_na_dzien(spec, market_data, wskazniki, d)

    ranking = []
    for t in spec.universe:
        v = score_wiersz.get(t)
        if v is None or v != v:
            continue
        if t in kanarki and t not in filtry["canary"]["target_assets"]:
            bramka = "canary"            # gauge, nigdy nie kupowany z rankingu
        else:
            bramka = {True: "ok", False: "no", None: "nodata"}[stan.get(t)]
        ranking.append({
            "t": t.split(".")[0].upper(),
            "exec": wykonawczy(t),       # sygnal liczy sie na US, kupujesz linie z Londynu
            "score": round(float(v) * 100, 2),
            "gate": bramka,
            "weight": round(wagi_exec.get(wykonawczy(t), 0.0), 6),
        })
    ranking.sort(key=lambda r: -r["score"])
    czeka = [r["t"] for r in ranking if r["gate"] == "nodata"]

    # --- kanarek: pelny przebieg wskaznika dla obu gauge'ow ---------------
    seria = wskazniki[klucz_kanarka].loc[:d, kanarki].dropna().tail(MIESIECY_KANARKA)
    kanarek = {
        "threshold": round(prog_kanarka, 2),
        "months": [x.strftime("%Y-%m") for x in seria.index],
    }
    for t in kanarki:
        kanarek[t.split(".")[0]] = [round(float(v) * 100, 2) for v in seria[t]]

    # --- progi: o ile naprawde blisko jest kazda decyzja -------------------
    progi = []
    zdatne = [r for r in ranking if r["gate"] == "ok"]
    if len(zdatne) >= 2:
        progi.append({"status": "ok", "title": f"{zdatne[0]['t']} przed {zdatne[1]['t']}",
                      "sub": "przewaga w rankingu",
                      "value": pp(zdatne[0]["score"] - zdatne[1]["score"])})
    if len(zdatne) >= 3:
        progi.append({"status": "ok", "title": f"{zdatne[1]['t']} utrzymuje 2. miejsce",
                      "sub": f"nad {zdatne[2]['t']}, pierwszym poza podium",
                      "value": pp(zdatne[1]["score"] - zdatne[2]["score"])})
    for t in bramki:
        seria_bramki = wskazniki[bramki[t]["indicator_key"]][t]
        krotki = t.split(".")[0].upper()
        if d not in seria_bramki.index or seria_bramki.loc[d] != seria_bramki.loc[d]:
            # Bramka liczy sie z ceny Z DNIA REBALANSU - dopoki to notowanie nie
            # przyjdzie, silnik traktuje walor jako niezdatny. To nie jest ocena
            # momentum, tylko brak danych, i tak to trzeba pokazac.
            progi.append({"status": "no", "title": f"{krotki} bez bramki 3m",
                          "sub": "brak notowania z dnia rebalansu - silnik odcina walor",
                          "value": "brak danych"})
            continue
        m = float(seria_bramki.loc[d]) * 100
        przeszlo = m > prog_bramki
        progi.append({"status": "ok" if przeszlo else "no",
                      "title": f"{krotki} {'nad' if przeszlo else 'pod'} bramką 3m",
                      "sub": f"momentum {proc(m)} wobec progu {proc(prog_bramki)}",
                      "value": pp(m - prog_bramki)})
    for t in kanarki:
        v = float(wskazniki[klucz_kanarka].loc[d, t]) * 100
        progi.append({"status": "nr" if v > prog_kanarka else "no",
                      "title": f"Kanarek {t.split('.')[0].upper()}",
                      "sub": f"{proc(v)} wobec progu {proc(prog_kanarka)}",
                      "value": pp(v - prog_kanarka)})

    return {"ranking": ranking, "gate_threshold": round(prog_bramki, 2),
            "canary": kanarek, "progi": progi, "pending": czeka}


def diagnostyka_gpm(spec: StrategySpec, data: str) -> list[list[str]]:
    """Szerokosc rynku i podzial ryzyko/ochrona - odtworzone z tego samego `score`,
    ktorym karmi sie gpm_breadth_protective_split."""
    _md, _ind, score, _tw = _run_phase_a(spec)
    p = spec.base_params["portfolio_risk_engine"]
    ryzykowne, ochronne = p["risky_assets"], p["protective_assets"]
    d = pd.Timestamp(data)

    s = score.loc[d, ryzykowne]
    n = int((s > 0).sum())
    if n <= int(p.get("full_protective_max_n", 6)):
        udzial = 1.0
    else:
        udzial = max(0.0, min(1.0, (len(ryzykowne) - n) / float(p["protective_scale_denominator"])))

    top = list(s.dropna().sort_values(ascending=False).index[: int(p.get("top_n_risky", 3))])
    so = score.loc[d, ochronne].dropna()
    best = wykonawczy(so.idxmax()) if not so.empty else "—"

    return [
        [f"Ryzykowne w top {int(p.get('top_n_risky', 3))}", " · ".join(wykonawczy(t) for t in top)],
        ["Przeszło filtr trendu", f"{n} z {len(ryzykowne)}"],
        ["Mianownik", str(int(p["protective_scale_denominator"]))],
        ["Udział ochronny", f"{round(udzial * 100)}% · {best}" if udzial else "0%"],
    ]


def transza(baza: Path, dzien: int, okresow: int) -> dict:
    """Jedna transza: obie nogi na TYM SAMYM dniu wykonania, plus realne daty transakcji.

    Silnik etykietuje kazdy okres poczatkiem miesiaca NIEZALEZNIE od dnia wykonania (patrz
    engine_v2/period_anchor.py), wiec sama etykieta nie mowi, kiedy transza faktycznie
    kupowala. Realna date bierzemy z `nth_trading_day_dates` na tym samym kalendarzu, na
    ktorym liczy polaczona strategia."""
    przebiegi, specy = {}, {}
    for noga, katalog in NOGI.items():
        spec = StrategySpec.load(baza / f"{katalog}_day{dzien}" / "strategy_spec.json")
        przebiegi[noga] = run_strategy_pipeline(spec)
        specy[noga] = spec  # bloki juz rozwiazane przez run_strategy_pipeline

    kat = baza / f"gpm_uk_best17_a_day{dzien}"
    cs = CombinedSpec.load(kat / "combined_spec.json")
    daty = nth_trading_day_dates(load_combined_daily_prices(cs, kat).index, dzien)

    etykiety = sorted(set(d.strftime("%Y-%m-%d") for d in przebiegi["gpm"]["date"])
                      & set(d.strftime("%Y-%m-%d") for d in przebiegi["best17"]["date"]))
    idx = {n: {d.strftime("%Y-%m-%d"): i for i, d in enumerate(pf["date"])}
           for n, pf in przebiegi.items()}

    sklad, czekaja = [], []
    for e in etykiety[-(okresow + 6):]:
        data = daty.get(pd.Timestamp(e))
        if data is None or pd.isna(data):
            czekaja.append({"tranche": dzien, "period": e,
                            "reason": "miesiac nie ma jeszcze zadnego notowania"})
            continue
        if data.day < dzien:
            # Anchor nie znalazl sesji na/po {dzien}-tym i cofnal sie do ostatniej dostepnej -
            # czyli miesiac jest urwany na danych. To NIE jest kurs z dnia rebalansu, wiec
            # takiego okresu nie wolno opublikowac jako sygnalu.
            czekaja.append({"tranche": dzien, "period": e, "last": data.strftime("%Y-%m-%d"),
                            "reason": f"brak sesji {dzien}-tego lub pozniej - dane koncza sie "
                                      f"na {data.strftime('%Y-%m-%d')}"})
            continue
        sklad.append({"date": data.strftime("%Y-%m-%d"), "period": e, "tranche": dzien,
                      **{noga: wagi(pf.iloc[idx[noga][e]]) for noga, pf in przebiegi.items()}})

    if not sklad:
        raise SystemExit(f"transza {dzien}: zaden okres nie ma kursu z dnia rebalansu "
                         f"({len(czekaja)} czeka) - nie ma czego opublikowac.")
    sklad = sklad[-okresow:]
    print(f"transza {dzien:2}: {len(sklad)} okresow, ostatni {sklad[-1]['date']} "
          f"(etykieta {sklad[-1]['period']}), czeka {len(czekaja)}")
    return {"sklad": sklad, "czekaja": czekaja, "specy": specy}


def tryb(wpis: dict, noga: str) -> str:
    return "RISK" if wpis[noga] else "CASH"


def sygnal(wpis: dict) -> dict:
    return {
        "date": wpis["date"], "period": wpis["period"], "tranche": wpis["tranche"],
        "best17": {"mode": tryb(wpis, "best17"),
                   "picks": sorted(wpis["best17"], key=lambda k: -wpis["best17"][k]),
                   "weights": wpis["best17"]},
        "gpm": {"mode": tryb(wpis, "gpm"), "weights": wpis["gpm"]},
    }


def opis_zmiany(teraz: dict, poprz: dict | None) -> str:
    if poprz is None:
        return "pierwszy okres"
    if teraz["best17"] == poprz["best17"] and teraz["gpm"] == poprz["gpm"]:
        return "bez zmian"
    teraz_t = set(teraz["best17"]) | set(teraz["gpm"])
    poprz_t = set(poprz["best17"]) | set(poprz["gpm"])
    return " · ".join(filter(None, [
        ("+ " + ", ".join(sorted(teraz_t - poprz_t))) if teraz_t - poprz_t else "",
        ("− " + ", ".join(sorted(poprz_t - teraz_t))) if poprz_t - teraz_t else ""])) or "zmiana wag"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--okresow", type=int, default=12)
    ap.add_argument("--specs", help="katalog z kopiami strategii (np. z sync_prices.py)")
    a = ap.parse_args()

    baza = Path(a.specs) if a.specs else ROOT / "strategies_v2"
    T = {dzien: transza(baza, dzien, a.okresow) for dzien in TRANSZE}

    sygnaly = [sygnal(T[dzien]["sklad"][-1]) for dzien in TRANSZE]
    czekaja = [c for dzien in TRANSZE for c in T[dzien]["czekaja"]]

    # Historia: obie transze w jednym strumieniu, bo tak to wyglada na rachunku - ale
    # "co sie zmienilo" liczy sie ZAWSZE wzgledem poprzedniego okresu TEJ SAMEJ transzy.
    wszystkie = []
    for dzien in TRANSZE:
        s = T[dzien]["sklad"]
        for i, w in enumerate(s):
            wszystkie.append((w, s[i - 1] if i else None))
    wszystkie.sort(key=lambda x: x[0]["date"], reverse=True)
    historia = [[w["date"], w["tranche"], tryb(w, "best17"),
                 " / ".join(sorted(w["best17"], key=lambda k: -w["best17"][k])) or "—",
                 tryb(w, "gpm"), opis_zmiany(w, p)]
                for w, p in wszystkie[:8]]

    diagnostyka = {}
    for dzien in TRANSZE:
        ost = T[dzien]["sklad"][-1]
        d = diagnostyka_best17(T[dzien]["specy"]["best17"], ost["period"], ost["best17"])
        d["gpm_info"] = diagnostyka_gpm(T[dzien]["specy"]["gpm"], ost["period"])
        d["date"] = ost["date"]
        diagnostyka[str(dzien)] = d

    stare = json.loads(WYJSCIE.read_text()) if WYJSCIE.exists() else {}
    wynik = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "engine_v2 / " + " + ".join(f"strategies_v2/gpm_uk_best17_a_day{d}" for d in TRANSZE),
        "config_hash": hashlib.sha256(b"".join(
            (ROOT / "strategies_v2" / f"gpm_uk_best17_a_day{d}" / "combined_spec.json").read_bytes()
            for d in TRANSZE)).hexdigest()[:8],
        "universe": stare.get("universe", []),
        "roles": stare.get("roles", {}),
        "tranches": list(TRANSZE),
        "signals": sygnaly,
        "awaiting": czekaja,
        "history": historia,
        # Diagnostyka liczona tymi samymi funkcjami silnika, co sygnal - patrz
        # diagnostyka_best17 / diagnostyka_gpm.
        "diagnostics": diagnostyka,
        "composition": sorted((w for dzien in TRANSZE for w in T[dzien]["sklad"]),
                              key=lambda w: w["date"]),
    }
    zapisz_jesli_zmiana(WYJSCIE, wynik)
    print(f"\n{WYJSCIE.relative_to(ROOT)}: {len(wynik['composition'])} okresow "
          f"({len(TRANSZE)} transze), hash configu {wynik['config_hash']}")
    for s in sygnaly:
        print(f"  transza {s['tranche']:2}  {s['date']}  BEST17 {s['best17']['mode']:4} {s['best17']['weights']}")
        print(f"                           GPM    {s['gpm']['mode']:4} {s['gpm']['weights']}")
    for c in czekaja:
        print(f"  czeka: transza {c['tranche']}, okres {c['period']} - {c['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
