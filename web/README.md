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
| `data/performance.json` | historia strategii: miesiące, metryki, obsunięcie, miks klas | pipeline (silnik) |
| `data/prices.json` | ceny wykonania obu transz - te, ktorymi liczyl silnik | pipeline (silnik) |
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

## Ceny

Ekran *Ceny* nie pobiera nic na zywo i nie ma pobierac. Pokazuje **liczby, z
ktorych policzony zostal sygnal**, zebys mogl porownac je z rachunkiem u brokera.
Dlatego czyta je ten sam loader i to samo kotwiczenie dnia, co strategia.

Kazda noga ma wlasny kalendarz gieldowy, wiec kurs potrafi byc z innego dnia niz
data kolumny (np. Memorial Day w US, bank holiday w UK) - panel pisze wtedy przy
cenie, z ktorej sesji naprawde pochodzi. Gdy danego dnia sesji nie bylo w ogole,
pokazuje liczbe, ktorej uzyl silnik, i oznacza ja jako interpolacje - bo to nie
jest notowanie.

## Wyniki

Historia zaczyna się **2018-06**, nie wcześniej: `gpm_uk` nie ma wcześniejszych
danych, a combiner trzymałby wtedy połowę kapitału w bezczynnej gotówce - to nie
byłby wynik tego portfela. Granicę wyznacza `find_combined_valid_window_start`,
czyli ta sama funkcja, której silnik używa do własnych metryk.

Kończy się na ostatnim okresie, dla którego **znany jest kurs następnego
rebalansu** - bez niego zwrot okresu nie istnieje, a silnik zwróciłby zero, co
wyglądałoby jak "miesiąc na zero".

CAGR, MaxDD, Sharpe i Calmar liczą się z **dziennej** krzywej kapitału. Z samych
miesięcznych zamknięć MaxDD wychodził −7,8% zamiast prawdziwych −15,8%.

## Stan

| Dane | Skąd | Prawdziwe? |
|---|---|---|
| `signals.json` | `tools/build_signals.py`, silnik `engine_v2` | tak |
| `performance.json` | `tools/build_performance.py`, silnik `engine_v2` | tak |
| `prices.json` | `tools/build_prices.py`, silnik `engine_v2` | tak |
| `portfolio.json` | — | przykładowe (salda, wpłaty, konta) |

Pasek „Prototyp — dane przykładowe" u góry strony dotyczy tych pozycji, które
nie są jeszcze prawdziwe.
