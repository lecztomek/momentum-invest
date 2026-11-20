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

from engine_v2.pipeline import run_strategy_pipeline
from engine_v2.spec import StrategySpec

ROOT = Path(__file__).resolve().parent.parent
WYJSCIE = ROOT / "web" / "data" / "signals.json"
NOGI = {"best17": "best17_a", "gpm": "gpm_uk"}

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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--okresow", type=int, default=12)
    a = ap.parse_args()

    przebiegi = {}
    for noga, katalog in NOGI.items():
        spec = StrategySpec.load(ROOT / "strategies_v2" / katalog / "strategy_spec.json")
        pf = run_strategy_pipeline(spec)
        przebiegi[noga] = pf
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
        # Ranking i kanarek to diagnostyka, ktorej silnik nie wystawia osobno -
        # do czasu jej wyliczenia zostaja przykladowe i sa tak oznaczone.
        "diagnostics_source": "przykladowe",
        "ranking": stare.get("ranking", []),
        "canary": stare.get("canary", {}),
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
