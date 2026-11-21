# Panel strategii BEST17 + GPM UK

Statyczna strona pod GitHub Pages, serwowana z katalogu glownego repozytorium. **Nic tu nie liczy strategii** — sygnały wylicza
silnik w Pythonie (`strategies_v2/`) uruchamiany przez GitHub Actions, a strona
wyłącznie czyta gotowe pliki JSON z `web/data/`.

## Uruchomienie lokalnie

Strona czyta dane przez `fetch`, więc musi być serwowana po HTTP — otwarcie
`index.html` z dysku nie zadziała.

    python3 -m http.server 8000   # z katalogu glownego repo

## Pliki

| Plik | Co zawiera | Kto zapisuje |
|---|---|---|
| `../index.html` | szkielet widoków (w katalogu glownym, bo Pages serwuje z `/`) | ręcznie |
| `app.css` | style, motyw ciemny jednowariantowy | ręcznie |
| `app.js` | render i wykresy (moduł ES, bez bibliotek) | ręcznie |
| `data/signals.json` | sygnał obu transz, historia, diagnostyka per transza | pipeline (silnik) |
| `data/performance.json` | miesięczne stopy zwrotu strategii | pipeline |
| `data/prices.json` | instrumenty źródłowe i stan feedu | pipeline |
| `data/portfolio.json` | kapitał, stan posiadania, krzywa wartości | docelowo baza |
| `.nojekyll` | wylacza Jekylla na Pages (serwuje pliki bez przetwarzania) | — |

Zadnego pliku nie generuje sie w trakcie wdrozenia - co w repo, to na stronie.

`data/portfolio.json` jest tu tylko dla prototypu — docelowo te dane są prywatne
i idą do bazy (per użytkownik), a nie do repozytorium.

## Publikacja

Settings → Pages → Source: **Deploy from a branch** → galaz `main`, folder **`/ (root)`**.
Adres: `https://<uzytkownik>.github.io/momentum-invest/`.

GitHub przebudowuje strone sam po kazdym pushu na `main`, wiec osobny workflow
wdrazajacy nie jest potrzebny. Pipeline cenowy bedzie commitowal pliki do
`web/data/` i to wystarczy, zeby strona pokazala nowe dane.

## Transze

Kapitał jest podzielony na dwie równe transze: jedna rebalansuje się 10-tego,
druga 25-tego (dokładniej: pierwszej sesji **na lub po** tym dniu — tę samą
regułę stosuje silnik, patrz `engine_v2/period_anchor.py`). Każda transza ma
własną parę strategii (`strategies_v2/gpm_uk_best17_a_day10` i `…_day25`), więc
i własny sygnał, własny ranking i własnego kanarka — ekran *Analiza* przełącza
się między nimi.

Okres, dla którego nie ma jeszcze notowania z dnia rebalansu, **nie jest
publikowany jako sygnał**: wpada do `awaiting` z powodem. Opublikowanie go
dałoby skład policzony z ceny z innego dnia, a tam, gdzie brakuje danych do
bramki 3-miesięcznej, nawet fałszywe „wszystko do gotówki".

## Stan

| Dane | Skąd | Prawdziwe? |
|---|---|---|
| `signals.json` | `tools/build_signals.py`, silnik `engine_v2` | tak |
| `performance.json` | — | przykładowe |
| `prices.json` | `base` z feedu; szereg dzienny dorabia strona | częściowo |
| `portfolio.json` | — | przykładowe (salda, wpłaty, konta) |

Pasek „Prototyp — dane przykładowe" u góry strony dotyczy tych pozycji, które
nie są jeszcze prawdziwe.
