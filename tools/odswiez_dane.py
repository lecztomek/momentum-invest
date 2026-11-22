"""
Odswieza pliki notowan z nowszej paczki: szuka w ZRODLE plikow o tych samych
nazwach, co w CELU, i podmienia te, ktore sa nowsze. Oba katalogi przeszukuje
rekurencyjnie, a plik laduje TAM, GDZIE LEZAL w celu - uklad podkatalogow celu
zostaje nietkniety.

Bierze pod uwage tylko pliki, ktore JUZ sa w celu. Paczka ze stooq ma tysiace
tickerow; sciaganie ich wszystkich tylko zasmiecilo by repo.

"Nowszy" domyslnie znaczy NOWSZE NOTOWANIA, nie nowszy plik. Data pliku po
rozpakowaniu archiwum to data rozpakowania - wszystko wygladaloby wtedy na
nowsze, lacznie z paczka sprzed roku. Liczy sie ostatnia sesja w srodku.
Gdy pliku nie da sie sparsowac, skrypt mowi o tym wprost i porownuje czas
modyfikacji (albo --wg-czasu, zeby robil tak zawsze).

    python3 tools/odswiez_dane.py ~/pobrane/d_us_txt            # podglad
    python3 tools/odswiez_dane.py ~/pobrane/d_us_txt --zapisz   # podmienia
    python3 tools/odswiez_dane.py ~/paczka --cel data/uk --przenies --zapisz
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def ostatnia_sesja(sciezka: Path) -> str | None:
    """Ostatnia data w pliku stooq (kolumna 3, format YYYYMMDD). None = nie ten
    format, nie zgadujemy."""
    try:
        linie = sciezka.read_text(errors="replace").splitlines()
    except OSError:
        return None
    for w in reversed(linie[1:] if len(linie) > 1 else []):
        czesci = w.split(",")
        if len(czesci) > 2 and czesci[2].isdigit() and len(czesci[2]) == 8:
            return czesci[2]
    return None


def nowszy(zrodlo: Path, cel: Path, wg_czasu: bool) -> tuple[bool, str]:
    """(czy podmieniac, opis dla czlowieka)."""
    if wg_czasu:
        a, b = zrodlo.stat().st_mtime, cel.stat().st_mtime
        return a > b, f"plik {'nowszy' if a > b else 'nie nowszy'} o {abs(a-b)/86400:.1f} dnia"

    z, c = ostatnia_sesja(zrodlo), ostatnia_sesja(cel)
    if z is None or c is None:
        a, b = zrodlo.stat().st_mtime, cel.stat().st_mtime
        return a > b, "nie czytam dat w srodku, biore czas pliku"
    if z > c:
        return True, f"{c} -> {z}"
    if z == c:
        return False, f"to samo ({c})"
    return False, f"ZRODLO STARSZE ({z} < {c}), pomijam"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("zrodlo", help="katalog z nowa paczka (przeszukiwany rekurencyjnie)")
    ap.add_argument("--cel", default="data", help="katalog do odswiezenia (domyslnie data/)")
    ap.add_argument("--wzorzec", default="*.txt", help="jakie pliki brac pod uwage")
    ap.add_argument("--zapisz", action="store_true", help="bez tego tylko pokazuje, co by zrobil")
    ap.add_argument("--przenies", action="store_true", help="przenosi zamiast kopiowac")
    ap.add_argument("--wg-czasu", action="store_true", help="porownuj czas pliku, nie daty w srodku")
    a = ap.parse_args()

    zrodlo = Path(a.zrodlo).expanduser().resolve()
    cel = Path(a.cel).expanduser()
    if not cel.is_absolute():
        cel = (ROOT / cel).resolve()
    for p, opis in ((zrodlo, "zrodlo"), (cel, "cel")):
        if not p.is_dir():
            raise SystemExit(f"{opis} nie jest katalogiem: {p}")
    if zrodlo == cel:
        raise SystemExit("zrodlo i cel to ten sam katalog")

    # W zrodle moga byc duplikaty tej samej nazwy w roznych podkatalogach -
    # bierzemy ten z najnowszymi notowaniami i mowimy, ze bylo ich wiecej.
    w_zrodle: dict[str, list[Path]] = {}
    for p in zrodlo.rglob(a.wzorzec):
        if p.is_file():
            w_zrodle.setdefault(p.name, []).append(p)

    pliki_celu = sorted((p for p in cel.rglob(a.wzorzec) if p.is_file()), key=lambda q: q.name)
    if not pliki_celu:
        raise SystemExit(f"w celu nie ma zadnego pliku pasujacego do {a.wzorzec}")

    print(f"zrodlo: {zrodlo}  ({len(w_zrodle)} unikalnych nazw)")
    print(f"cel:    {cel}  ({len(pliki_celu)} plikow)\n")
    print(f"{'plik':22} {'decyzja':10} szczegoly")
    print("-" * 78)

    podmienione = pominiete = brakujace = 0
    for p_cel in pliki_celu:
        kandydaci = w_zrodle.get(p_cel.name, [])
        if not kandydaci:
            brakujace += 1
            print(f"{p_cel.name:22} {'brak':10} nie ma w zrodle")
            continue
        p_zrod = max(kandydaci, key=lambda q: (ostatnia_sesja(q) or "", q.stat().st_mtime))
        ile = f" [{len(kandydaci)} kopii w zrodle]" if len(kandydaci) > 1 else ""
        bierz, czemu = nowszy(p_zrod, p_cel, a.wg_czasu)
        if not bierz:
            pominiete += 1
            print(f"{p_cel.name:22} {'pomijam':10} {czemu}{ile}")
            continue
        if a.zapisz:
            shutil.copy2(p_zrod, p_cel)
            if a.przenies:
                p_zrod.unlink()
        podmienione += 1
        print(f"{p_cel.name:22} {'PODMIEN' if not a.zapisz else 'zrobione':10} {czemu}{ile}")

    print("-" * 78)
    print(f"do podmiany: {podmienione}, bez zmian: {pominiete}, brak w zrodle: {brakujace}")
    if podmienione and not a.zapisz:
        print("\nTo byl podglad. Zeby naprawde "
              + ("przeniesc" if a.przenies else "skopiowac") + ": --zapisz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
