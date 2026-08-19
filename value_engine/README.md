# value_engine - koncepcja "przeceniona ale zdrowa spolka GPW"

Osobny silnik, poza `engine_v2`. Testuje koncepcje: **kup spolke mocno przecenona wzgledem 52W
high, ale fundamentalnie zdrowa; sprzedaj po odbiciu albo po X miesiacach.**

## Dlaczego osobny folder, a nie `engine_v2`

Ocena zrobiona PRZED napisaniem kodu. Z pieciu elementow koncepcji **cztery** mieszcza sie w
`engine_v2` bez problemu, ale **piaty go lamie**:

| element koncepcji | `engine_v2` |
|---|---|
| ceny dzienne PL | ✅ ten sam format stooq co US/UK - `stooq_csv` czyta `data/pl` bez zmian |
| sygnal cenowy (>=25% pod 52W high) | ✅ zwykly wskaznik + filtr, standardowy ksztalt |
| filtr fundamentalny | ✅ moglby byc wskaznikiem (pipeline nie pyta, skad wartosci) |
| ranking + portfel (top 2-3, equal weight) | ✅ `top_n` + `rank_weights`, natywnie |
| **exit po odbiciu / po 6 miesiacach** | ❌ **nie da sie** |

`engine_v2` jest silnikiem **rotacyjnym i bezstanowym wzgledem pozycji**: kazdy miesiac liczy wagi
docelowe od zera z biezacych wskaznikow, a `PortfolioState` niesie miedzy miesiacami tylko
`current_weights` / `equity` / `tax_base_equity` / `last_target_signature`. Nie ma tam **ceny
wejscia** ani **czasu trzymania** pojedynczej pozycji - a exit wymaga obu. Dorzucenie tych pol
znaczylo by przebudowe wspolnego silnika uzywanego przez ~50 istniejacych strategii, wprost
przeciwko zasadzie repo ("wariant eksperymentalny = osobny plik, nigdy flaga w produkcyjnym
bloku"). To tez inny **paradygmat** (portfel zawsze zaalokowany wg biezacego sygnalu vs dyskretne
transakcje z wlasnym cyklem zycia), a nie brakujacy parametr.

**Co jednak jest ponownie uzyte z `engine_v2`** (bez kopiowania kodu): loader cen `stooq_csv` oraz
`metrics.compute_metrics` - te same definicje CAGR/MaxDD/Sharpe/Calmar, wiec liczby sa
porownywalne 1:1 z reszta repo.

## Moduly

| plik | rola |
|---|---|
| `biznesradar_scraper.py` | (dostarczony) zapis surowych stron BiznesRadaru do SQLite |
| `br_parser.py` | surowy HTML -> uporzadkowane szeregi (okresy, **daty publikacji**, metryki) |
| `fundamentals.py` | panel **point-in-time**: co bylo publicznie znane na dana date |
| `signals.py` | obsuniecie od 52W high, daty decyzyjne (1. dzien handlowy miesiaca) |
| `backtest.py` | silnik dyskretnych transakcji (wejscie -> trzymanie -> wlasny warunek wyjscia) |
| `run_test.py` | odpalenie end-to-end |

```
.venv/bin/python3 -m value_engine.run_test
.venv/bin/python3 -m value_engine.run_test --min-drawdown -0.35 --exit-gain 0.30 --show-trades
.venv/bin/pytest value_engine/tests/ -v
```

## Najwazniejsza rzecz: point-in-time (look-ahead bias)

Raport za okres konczacy sie 2020-12-31 **nie jest znany** 2020-12-31. Zmierzone na tych danych:
mediana opoznienia publikacji **35-58 dni**, maksimum **115 dni**.

BiznesRadar podaje w tabeli wiersz "Data publikacji" (`data-field="PrimaryReport"`), wiec panel
indeksuje wartosci po **dacie publikacji**, nie po koncu okresu. Dowod, ze dziala (test na
prawdziwych danych) - CD Projekt, raport za 2020 opublikowany 2021-04-22:

| data | TTM zysk netto, jaki strategia "zna" |
|---|---|
| 2021-04-21 | 279 019 tys. PLN |
| 2021-04-23 | **1 154 327 tys. PLN** |

4-krotny skok wiedzy w jeden dzien. Bez tego rozgraniczenia backtest podejmowalby decyzje na
danych z przyszlosci.

**Czego to NIE naprawia:** BiznesRadar pokazuje liczby po ewentualnych korektach (restatements) -
wyrownanie po dacie publikacji naprawia **timing**, nie **tresc**. Prawdziwa historia
point-in-time powstanie z czasem, bo `snapshots` trzyma `fetched_at`.

## Wyniki pierwszego testu (uczciwie)

Uniwersum: DNP, CDR, KGH, PKN. Okno **2006-03 -> 2026-08** (liczone od momentu, gdy sygnal cenowy
**i** fundamenty realnie istnialy - inaczej kilkanascie lat martwej gotowki cicho rozwadnialoby
CAGR, ten sam blad co naprawiony w `engine_v2`, CHANGELOG 2026-08-12 (2)).

