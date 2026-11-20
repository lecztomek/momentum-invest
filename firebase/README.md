# Firestore - reguly i testy

## Podzial danych

| Gdzie | Co | Kto pisze |
|---|---|---|
| repo, `web/data/*.json` | ceny opublikowane i sygnaly | pipeline w Actions |
| Firestore, `price_entries` | ceny wpisane recznie | admin z przegladarki |
| Firestore, `overrides` | korekty cen z powodem i autorem | admin z przegladarki |
| Firestore, `users/{uid}` | salda, wplaty, transakcje | wylacznie wlasciciel |
| Firestore, `admins/{uid}` | kto jest adminem | wylacznie konsola Firebase |

Dane publiczne ida przez repo, bo sa tylko do czytania i tak jest szybciej.
Baza trzyma to, co trzeba zapisac z przegladarki albo co jest prywatne.

## Uruchomienie testow

    npm ci
    npm run test:rules

Potrzebna Java - emulator Firestore jest napisany w Javie.

## Czego reguly nie obejmuja

Pipeline pisze przez Admin SDK, ktory **omija reguly w calosci**. Reguly chronia
wylacznie dostep z przegladarki. Klucz konta serwisowego nie moze wiec nigdy
trafic do kodu strony - tylko do sekretow repozytorium.
