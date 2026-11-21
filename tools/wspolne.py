"""
Drobiazgi wspolne dla narzedzi pipeline'u.
"""
from __future__ import annotations

import json
from pathlib import Path


def zapisz_jesli_zmiana(sciezka: Path, wynik: dict, pomin=("generated",)) -> bool:
    """Zapisuje JSON tylko wtedy, gdy zmienila sie TRESC.

    Kazdy przebieg wstawia swiezy `generated`, wiec plik rozni sie od poprzedniego
    nawet gdy sygnal i ceny sa co do liczby identyczne. Gdyby to szlo do repo,
    codzienny workflow commitowalby szum, a historia pliku przestalaby cokolwiek
    znaczyc - "zmienilo sie" ma znaczyc, ze zmienily sie DANE."""
    bez = lambda d: {k: v for k, v in d.items() if k not in pomin}
    if sciezka.exists():
        try:
            if bez(json.loads(sciezka.read_text())) == bez(wynik):
                print(f"{sciezka.name}: bez zmian w danych - zostawiam plik bez ruszania")
                return False
        except json.JSONDecodeError:
            pass
    sciezka.write_text(json.dumps(wynik, indent=1, ensure_ascii=False))
    return True