Konfiguracja bazowa: dd <= -25%, exit +20% albo 6 miesiecy, max 3 pozycje, 40 bps.

| | CAGR | MaxDD | Sharpe | Calmar |
|---|---|---|---|---|
| strategia (srednia ekspozycja **31%**) | 3.27% | -42.72% | 0.288 | 0.077 |
| buy&hold 4 spolki (100%) | 18.94% | -80.04% | 0.651 | 0.237 |
| **buy&hold skalowany do 31%, ZERO timingu** | **7.15%** | **-37.22%** | **0.651** | **0.192** |

**Wniosek: koncepcja w tej postaci niszczy wartosc.** Trzecia linia to najuczciwsze porownanie -
"trzymaj 31% tych spolek na stale, bez zadnego sygnalu" bije strategie na **kazdej** metryce
(2x CAGR, plytszy MaxDD, 2x Sharpe i Calmar). Czyli timing wejsc/wyjsc nie jest tylko ostrozny,
on aktywnie szkodzi. Statystyki transakcji wygladaja przy tym niewinnie (47 transakcji, 62%
zyskownych, srednio +6.08%) - dlatego sam "win rate" jest myslacym mylnie miernikiem.

### Sweep parametrow - gdzie dokladnie jest problem

| wariant | CAGR | MaxDD | Sharpe | Calmar | transakcji | ekspozycja |
|---|---|---|---|---|---|---|
| exit +20% / **3m** | 2.38% | -47.73% | 0.231 | 0.050 | 74 | 28% |
| exit +20% / 6m | 3.27% | -42.72% | 0.288 | 0.077 | 47 | 31% |
| exit +20% / 12m | 4.51% | -42.83% | 0.358 | 0.105 | 35 | 36% |
| exit +20% / **24m** | **8.16%** | -47.68% | 0.545 | 0.171 | 29 | 46% |
| exit **+10%** / 6m | 2.55% | -42.72% | 0.247 | 0.060 | 51 | 28% |
| exit **+60%** / 6m | 5.91% | -42.72% | 0.429 | 0.138 | 44 | 35% |
| dd <= -15% | 5.15% | -43.63% | 0.363 | 0.118 | 71 | 48% |
| dd <= -45% | 3.63% | -23.54% | 0.473 | 0.154 | 12 | 7% |
| **bez filtra fundamentalnego** | 1.98% | -62.17% | 0.199 | 0.032 | 87 | 41% |

Dwa czyste, monotoniczne wnioski:

1. **Regula wyjscia jest zla.** Im dluzej trzymamy i im wyzszy prog realizacji zysku, tym lepiej
   (3m -> 24m: CAGR 2.38% -> 8.16%; +10% -> +60%: 2.55% -> 5.91%). Sprzedawanie po +20% i
   przymusowe zamykanie po 6 miesiacach systematycznie **ucina zwyciezcow**. W granicy (trzymaj i
   nie realizuj zysku) koncepcja zbiega do buy&hold, ktory jest znacznie lepszy.
2. **Filtr fundamentalny realnie pomaga** - bez niego CAGR 1.98% i MaxDD -62%, z nim 3.27% i
   -42.7%. To jedyny element koncepcji, ktory dodaje wartosc.

## Ograniczenia tego testu (istotne)

- **Uniwersum to 4 recznie wybrane spolki, ktore przetrwaly i wygraly** - CDR zrobil 86x, KGH 13x,
  DNP 8.7x, PKN 5x. Sam benchmark buy&hold (18.94% CAGR) jest tym zawyzony. Prawdziwy test
  strategii "value" wymaga tez spolek, ktore zbankrutowaly lub uwiadly - inaczej "kup przecenione"
  jest testowane wylacznie na przecenach, po ktorych nastapilo odbicie.
- **Male probki**: 12-87 transakcji zaleznie od wariantu, portfel 2-3 pozycji z uniwersum 4 spolek
  (czyli 50-75% uniwersum naraz - to prawie brak selekcji). Zadna z powyzszych liczb nie jest
  statystycznie mocna. Kierunek wniosku jest jednak spojny we **wszystkich 14 wariantach**, co
  daje pewnosc co do kierunku, nie co do wartosci.
- Brak indeksu odniesienia (WIG20/WIG) - benchmark to equal-weight tych samych 4 spolek.
- Fundamenty: TTM z kwartalow (zweryfikowane, ze kwartaly sa jednostkowe - suma 4Q = wartosc
  roczna, 8/8 sprawdzonych par).

## Co dalej (jesli wracamy do tej koncepcji)

Kolejnosc wynikajaca z wynikow, nie z gustu:
1. **Poszerzyc uniwersum** o spolki, ktorym sie NIE udalo - bez tego kazdy wynik jest zawyzony.
2. **Wyrzucic albo mocno rozluznic regule wyjscia** (to ona kosztuje), np. wyjscie dopiero gdy
   psuja sie fundamenty, a nie po x% albo po n miesiacach.
3. Zostawic filtr fundamentalny - to jedyna czesc, ktora sie obronila.
