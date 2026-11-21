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
| `.nojekyll` | wylacza Jekylla na Pages (serwuje pliki bez przetwarzania) | — |

Zadnego pliku nie generuje sie w trakcie wdrozenia - co w repo, to na stronie.

Dane konta są prywatne i leżą wyłącznie w bazie, per użytkownik
(`users/{uid}/transactions`). W repozytorium nie ma ich w żadnej postaci - nie
ma też pliku z przykładowym portfelem. Panel bez wpisów nie pokazuje **żadnej
kwoty**, tylko mówi, czego mu brakuje.

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

## Benchmark

Porównanie siedzi na ekranie *Wyniki*. Benchmarki to **UK-listowane ETF-y klasy
Acc** — `cspx.uk` (S&P 500) i `vwra.uk` (świat) — a nie surowe `spy.us`/`vt.us`
z `data/us`. Powód jest konkretny: pliki z `data/us` to ceny zamknięcia **bez
reinwestycji dywidend** (patrz `dividend_adjusted_csv_loader`), więc benchmark
z nich byłby zaniżony o całą stopę dywidendy i porównanie wychodziłoby za ładnie
dla strategii. Klasa Acc trzyma dywidendy w NAV, więc jest uczciwa.

W drugą stronę uczciwości już nie ma i panel to pisze: noga BEST17 liczy się na
surowych cenach z USA, więc **strategia jest zaniżona**, nie podkoloryzowana.

`vwra.uk` jest notowany dopiero od 2019-07, czyli krócej niż okno strategii —
jego wiersz w tabeli ma własne daty, a na wykresie krzywa startuje od wartości
strategii z tamtego dnia.

## Dane konta

User nie prowadzi księgi transakcji - *"co jakiś czas wpisuje, ile ma na
koncie"*. Panel przyjmuje więc **migawki stanu** (data, konto, wartość w USD)
oraz wpłaty i wypłaty, i z tego liczy wszystko, co pokazuje Pulpit:

- kapitał = suma ostatnich stanów wszystkich kont,
- wpłacone = skumulowane przepływy od początku historii,
- wynik = kapitał − wpłacone,
- TWR = zwroty łączone **tylko między miesiącami, w których jest wpis stanu**,
  z odjętymi przepływami. Miesiąc bez wpisu nie jest miesiącem na zero - po
  prostu nie wiadomo, ile konto było wtedy warte, i panel go nie rysuje.

Przy stanie konta można (nieobowiązkowo) rozpisać kwoty na walory. Dopiero
wtedy panel wie, **co dokupić, a co sprzedać** - bez rozbicia mówi to wprost
zamiast zgadywać. Z rozbicia odczytuje też, która noga leży na którym koncie:
nie z deklaracji, tylko z tego, co tam naprawdę jest.

Kwoty są w USD (ETF-y są dolarowe), złote to przeliczenie po kursie.

## Stan

| Dane | Skąd | Prawdziwe? |
|---|---|---|
| `signals.json` | `tools/build_signals.py`, silnik `engine_v2` | tak |
| `performance.json` | `tools/build_performance.py`, silnik `engine_v2` | tak |
| `prices.json` | `tools/build_prices.py`, silnik `engine_v2` | tak |

Wszystkie trzy pliki liczy silnik. Czwartego nie ma: dane konta nie mieszkają
w repozytorium.

Zasada, której panel się trzyma: **nie pokazuje liczby, której nie zna**.
Zamiast wymyślonego kapitału pisze, że go nie zna, a skład docelowy podaje
w procentach — udział jest prawdziwy niezależnie od tego, ile kto ma.
