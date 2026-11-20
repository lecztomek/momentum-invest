"""
Zamienia wyjscie silnika na web/data/signals.json - plik, ktory czyta strona.

Strona nic nie liczy. Liczy silnik w Pythonie, a tu tylko tlumaczymy jego wynik
na ksztalt, ktorego oczekuje front: wagi na walory wykonawcze, tryb kazdej nogi
i historia zmian.

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

from engine_v2.pipeline import _lookup, _run_phase_a, run_strategy_pipeline
from engine_v2.spec import StrategySpec

ROOT = Path(__file__).resolve().parent.parent
WYJSCIE = ROOT / "web" / "data" / "signals.json"
NOGI = {"best17": "best17_a", "gpm": "gpm_uk"}
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

    import pandas as pd  # lokalnie: reszta pliku nie potrzebuje pandas

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
    import pandas as pd

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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--okresow", type=int, default=12)
    ap.add_argument("--specs", help="katalog z kopiami strategii (np. z sync_prices.py)")
    a = ap.parse_args()

    przebiegi, specy = {}, {}
    for noga, katalog in NOGI.items():
        baza = Path(a.specs) if a.specs else ROOT / "strategies_v2"
        spec = StrategySpec.load(baza / katalog / "strategy_spec.json")
        pf = run_strategy_pipeline(spec)
        przebiegi[noga] = pf
        specy[noga] = spec  # bloki juz rozwiazane przez run_strategy_pipeline
        print(f"{noga:8} {len(pf)} okresow, ostatni {pf.iloc[-1]['date'].date()}")

    daty = [d.strftime("%Y-%m-%d") for d in przebiegi["gpm"]["date"]]
    inne = [d.strftime("%Y-%m-%d") for d in przebiegi["best17"]["date"]]
    if daty[-len(inne):] != inne[-len(daty):]:
        wspolne = sorted(set(daty) & set(inne))
        print(f"UWAGA: nogi maja rozne daty rebalansu, biore {len(wspolne)} wspolnych")
        daty = wspolne

    idx = {n: {d.strftime("%Y-%m-%d"): i for i, d in enumerate(pf["date"])}
           for n, pf in przebiegi.items()}
    okresy = daty[-a.okresow:]

    sklad = []
    for d in okresy:
        wpis = {"date": d, "tranche": int(d[8:10])}
        for noga, pf in przebiegi.items():
            wpis[noga] = wagi(pf.iloc[idx[noga][d]])
        sklad.append(wpis)

    def tryb(noga: str, d: str) -> str:
        return "RISK" if sklad[[s["date"] for s in sklad].index(d)][noga] else "CASH"

    sygnaly = []
    for d in okresy[-2:][::-1]:
        s = sklad[[x["date"] for x in sklad].index(d)]
        sygnaly.append({
            "date": d, "tranche": s["tranche"],
            "best17": {"mode": tryb("best17", d),
                       "picks": sorted(s["best17"], key=lambda k: -s["best17"][k]),
                       "weights": s["best17"]},
            "gpm": {"mode": tryb("gpm", d), "weights": s["gpm"]},
        })

    historia = []
    for i in range(len(okresy) - 1, max(-1, len(okresy) - 7), -1):
        d = okresy[i]
        s = sklad[i]
        poprz = sklad[i - 1] if i else None
        if poprz is None:
            zmiana = "pierwszy okres"
        elif s["best17"] == poprz["best17"] and s["gpm"] == poprz["gpm"]:
            zmiana = "bez zmian"
        else:
            weszly = sorted((set(s["best17"]) | set(s["gpm"])) - (set(poprz["best17"]) | set(poprz["gpm"])))
            wyszly = sorted((set(poprz["best17"]) | set(poprz["gpm"])) - (set(s["best17"]) | set(s["gpm"])))
            zmiana = " · ".join(filter(None, [
                ("+ " + ", ".join(weszly)) if weszly else "",
                ("− " + ", ".join(wyszly)) if wyszly else ""])) or "zmiana wag"
        historia.append([d, tryb("best17", d),
                         " / ".join(sygnaly[0]["best17"]["picks"]) if i == len(okresy) - 1
                         else (" / ".join(sorted(s["best17"], key=lambda k: -s["best17"][k])) or "—"),
                         tryb("gpm", d), zmiana])

    ostatni = okresy[-1]
    diag = diagnostyka_best17(specy["best17"], ostatni, sklad[-1]["best17"])
    gpm_info = diagnostyka_gpm(specy["gpm"], ostatni)

    stare = json.loads(WYJSCIE.read_text()) if WYJSCIE.exists() else {}
    wynik = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "engine_v2 / strategies_v2/gpm_uk_best17_a",
        "config_hash": hashlib.sha256(
            (ROOT / "strategies_v2" / "gpm_uk_best17_a" / "combined_spec.json").read_bytes()
        ).hexdigest()[:8],
        "universe": stare.get("universe", []),
        "roles": stare.get("roles", {}),
        "signals": sygnaly,
        "history": historia,
        # Diagnostyka liczona tymi samymi funkcjami silnika, co sygnal - patrz
        # diagnostyka_best17 / diagnostyka_gpm.
        "pending": diag["pending"],
        "ranking": diag["ranking"],
        "gate_threshold": diag["gate_threshold"],
        "canary": diag["canary"],
        "progi": diag["progi"],
        "gpm_info": gpm_info,
        "composition": sklad,
    }
    WYJSCIE.write_text(json.dumps(wynik, indent=1, ensure_ascii=False))
    print(f"\nzapisano {WYJSCIE.relative_to(ROOT)}: {len(sklad)} okresow, "
          f"ostatni {okresy[-1]}, hash configu {wynik['config_hash']}")
    for s in sygnaly:
        print(f"  {s['date']}  BEST17 {s['best17']['mode']:4} {s['best17']['weights']}")
        print(f"              GPM    {s['gpm']['mode']:4} {s['gpm']['weights']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
