# value_engine - strategie "value" na GPW

Osobny silnik, poza `engine_v2`. Piec przetestowanych koncepcji, wszystkie oparte na tych samych,
wspolnych fundamentach technicznych (parser BiznesRadaru + panel point-in-time + ceny PL +
uniwersum point-in-time).

| koncepcja | plik silnika | runner | wynik na 22 spolkach | **wynik na 41 spolkach** |
|---|---|---|---|---|
| v1: przeceniona + zdrowa, profit target | `backtest.py` | `run_test.py` | odrzucona (niszczy wartosc) | – |
| v2: quality value, sloty + podmiana | `quality_value_backtest.py` | `run_quality_value.py` | 8.25% vs 9.64% bench | **-1.34% vs 7.99%** |
| v3: bez podmiany, 36m, opcjonalny trailing stop | ten sam silnik, `allow_score_replacement=False` | `run_v3_comparison.py` | 5.74% vs 9.64% (ze stopem) | **3.55% vs 7.99%** |
| v4: Value + Quality + Momentum, top4/top8 | `factor_backtest.py` | `run_factor.py` | 14.42% vs 9.64% (**+4.78pp**, LOO 21/22) | **6.63% vs 7.99% (-1.36pp, LOO 12/41)** |
| v5: Quality Defensive (Quality + LowVol), top 5 | ten sam silnik, `scorer=` | `run_defensive.py` | 9.61% vs 9.61% (remis, LOO 6/21) | **7.08% vs 7.95% (-0.87pp, LOO 2/40)** |

**NAJWAZNIEJSZY WNIOSEK CALEJ SERII: zaden z pieciu pomyslow nie bije uczciwego benchmarku PIT na
szerszym uniwersum.** Wynik kazdej wersji zalezy DRASTYCZNIE od tego, na czym jest liczony - i to
zaleznosc silniejsza niz jakakolwiek zmiana regul strategii:

1. **survivorship w benchmarku**: v3 + trailing stop daje 23.34% CAGR na stalej liscie dzisiejszych
   ocalalych i 5.74% na uniwersum point-in-time. Ta sama strategia, ta sama historia cen.
2. **liczba kandydatow**: przewaga v4 (+4.78pp, potwierdzona leave-one-out 21/22) **znikla po
   dolozeniu 19 spolek** - te same reguly daja teraz -1.36pp, a leave-one-out spadl do 12/41 przy
   rozrzucie 11.82pp. Szczegoly i mechanizm nizej.

Praktyczny wniosek: kazdy pozytywny wynik w tym folderze nalezy traktowac jako hipoteze do
falsyfikacji przez poszerzenie danych, nie jako przewage. Dwa razy z rzedu poszerzenie danych
falsyfikowalo wniosek.

## Dlaczego osobny folder, a nie `engine_v2`

Ocena zrobiona PRZED napisaniem kodu. Z pieciu elementow koncepcji **cztery** mieszcza sie w
`engine_v2` bez problemu, ale **piaty go lamie**:

| element | `engine_v2` |
|---|---|
| ceny dzienne PL | ✅ ten sam format stooq co US/UK - `stooq_csv` czyta `data/pl` bez zmian |
| sygnal cenowy (>=25% pod 52W high) | ✅ zwykly wskaznik + filtr |
| filtr/score fundamentalny | ✅ moglby byc wskaznikiem (pipeline nie pyta, skad wartosci) |
| ranking + portfel (top N, equal weight) | ✅ `top_n` + `rank_weights` |
| **exit po odbiciu / po N miesiacach, sloty z podmiana** | ❌ **nie da sie** |

`engine_v2` jest silnikiem **rotacyjnym i bezstanowym wzgledem pozycji**: kazdy miesiac liczy wagi
docelowe od zera z biezacych wskaznikow, a `PortfolioState` niesie tylko `current_weights` /
`equity` / `tax_base_equity` / `last_target_signature`. Nie ma tam **ceny wejscia**, **czasu
trzymania** ani **tozsamosci pozycji** - a te koncepcje wymagaja wszystkich trzech. Dorzucenie ich
znaczylo by przebudowe wspolnego silnika ~50 istniejacych strategii, wprost przeciwko zasadzie repo
("wariant eksperymentalny = osobny plik, nigdy flaga w produkcyjnym bloku").

**Co JEST ponownie uzyte z `engine_v2`** (bez kopiowania kodu): loader cen `stooq_csv` oraz
`metrics.compute_metrics` - te same definicje CAGR/MaxDD/Sharpe/Calmar, wiec liczby sa
porownywalne 1:1 z reszta repo.

## Moduly

| plik | rola |
|---|---|
| `biznesradar_scraper.py` | (dostarczony) zapis surowych stron BiznesRadaru do SQLite (**gzip**) + kopiowanie plikow cen |
| `br_parser.py` | surowy HTML -> uporzadkowane szeregi (okresy, **daty publikacji**, metryki) |
| `fundamentals.py` | panel **point-in-time**: co bylo publicznie znane na dana date |
| `signals.py` | obsuniecie od 52W high, daty decyzyjne (1. dzien handlowy miesiaca) |
| `scoring.py` | QUALITY (4 kryteria x 25 pkt), percentyle DD/REL, skladanie SCORE 0-100 |
| `universe.py` | uniwersum **point-in-time** (plynnosc, historia) + branze (wykluczenie finansowych) |
| `market_cap.py` | kapitalizacja point-in-time odtworzona z kapitalu zakladowego |
| `canary.py` | filtr rezimu WIG20 > 10M MA (sprawdzony - szkodzi strategiom valuowym) |
| `backtest.py` | silnik koncepcji v1 |
| `quality_value_backtest.py` | silnik koncepcji v2/v3 (sloty + regula podmiany) |
| `factor_scoring.py` | scoring v4: Value (rentownosci) + Quality (5 kryteriow) + Momentum 12-1 |
| `factor_backtest.py` | silnik koncepcji v4 i v5 - **scoring wstrzykiwany przez `scorer=`** |
| `defensive_scoring.py` | scoring v5: 50% Quality (ROE/ROIC/Debt-MC) + 50% LowVol (6M/12M) |

### Gdzie leza dane

| co | gdzie | uwaga |
|---|---|---|
| fundamenty (surowy HTML) | `value_engine/biznesradar_raw.sqlite3` | **spakowane gzipem**, czytane przez `br_parser.decode_body` |
| ceny dzienne, ktore czytaja runnery | `data/pl/*.txt` | + `wig20.txt` na kanarka i benchmark v2/v3 |
| ceny zrzucone przez scraper | `value_engine/ticker_files/*.txt` | katalog docelowy `--ticker-files-dest`, domyslnie obok bazy |

`PL_DATA_DIR` wskazuje na `data/pl`, wiec nowe pliki z `ticker_files` trzeba tam skopiowac (albo
uruchomic scraper z `--ticker-files-dest data/pl`). UWAGA: `unique_destination` w scraperze NIE
nadpisuje istniejacych plikow, tylko dokleja `_2` - po drugim przebiegu na tych samych tickerach
katalog mial 82 pliki, z czego 41 bylo bajt w bajt duplikatami (usuniete).

```
.venv/bin/python3 -m value_engine.run_quality_value
.venv/bin/python3 -m value_engine.run_quality_value --sweep
.venv/bin/python3 -m value_engine.run_v3_comparison --leave-one-out
.venv/bin/python3 -m value_engine.run_factor
.venv/bin/python3 -m value_engine.run_defensive
.venv/bin/python3 -m value_engine.run_defensive --leave-one-out
.venv/bin/pytest value_engine/tests/ -v
```

## Fundament wspolny 2: uniwersum POINT-IN-TIME (`universe.py`)

User: "Najpierw jednak poprawilbym universe point-in-time. Test z CDR praktycznie udowodnil, ze
obecny survivorship bias moze calkowicie zmienic wniosek."

Uniwersum bylo LISTA STALA, wybrana z dzisiejszej perspektywy. To wnosilo **dwa rozne** bledy i
tylko jeden z nich da sie naprawic tymi danymi:

**(1) HINDSIGHT CO DO ROZMIARU/PLYNNOSCI - NAPRAWIONE.** Spolka byla w uniwersum przez cala
historie, takze w latach, gdy byla mikrospolka. Zmierzona mediana obrotu dziennego:

| ticker | 2008 | 2015 | 2026 |
|---|---|---|---|
| KGH | 66.6 mln | 82.3 mln | 271.2 mln |
| **CDR** | **0.39 mln** | 4.1 mln | 75.1 mln |
| DOM | 0.21 mln | **0.02 mln** | 1.5 mln |
| RBW | 0.01 mln | 0.28 mln | 5.3 mln |

CDR w 2008 mial obrot ~170x mniejszy niz KGH - nie byl "duza i plynna spolka". A to WLASNIE CDR
odwracal wnioski v2. Filtr plynnosci liczony z danych z TAMTEGO momentu (mediana obrotu z 6M,
liczona krocząco wstecz - zero look-ahead) wyklucza go do 2011 i wpuszcza na stale od 2015.

**(2) SURVIVORSHIP - NIENAPRAWIALNE tymi danymi.** W `data/pl` nie ma spolek wycofanych z
obrotu/upadlych. Filtr plynnosci nie odtworzy brakujacych szeregow. Po poprawce wynik jest wciaz
zawyzony, tylko mniej - i to trzeba pamietac przy kazdej liczbie ponizej.

Rozmiar uniwersum PIT (prog 2 mln PLN/dzien), przed i po poszerzeniu zbioru zrodlowego:

| rok | zbior 22 spolek | **zbior 41 spolek (obecny)** |
|---|---|---|
| 2006 | 3.0 | 3.0 |
| 2010 | 5.2 | 5.2 |
| 2014 | 9.5 | **12.1** |
| 2018 | 10.7 | **15.2** |
| 2022 | 15.2 | **21.2** |
| 2026 | 14.9 | **22.8** |

Wczesny okres jest identyczny (nowe spolki albo nie byly notowane, albo nie mialy jeszcze plynnosci)
i pozostaje bardzo waski - przy 4 slotach praktycznie nie ma tam z czego wybierac. Realna zmiana
zaczyna sie od ~2014. Mediana rankowanego uniwersum w calym oknie wzrosla z **10 do 14** spolek - i
to wystarczylo, zeby odwrocic wniosek o v4 (patrz sekcja o przeliczeniu na 41 spolkach).

**Uniwersum PIT ogranicza tylko NOWE WEJSCIA.** Pozycja, ktora wypadla z uniwersum (spadla
plynnosc), nie jest sprzedawana na sile - wychodzi normalnymi reguami. Wymuszona sprzedaz przy
zaniku plynnosci bylaby nierealistyczna: wtedy najtrudniej wyjsc.

**Benchmark tez musial zostac poprawiony** (`buy_hold_pit`). Poczatkowo porownywalem uczciwa
strategie (PIT) z nieuczciwym benchmarkiem (rownowazona srednia dzisiejszych ocalalych) - taki uklad
z definicji przegrywa. Skala bledu jest duza i ROSNIE z liczba spolek: przy 22 nazwach benchmark
survivorship dawal 14.56% CAGR vs 9.64% PIT (~5pp), przy 41 nazwach **14.23% vs 7.99% (~6.2pp)**.
Kazda liczba "vs benchmark" w tym pliku odnosi sie do benchmarku PIT.

## Fundament wspolny: point-in-time fundamentow (look-ahead bias)

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

---

# PRZELICZENIE NA 41 SPOLKACH - przewaga v4 znika

User: "wrzucilem wiecej danych spolek (...) trzeba zrobic na nowo testy bo mamy wiecej kandydatow
wiec moze cos sie zmienic". Zmienilo sie - i to najwazniejsza rzecz w tym pliku.

**Co doszlo**: 19 nowych spolek (11B, APR, ATT, BDX, BFT, CLN, ENA, ENG, GPP, HUG, JSW, KTY, MRC,
PCR, SEL, SNT, VRG, WPL, ZEP), lacznie **41** zamiast 22. Mediana rankowanego uniwersum wzrosla z
**10 do 14** spolek (a w ostatnich latach do ~22). Fundamenty w SQLite sa teraz **spakowane gzipem**
(72 MB -> 10.8 MB) - patrz `br_parser.decode_body`.

## Wszystkie koncepcje, to samo okno (2006-03 -> 2026-08), ten sam uczciwy benchmark

| wariant | CAGR (22) | **CAGR (41)** | MaxDD (41) | Sharpe (41) | n (41) |
|---|---|---|---|---|---|
| **benchmark: buy&hold uniwersum PIT** | 9.64% | **7.99%** | -59.43% | 0.456 | - |
| v2 (podmiana po score, 24m), PIT | 8.25% | **-1.34%** | -65.50% | 0.060 | 84 |
| v3 (bez podmiany, 36m), PIT | 3.17% | **0.60%** | -62.63% | 0.148 | 28 |
| v3 + trailing stop 20%, PIT | 5.74% | **3.55%** | -63.13% | 0.267 | 150 |
| v4 (Value+Quality+Momentum, top4/top8) | **14.42%** | **6.63%** | -62.49% | 0.383 | 52 |
| v5 (Quality+LowVol, top 5) | 9.61% | **7.08%** | -57.05% | 0.431 | 128 |
| v4 + kanarek WIG20 | 5.55% | 4.86% | -39.43% | 0.372 | 100 |
| v5 + kanarek WIG20 | 4.58% | 5.11% | -33.10% | 0.422 | 155 |
| *buy&hold STALE 41 spolek (survivorship!)* | *14.56%* | *14.23%* | *-72.29%* | *0.637* | - |

**Zadna wersja nie bije benchmarku PIT.** Najblizej jest v5 (-0.87pp), v4 traci -1.36pp, v2 wychodzi
wrecz na minus. Benchmark tez spadl (9.64% -> 7.99%), bo nowe spolki sa slabsze - ale v4 spadl
**5-krotnie mocniej** (-7.79pp vs -1.65pp), czyli jego ranking wybiera z nowej puli GORZEJ niz losowo.

## Mechanizm: dwie rzeczy, obie sprawdzone na transakcjach

**(1) Nowe spolki to value trapy, a Value ma 40% wagi w v4.** Transakcje v4 wg pochodzenia spolki:

| spolki | transakcji | sredni zwrot | **mediana** |
|---|---|---|---|
| stare 22 | 35 | +24.0% | +15.4% |
| **nowe 19** | 17 | -4.3% | **-23.3%** |

Najgorsze wejscia to ATT (-49%), ENG (-48%), MRC (-40%), ENA (-35%, -33%), KTY (-35%) - chemia,
energetyka, gornictwo, w duzej czesci spolki kontrolowane przez skarb panstwa. Sa TANIE (niskie P/E,
P/BV, wysoki FCF yield) i wlasnie dlatego czynnik Value je wybiera. Nowe nazwy to 20% uniwersum PIT,
ale 24% pozycji v4 - lekkie przewazenie, na dodatek tych najslabszych.

**(2) Histereza, ktora byla bezwladna, teraz WYCINA ZWYCIEZCE.** Na 22 spolkach "poza top 8"
znaczylo "w najgorszej dwojce z dziesieciu" i praktycznie nie zachodzilo (2.3% obserwacji) - dzieki
temu v4 trzymal CDR **3.6 roku i zrobil na nim +967%**, co samo w sobie odpowiadalo za wiekszosc
przewagi. Na 41 spolkach "top 8 z 14-22" jest realnym ograniczeniem i ta sama regula sprzedaje CDR
po **8 miesiacach z +76%**:

| | 22 spolki | 41 spolek |
|---|---|---|
| najlepsza transakcja | **CDR +967.2%** (2016-01 -> 2019-08, 1338d) | KGH +294.8% (2006-03 -> 2013-12) |
| transakcja na CDR | +967.2%, 1338 dni | **+76.1%, 243 dni** |
| transakcji ogolem | 26 | 52 |
| mediana czasu trzymania | 632 dni | 350 dni |

Powod jest wbudowany w konstrukcje: gdy kurs rosnie, score Value SPADA, wiec zwyciezca sam schodzi w
rankingu - a przy szerszej puli zawsze znajdzie sie tanszy kandydat, ktory go wypchnie. **v4 na 41
spolkach systematycznie sprzedaje to, co rosnie.** README ostrzegal o tym wczesniej ("parametr
`keep_rank=8` jest dostrojony do uniwersum znacznie wiekszego niz to, ktore realnie mamy") - tylko ze
skutek okazal sie odwrotny do oczekiwanego: przy wiekszym uniwersum regula nie zaczyna dzialac
lepiej, ona zaczyna szkodzic.

## Leave-one-out na 41 spolkach: v4 21/22 -> **12/41**, v5 6/21 -> **2/40**

| | v4 (22) | **v4 (41)** | v5 (22) | **v5 (41)** |
|---|---|---|---|---|
| bije swoj benchmark na CAGR | **21/22** | **12/41** | 6/21 | **2/40** |
| bije swoj benchmark na Sharpe | 21/22 | 10/41 | 14/21 | 7/40 |
| rozrzut CAGR | 8.22pp | **11.82pp** | 3.94pp | 4.24pp |

Te dwie liczby mowia o DWOCH ROZNYCH rodzajach porazki i warto ich nie mieszac:

**v4 jest KRUCHY.** Rozrzut 11.82pp (5.22% - 17.04%) przy sredniej 6.63% znaczy, ze wynik zalezy od
kilku konkretnych nazw, nie od reguly:

| bez spolki | CAGR v4 | vs benchmark |
|---|---|---|
| **bez CPS** | **17.04%** | **+8.80pp** |
| bez ENA | 13.92% | +5.57pp |
| bez JSW | 12.35% | +3.78pp |
| *pelne 41* | *6.63%* | *-1.36pp* |
| bez ALE | 5.22% | -2.89pp |
| bez TEN | 5.30% | -2.97pp |

Usuniecie JEDNEJ spolki (CPS) zamienia -1.36pp na +8.80pp. Strategia, ktorej wniosek odwraca sie na
jednej nazwie z 41, nie ma zmierzonej przewagi - ma szum.

**v5 jest STABILNIE ZA SLABY.** Rozrzut tylko 4.24pp, ale 38 z 40 przebiegow przegrywa, prawie
wszystkie w waskim pasmie -0.2pp do -1.3pp. To wynik systematyczny, nie przypadkowy, i akurat
dlatego bardziej wiarygodny: v5 po prostu nie ma przewagi. Zniknela tez jego jedyna zaleta z
uniwersum 22 spolek - **przewaga na Sharpe** (0.555 vs 0.521) zamienila sie w strate (0.431 vs
0.453). Zostal tylko nieco lepszy MaxDD (-57.05% vs -59.43%).

## Gdzie v4 parkuje kapital: 61% czasu w 5 nazwach

Miesiace w portfelu (z 246), pelny przebieg na 41 spolkach:

| spolka | miesiecy | udzial | transakcji | sredni zwrot |
|---|---|---|---|---|
| PKN | 167 | **68%** | 8 | +4.5% |
| ACP | 151 | **61%** | 4 | +48.4% |
| KGH | 107 | 43% | 2 | +161.1% |
| **OPL** | 105 | **43%** | 5 | **+5.6%** (w tym +14.8% przez 5.3 ROKU) |
| ENA | 65 | 26% | 5 | **-5.6%** |
| CPS | 61 | 25% | 3 | +10.5% |

Piec najczestszych nazw to **595 z 973 miesiaco-pozycji (61%)**. Telekom i energetyka trzymane
latami przy zwrotach kilkunastu procent - to nie jest strata, to KOSZT ALTERNATYWNY, i wlasnie on
tlumaczy, dlaczego usuniecie CPS albo ENA podnosi CAGR o 5-9pp. Czynnik Value (40% wagi) wskazuje te
spolki niezmiennie, bo one sa trwale tanie - i trwale tanie zostaja.

## Co to znaczy

- **Przewaga v4 byla artefaktem waskiego uniwersum, nie odkryciem.** Test leave-one-out 21/22
  sprawdzal odpornosc na usuniecie spolki, ale nie mial szans wykryc wrazliwosci na DODANIE spolek.
  To osobny wymiar kruchosci i od teraz trzeba go sprawdzac osobno.
- **Kanarek WIG20 nadal szkodzi na zwrocie** (v4: 6.63% -> 4.86%), ale przy tak slabych wynikach
  bazowych jego przewaga w MaxDD (-62% -> -39%) przestaje byc bez znaczenia. Wniosek "nie wdrazac"
  zostaje, bo bierne trzymanie ~55% benchmarku nadal wypada lepiej.
- **Nie ma sensu sweep wag** ani dobieranie `keep_rank` pod nowe uniwersum. Zgodnie z zasada
  przyjeta przy v4 ("jesli nie ma przewagi, nie ratujemy jej optymalizacja") - a teraz doszedl
  drugi argument: kazdy parametr dobrany pod 41 spolek bedzie mial dokladnie ten sam problem, ktory
  wlasnie zlapalismy przy przejsciu z 22 na 41.

---

# Koncepcja v2: "quality value" (uniwersum 22 spolki)

Uniwersum: **22 spolki GPW** (bez bankow i ubezpieczycieli): acp ale asb car cdr cps dnp dom dvl
kgh kru lpp lwb neu opl pep pge pkn rbw ten tpe txt.

    SCORE = 0.50 * DD + 0.25 * REL + 0.25 * QUALITY

- **DD** - percentyl obsuniecia od 52W high (najbardziej przeceniona ~100)
- **REL** - percentyl slabosci wzgledem rynku za 6M (najbardziej odstajaca w tyl ~100)
- **QUALITY** - 0/25/50/75/100, po 25 pkt za: zysk TTM > 0; CFO TTM > 0; CFO >= zysk;
  dlug/aktywa <= rok wczesniej

Bramka wejscia: `drawdown >= 25%` ORAZ `QUALITY >= 50`. Max 4 pozycje po 25%. Wolny slot -> najlepszy
kandydat. Portfel pelny -> podmiana najslabszej, gdy nowy ma score wyzszy o >= 10 pkt. Wyjscie:
fundamental fail albo max holding 24m; bez profit targetu. Decyzje raz w miesiacu.

## Wynik (okno 2006-03 -> 2026-08)

| | CAGR | MaxDD | Sharpe | Calmar |
|---|---|---|---|---|
| strategia (ekspozycja 97%) | 10.61% | -65.82% | 0.540 | 0.161 |
| buy&hold uniwersum (100%) | **14.56%** | -69.89% | **0.634** | **0.208** |
| buy&hold skalowany do 97%, zero timingu | **14.23%** | -68.75% | **0.634** | **0.207** |

**Strategia nie bije benchmarku** - ani na zwrocie, ani na miarach ryzyka. Poprawia jedynie MaxDD
(-65.8% vs -68.8%), i to nieznacznie. Jest to jednak **duzo blizej** niz koncepcja v1 (tam
stosunek CAGR do benchmarku byl 0.46, tu 0.75).

## Sweep 12 wariantow

| wariant | CAGR | MaxDD | Sharpe | Calmar | transakcji | ekspozycja |
|---|---|---|---|---|---|---|
| bazowa (24m, margin 10) | 10.61% | -65.82% | 0.540 | 0.161 | 114 | 97% |
| max holding 36m | 11.96% | -62.47% | 0.598 | 0.191 | 109 | 98% |
| max holding 12m | 8.97% | -57.65% | 0.477 | 0.156 | 129 | 90% |
| margin podmiany 0 | 10.56% | -65.82% | 0.543 | 0.161 | 140 | 97% |
| margin podmiany 20 | 8.82% | -67.65% | 0.474 | 0.130 | 93 | 97% |
| bramka dd >= 15% | 9.14% | -58.52% | 0.494 | 0.156 | 150 | 99% |
| bramka dd >= 35% | 7.68% | -68.90% | 0.428 | 0.112 | 70 | 82% |
| QUALITY >= 75 | 9.12% | -59.95% | 0.487 | 0.152 | 106 | 89% |
| **QUALITY >= 0 (bez bramki jakosci)** | **15.36%** | -63.63% | **0.694** | **0.241** | 129 | 100% |
| rebalans do 25% co miesiac | 10.42% | **-74.06%** | 0.503 | 0.141 | 114 | 97% |
| max 2 pozycje | 5.94% | -77.53% | 0.341 | 0.077 | 83 | 99% |
| max 6 pozycji | 11.25% | -67.99% | 0.612 | 0.165 | 125 | 92% |

## Najwazniejsze: dlaczego "QUALITY >= 0" to NIE odkrycie

Jedyny wariant bijacy benchmark (15.36% / Sharpe 0.694) to ten **bez bramki jakosci**. Wygladalo
to na realne odkrycie ("bramka jakosci szkodzi"), ale sprawdzenie pokazalo, ze to **artefakt
jednej spolki** - CD Projekt (86x w oknie). Bez bramki strategia kupuje CDR 13 razy, w tym w
momentach o QUALITY 0-25.

Wystarczylo usunac CDR z uniwersum (21 spolek zamiast 22), zeby wniosek sie odwrocil:

| | CAGR | MaxDD | Sharpe | Calmar |
|---|---|---|---|---|
| **z CDR** QUALITY>=50 | 10.61% | -65.82% | 0.540 | 0.161 |
| **z CDR** QUALITY>=0 | 15.36% | -63.63% | 0.694 | 0.241 |
| **z CDR** buy&hold | 14.56% | -69.89% | 0.634 | 0.208 |
| **bez CDR** QUALITY>=50 | 10.96% | -65.55% | 0.560 | 0.167 |
| **bez CDR** QUALITY>=0 | 12.31% | -63.53% | 0.594 | 0.194 |
| **bez CDR** buy&hold | **13.27%** | -70.39% | **0.607** | 0.189 |

Przewaga "bez bramki" nad "z bramka" spada z +4.75pp do +1.35pp, a przewaga nad benchmarkiem
(+0.80pp) zamienia sie w strate (-0.96pp). **Jedna spolka z 22 przewraca wniosek** - to miara
tego, jak krucha jest ta probka.

## Obserwacja strukturalna: regula podmiany to de facto szybkie wyjscie

Spec mowil "bez szybkiego profit targetu" i "max holding 24/36 miesiecy", ale w praktyce:

| powod wyjscia | udzial |
|---|---|
| podmiana (`replaced`) | **77%** (88/114) |
| fundamental fail | 11% (13) |
| timeout 24m | **8%** (9) |
| koniec danych | 4% (4) |

Mediana czasu trzymania: **182 dni**, 51% pozycji trzymane krocej niz 6 miesiecy. Limit 24 miesiecy
zadzialal 9 razy. Czyli **regula podmiany przejela role profit targetu**, ktorego spec chcial
uniknac - strategia realnie zachowuje sie jak miesieczna rotacja po obsunieciu, a nie jak
cierpliwy value. To najwazniejsza rozbieznosc miedzy intencja spec a jej faktycznym dzialaniem.

## Wnioski powtarzalne miedzy v1 i v2

1. **Dluzsze trzymanie jest lepsze** - v2: 12m -> 24m -> 36m daje 8.97% -> 10.61% -> 11.96%;
   v1: 3m -> 24m daje 2.38% -> 8.16%. Spojne w obu koncepcjach.
2. **Koncentracja szkodzi** - max 2 pozycje: CAGR 5.94% i MaxDD -77.5% (najgorszy wariant).
3. **Wymuszony rebalans do 25% co miesiac pogarsza MaxDD** (-65.8% -> -74.1%) przy tym samym CAGR.
4. **Bramka jakosci nie pomaga** (v2), choc w v1 filtr fundamentalny pomagal - roznica: w v1 byl
   jedynym filtrem, w v2 QUALITY jest juz w score, wiec bramka dubluje ten sam sygnal i tylko
   zawęża wybor.

## Ograniczenia (istotne)

- **Uniwersum to spolki, ktore PRZETRWALY do dzis** - brak spolek wycofanych z obrotu/upadlych.
  Zawyza to i strategie, i benchmark, ale najbardziej "kup przecenione", bo testujemy je wylacznie
  na przecenach, po ktorych nastapilo odbicie.
- **Brak WIG20**: `REL` liczony wzgledem rownowazonej sredniej uniwersum (fallback z jawnym
  ostrzezeniem w kazdym uruchomieniu). To NIE to samo co spec - dodatkowo taki REL jest czesciowo
  redundantny z DD (oba mierza slabosc wzgledem grupy). Wystarczy wrzucic `data/pl/wig20.txt`
  w formacie stooq, silnik uzyje go automatycznie.
- 114 transakcji w oknie 20 lat, portfel 4 z 22 spolek - probka mala, MaxDD ~-65% bardzo wysoki.
- Fundamenty: TTM z kwartalow (zweryfikowane, ze kwartaly sa jednostkowe - suma 4Q = wartosc
  roczna, 8/8 sprawdzonych par).
- `Debt` = oprocentowane zadluzenie (`Borrowings` biezace + dlugoterminowe), **bez leasingu** -
  leasing wszedl do bilansow z IFRS 16 (~2019) i jego wliczenie dawalo by sztuczny skok zadluzenia
  u kazdej spolki naraz w roku przejscia.

## Co dalej

1. **Wrzucic WIG20** - jedyna brakujaca czesc spec, i jedyny sposob, zeby REL byl niezaleznym
   sygnalem, a nie powtorzeniem DD.
2. **Poszerzyc uniwersum o spolki wycofane z obrotu** - bez tego kazdy wynik "value" jest zawyzony,
   a wnioski krucha (patrz test bez CDR).
3. **Rozstrzygnac konflikt regula-podmiany vs cierpliwe trzymanie** - albo podniesc margin i
   swiadomie trzymac dluzej, albo przyjac, ze to strategia rotacyjna i przestac ja opisywac jako
   value.

---

# Koncepcja v4: Value + Quality + Momentum (uniwersum 22 spolki)

Spec (user): uniwersum duze/plynne PIT; rebalans miesieczny; `FINAL = 0.40*Value + 0.30*Quality +
0.30*Momentum`; portfel top 4 po 25% bez wyrownywania; replacement gdy trzymana spolka wypadnie z
top 8, a kandydat jest w top 4 (histereza); **brak trailing stopu, profit targetu i timeoutu** -
sprzedaz wynika wylacznie z pogorszenia rankingu. Testowana DOKLADNIE ta jedna wersja, bez sweepu wag.

## Wynik

| | CAGR | MaxDD | Sharpe | Calmar | transakcji |
|---|---|---|---|---|---|
| **v4** | **14.42%** | -57.97% | **0.660** | **0.249** | 26 |
| buy&hold uniwersum PIT (uczciwy benchmark) | 9.64% | -55.06% | 0.525 | 0.175 | - |
| buy&hold STALE 22 spolki (survivorship!) | 14.56% | -69.89% | 0.634 | 0.208 | - |

Przewaga nad uczciwym benchmarkiem: **+4.78pp CAGR**, Sharpe 0.660 vs 0.525, Calmar 0.249 vs 0.175.
MaxDD nieco gorszy (-58.0% vs -55.1%). Warto zauwazyc, ze v4 mierzone na UCZCIWYM uniwersum
dorownuje benchmarkowi liczonemu na uniwersum OBCIAZONYM (14.42% vs 14.56%).

## Test kruchosci: 21/22

| | wynik |
|---|---|
| bije wlasny benchmark na CAGR | **21/22** |
| bije wlasny benchmark na Sharpe | **21/22** |
| rozrzut CAGR | 8.22pp (8.19% - 16.41%) |
| zakres przewagi | -0.03pp do +6.96pp |

Jedyny wariant bez przewagi to "bez CDR" i jest to praktycznie remis (8.42% vs 8.45%, -0.03pp).
Czyli: CD Projekt odpowiada za duza czesc BEZWZGLEDNEGO zwrotu, ale przewaga nad benchmarkiem
utrzymuje sie w 21 z 22 przypadkow - jakosciowo inaczej niz v2 (gdzie usuniecie CDR odwracalo
wniosek) i niz v3+stop (0/22 na uczciwym uniwersum).

## Wazne zastrzezenie: histereza jest niemal bezwladna

| | wartosc |
|---|---|
| obserwacje "trzymana poza top 8" | **22/970 (2.3%)** |
| miesiace z jakimkolwiek dropoutem | 21/246 (8.5%) |
| mediana liczby rankowanych spolek | **10** |
| transakcji | 26 w 246 miesiacach (1 na 9.5 mies.) |
| mediana czasu trzymania | 632 dni (1.7 roku), max 5997 dni (16.4 roku) |

Uniwersum PIT ma mediane **10 spolek**, wiec "poza top 8" znaczy w praktyce "badz w najgorszej
DWOJCE z dziesieciu". Regula podmiany prawie nie dziala - **v4 zachowuje sie glownie jak "wybierz 4
najlepsze wg score i trzymaj latami"**. To znaczy, ze przewaga pochodzi z RANKINGU PRZY WEJSCIU, a
nie z rotacji. Konsekwencja praktyczna: parametr `keep_rank=8` jest dostrojony do uniwersum
znacznie wiekszego niz to, ktore realnie mamy - przy 20-30 spolkach zachowywalby sie inaczej.

Najlepsza pojedyncza transakcja: **CDR +967.2%** (2016-01 -> 2019-08, 3.6 roku). Przy 4 pozycjach
jedna taka transakcja wazy bardzo duzo - dlatego test leave-one-out byl tu konieczny, a nie
opcjonalny.

## Decyzje implementacyjne wobec spec

1. **Value liczone jako RENTOWNOSCI, nie mnozniki**: `earnings_yield` (odwrotnosc P/E),
   `book_to_price` (odwrotnosc P/BV), `fcf_yield`. Ta sama tresc czynnika, ale odwrocenie usuwa dwie
   patologie: przy stracie P/E jest NIEOKRESLONE, a przy zysku bliskim zera leci do
   +nieskonczonosci (spolka na granicy rentownosci wygladalaby na "najdrozsza na rynku", mimo ze
   jest tuz obok tej ze strata). Rentownosc jest monotoniczna i ciagla przez zero.
2. **`ROA > 0` jest REDUNDANTNE z `zysk TTM > 0`** (przy dodatnich aktywach to dokladnie ten sam
   warunek), wiec te dwa kryteria zawsze zapalaja sie razem i "dodatni zysk" wazy w praktyce 40, a
   nie 20 pkt Quality. Zaimplementowane doslownie jak w spec, ale warto o tym wiedziec.
3. **Spolka poza top 8 zostaje, jesli nie ma kto jej zastapic** - spec wiaze sprzedaz z istnieniem
   kandydata z top 4, wiec sam spadek rankingu nie wypycha do gotowki (strategia jest zawsze
   zainwestowana, ekspozycja 99%).
4. **WIG20 przestal byc potrzebny**: v4 uzywa momentum ABSOLUTNEGO 12-1, a nie slabosci relatywnej
   wzgledem indeksu (jak v2/v3), wiec brak `wig20.txt` nie ogranicza tej wersji.

## Kapitalizacja point-in-time (`market_cap.py`) - warunek konieczny dla Value

BiznesRadar podaje `Liczba akcji` i `Kapitalizacja` TYLKO jako wartosc dzisiejsza. Uzycie
dzisiejszej liczby akcji dla calej historii bylo by powaznym bledem - `BalanceShareCapital` zmienil
sie miedzy najstarszym i najnowszym raportem np. CDR **10.6x**, TEN **22.3x**, PEP 4.3x. Liczbe
akcji odtwarzamy wiec z kapitalu zakladowego:

    nominal   = kapital_zakladowy_dzisiaj / akcje_dzisiaj
    akcje(t)  = kapital_zakladowy(t) / nominal

Splity nie wymagaja korekty: nie zmieniaja kapitalu zakladowego, a ceny stooq sa juz o nie
skorygowane. "Dzisiejsza" jest tylko KOTWICA JEDNOSTEK (liczba akcji), nie informacja o przyszlych
zwrotach; sam szereg kapitalu zakladowego jest w pelni point-in-time.

**Weryfikacja**: `ostatnia cena * liczba akcji` vs `Kapitalizacja` z BiznesRadaru - zgodnosc
0.988-1.027 dla **22/22** spolek. Ten test zlapal realny blad regexa (wzorzec przeskakiwal zwykly
`<td>` i zwracal Enterprise Value zamiast kapitalizacji - dla LWB 314 mln zamiast 755 mln, co
dawalo ilorazy od 0.46 do 2.38).

**Ograniczenie**: metoda zaklada stala wartosc nominalna akcji. Zmiana denominacji ja lamie -
wykrywalne (dla ALE iloraz kapitalu zakladowego to 0.024, czyli 40-krotny SPADEK) i odrzucane
(zwracamy None zamiast bledna wartosc).

## Kanarek WIG20 > 10M MA (`canary.py`) - sprawdzony, SZKODZI

User: "dodajmy kanarek WIG20 > 10M MA". Regula: risk-on <=> zamkniecie ostatniego ZAKONCZONEGO
miesiaca > srednia z 10 ostatnich zamkniec miesiecznych. W dniu decyzyjnym (1. dzien miesiaca M)
srednia siega najdalej do miesiaca M-1 - uzycie zamkniecia miesiaca M byloby look-ahead.

Sam filtr dziala poprawnie i sensownie odwzorowuje historie: **2008: 0% risk-on**, 2020: 8%,
2022: 8%, a w hossach (2006, 2017, 2021, 2026) 90-100%. Ogolem 57% miesiecy risk-on.

| wariant | CAGR | MaxDD | Sharpe | Calmar | n |
|---|---|---|---|---|---|
| v4 bez kanarka (ekspozycja 99%) | **14.42%** | -57.97% | **0.660** | **0.249** | 26 |
| v4 + kanarek (sprzedaje wszystko, ekspozycja 55%) | 5.55% | -38.89% | 0.409 | 0.143 | 86 |
| v4 + kanarek (tylko blokuje wejscia, ekspozycja 99%) | 6.36% | -57.97% | 0.379 | 0.110 | 20 |
| benchmark PIT 100% | 9.64% | -55.06% | 0.525 | 0.175 | - |
| **benchmark PIT skalowany do 55%, ZERO timingu** | **5.87%** | **-34.72%** | **0.525** | **0.169** | - |

**Kanarek zabiera 8.9pp CAGR i przewraca wynik z "bije benchmark o +4.78pp" na "przegrywa".**
Poprawia MaxDD (-58% -> -38.9%), ale to nie jest dobry handel: bierne trzymanie 55% benchmarku,
z zerowym timingiem, bije wersje z kanarkiem na KAZDEJ metryce, wliczajac obsuniecie (5.87% vs
5.55%, Sharpe 0.525 vs 0.409, MaxDD -34.7% vs -38.9%).

### Dlaczego szkodzi: to NIE whipsaw, to konflikt czynnikow

Naturalna hipoteza brzmialaby "wymuszona sprzedaz w risk-off = whipsaw" (19 z 67 wyjsc kanarkiem
konczylo sie odkupem TEJ SAMEJ spolki w <=100 dni po WYZSZEJ cenie). Ale wariant, ktory NIC nie
sprzedaje, a tylko blokuje nowe wejscia, wypada **jeszcze gorzej** na Sharpe (0.379) i Calmar
(0.110). Czyli glowny koszt to BLOKOWANIE WEJSC, nie sprzedaz.

Powod jest strukturalny. Zwroty transakcji v4 wg rezimu W MOMENCIE WEJSCIA:

| wejscia w | n | sredni zwrot | mediana | zyskownych |
|---|---|---|---|---|
| **risk-OFF** | 12 | **+107.67%** | **+25.81%** | 67% |
| risk-ON | 14 | +42.73% | +16.79% | 64% |

v4 ma 40% wagi w Value, a okazje valuowe pojawiaja sie wtedy, gdy rynek SPADA - czyli dokladnie
wtedy, gdy kanarek mowi "nie wchodz". Te dwa mechanizmy sa sobie strukturalnie przeciwne. Najlepsza
transakcja w calej historii (CDR +967%, wejscie 2016-01) byla wejsciem w RISK-OFF, podobnie ACP
+187%. Mediana (odporna na ten jeden wynik) tez faworyzuje risk-off, wiec wniosek nie stoi na
pojedynczym odstajacym przypadku - choc probka (12 vs 14 transakcji) jest mala.

**Wniosek**: kanarek WIG20 > 10M MA jest poprawnie zaimplementowany i historycznie trafnie wykrywa
bessy, ale doklejony do strategii valuowej odbiera jej wlasnie te wejscia, z ktorych bierze
przewage. Nie wdrazac w v4. Moglby miec sens w strategii MOMENTUM (gdzie kierunek sygnalu jest
zgodny z rezimem), nie w valuowej.

## Co dalej

1. **Poszerzyc uniwersum** - to wciaz jedyne, co realnie moze podwazyc ten wynik. Przy 10 spolkach w
   rankingu i 4 slotach histereza top-8 jest bezwladna, a 26 transakcji to mala probka. Priorytet:
   spolki wycofane z obrotu (survivorship), potem wiecej nazw ogolem.
2. **Dopasowac `keep_rank` do realnego rozmiaru uniwersum** (np. polowa rankingu, nie stale 8) -
   inaczej testujemy "kup i trzymaj 4 najlepsze", a nie zadeklarowana rotacje.
3. Dopiero potem sweep wag - zgodnie z zasada, ze nie ratujemy optymalizacja czegos, co nie ma
   przewagi. Tutaj przewaga jest, wiec sweep ma sens, ale najpierw fundament danych.

---

# Koncepcja v5: Quality Defensive (uniwersum 22 spolki)

Spec (user): uniwersum duze/plynne PIT, "na poczatek non-financials"; QUALITY 0-100 z wysokiego
**ROE TTM**, wysokiego **ROIC TTM** i niskiego **Debt / Market Cap**; DEFENSIVE 0-100 z niskiej
zmiennosci, `VOL = srednia(vol_6m, vol_12m)`, nizsza zmiennosc = wyzszy score; `FINAL = 50% QUALITY
+ 50% LOW_VOL`; kupujemy **top 5**, **maks 1 wymiana na miesiac**.

**Nie wymagalo nowego silnika.** v5 rozni sie od v4 WYLACZNIE scoringiem, wiec `factor_backtest.py`
dostal parametr `scorer=` (funkcja `(data, inwestowalne, ceny) -> ranking`), a v5 wstrzykuje
`defensive_scoring.build_scorer`. Mechanika slotow, podmiany i ksiegowania jest ta sama,
przetestowana - zadna trzecia kopia. `keep_rank = entry_rank = 5`, bo spec nie przewiduje histerezy
(v4 mial top 4 / top 8).

## Wynik (okno 2006-03 -> 2026-08)

| | CAGR | MaxDD | Sharpe | Calmar | transakcji |
|---|---|---|---|---|---|
| **v5** | 9.61% | **-49.63%** | **0.555** | **0.194** | 101 |
| buy&hold uniwersum PIT (uczciwy benchmark) | 9.61% | -55.06% | 0.521 | 0.175 | - |
| v5 + kanarek WIG20 > 10M MA | 4.58% | -33.59% | 0.389 | 0.136 | 141 |
| buy&hold STALE 21 non-financials (survivorship!) | 14.59% | -69.89% | 0.629 | 0.209 | - |

**Zwrot: dokladny remis.** CAGR v5 to 9.6142%, benchmarku 9.6105% - roznica **+0.004pp**, czyli
zero. Poprawa jest wylacznie po stronie ryzyka: MaxDD -49.6% vs -55.1%, Sharpe 0.555 vs 0.521,
Calmar 0.194 vs 0.175. To spojne z zamyslem "defensive" (mniej ryzyka za ten sam zwrot), ale to NIE
jest przewaga w zwrocie, jakiej szukalismy w v4.

Kontrola w podokresach - remis nie jest artefaktem jednego okna, ale nie jest tez stabilny:

| od | v5 CAGR | benchmark | roznica |
|---|---|---|---|
| 2006-03 | 9.61% | 9.61% | +0.00pp |
| 2011-01 | 9.68% | 10.30% | **-0.62pp** |
| 2016-01 | 17.26% | 17.23% | +0.03pp |

## Test kruchosci leave-one-out: remis na pelnej probce NIE jest odporny

| | wynik |
|---|---|
| bije wlasny benchmark na **CAGR** | **6/21** - i tylko **2** to prawdziwe wygrane (ASB +0.38pp, DNP +0.04pp) |
| pozostale 4 "wygrane" | dokladne remisy +0.00pp (DOM, DVL, NEU, PEP **nigdy nie wchodza do uniwersum PIT**, wiec przebieg jest identyczny z pelnym) |
| przegrywa z wlasnym benchmarkiem | **15/21**, od -0.18pp do **-1.91pp** |
| bije wlasny benchmark na **Sharpe** | 14/21 |
| rozrzut CAGR | 3.94pp (5.87% - 9.81%) |

To najwazniejszy wynik tego testu i zmienia interpretacje remisu z pelnej probki. Remis +0.004pp nie
jest "granica przewagi", jest **srodkiem rozkladu przechylonego na minus**: usuniecie prawie
dowolnej pojedynczej spolki sprawia, ze v5 wypada PONIZEJ swojego benchmarku na zwrocie. Najgorsze
przypadki to usuniecie ACP (-1.91pp), CPS (-1.41pp) i CDR (-1.24pp).

Jednoczesnie przewaga na **Sharpe utrzymuje sie w 14 z 21 przypadkow** - czyli redukcja ryzyka jest
znacznie bardziej powtarzalna niz zwrot. Dla porownania v4 mial 21/22 na OBU metrykach.

## Dlaczego remis: top 5 to 60% uniwersum

| | wartosc |
|---|---|
| spolek rankowanych w miesiacu | mediana 9, min 3, max 16 |
| udzial rankowanego uniwersum trzymany w portfelu | **srednio 60%, mediana 56%** |
| miesiace, w ktorych trzymamy >=80% uniwersum | 23% |
| miesiace, w ktorych rankowanych bylo <=5 spolek | **23%** (czyli: kup wszystko) |
| lata 2006-2010 | 3-5 spolek w rankingu |

Przy 5 slotach i medianie 9 rankowanych spolek v5 **z konstrukcji jest blisko benchmarku** - w co
czwartym miesiacu kupuje cale dostepne uniwersum, a w pozostalych odrzuca srednio 4 nazwy. Scoring
nie ma na czym pracowac. Dla porownania v4 trzymal 4 z 10 (40%) i mial przewage +4.78pp; roznica
miedzy tymi wersjami to nie tylko czynniki, ale i **selektywnosc**.

## Brak histerezy = 4x wieksza rotacja, i to kosztuje

| | v5 (top 5 / top 5) | v4 (top 4 / top 8) |
|---|---|---|
| transakcji | **101** | 26 |
| mediana czasu trzymania | **122 dni** | 632 dni |
| miesiecy z wymiana | 96/246 (39%) | 21/246 (8.5%) |

Bez buforu miedzy `entry_rank` i `keep_rank` pozycja wypada z portfela za sam spadek o jedno
miejsce w rankingu. Limit "1 wymiana na miesiac" ze spec to jedyny hamulec i wiaze - w 96 z 246
miesiecy zostal wykorzystany do konca. Efekt jest mierzalny:

| koszty transakcyjne | CAGR | Sharpe |
|---|---|---|
| 40 bps (realistyczne, jak w calym repo) | 9.61% | 0.555 |
| 0 bps (hipotetyczne) | 10.16% | 0.579 |

**Rotacja zjada 0.55pp CAGR rocznie - czyli dokladnie tyle, ile wynosi cala przewaga brutto v5 nad
benchmarkiem.** Strategia "zarabia" na scoringu tyle, ile placi maklerowi.

## Kanarek: ten sam wniosek co w v4

Kanarek WIG20 > 10M MA zabiera **5.03pp CAGR** (9.61% -> 4.58%) i obniza Sharpe (0.555 -> 0.389),
mimo ze poprawia MaxDD. Ekspozycja spada do 54%, a liczba transakcji rosnie z 101 do 141. To
niezalezne potwierdzenie mechanizmu opisanego przy v4: filtr rezimu blokuje wejscia dokladnie
wtedy, gdy pojawiaja sie okazje. Nie wdrazac.

## Decyzje implementacyjne wobec spec

1. **ROIC** - spec podaje tylko nazwe. Uzyty mianownik to `dlug oprocentowany + kapital wlasny`
   (invested capital), licznik `EBIT TTM * (1 - 0.19)`; 19% to realna stawka CIT w Polsce, wiec
   NOPAT jest przyblizeniem podrecznikowym, nie zgadywaniem. Stawka jest parametrem (`tax_rate`).
2. **Ujemny kapital wlasny uniewaznia ROE i ROIC** (zwracamy None), a nie daje ujemnej wartosci.
   Przy ujemnym mianowniku spolka z ogromna STRATA wychodzilaby na najbardziej rentowna w rankingu.
3. **Zerowa zmiennosc = wykluczenie**, nie "najbezpieczniejsza spolka swiata". Stala cena przez cale
   okno oznacza zawieszone notowania albo martwy szereg; bez tego takie papiery dostawalyby
   LOW_VOL = 100 i zajmowaly caly portfel.
4. **Zmiennosc liczona z PELNEGO okna** (126 / 252 sesji) - swiezo notowana spolka nie moze dostac
   niskiej zmiennosci z kilku dni. Okno konczy sie na dniu decyzyjnym WLACZNIE, bo dzienna cena z
   tego dnia jest wtedy znana (inaczej niz kanarek, ktory operuje na zamknieciach miesiecznych).
5. **Non-financials wykluczone na poziomie uniwersum** (`universe.non_financial_tickers`), nie w
   scoringu. Dla banku/windykatora `Debt / MarketCap` mierzy skale biznesu, nie ryzyko. W danych jest
   dokladnie jedna taka spolka: **KRU (Wierzytelnosci)**, wiec uniwersum to 21 z 22 nazw. Branza
   czytana jest z profilu BiznesRadaru (pole `Branza:`; pola "Sektor" tam NIE ma) i jest wartoscia
   dzisiejsza - ale przynaleznosc branzowa duzej spolki praktycznie sie nie zmienia, a wykluczenie
   finansowych jest decyzja o KONSTRUKCJI wskaznika, nie sygnalem o zwrotach. Spolka o nieznanej
   branzy ZOSTAJE w uniwersum (brak wpisu nie jest dowodem, ze to bank).
6. **Dlug bez leasingu** - tak jak w `scoring.py` (IFRS 16 wprowadzil nieciaglosc w 2019, ktora
   dodala wszystkim spolkom "dlug" z dnia na dzien bez zmiany sytuacji ekonomicznej).

## Wniosek

v5 robi to, co obiecuje etykieta "defensive", ale slabiej niz wygladalo to na pelnej probce:

- **zwrot: brak przewagi.** Remis na pelnym oknie (+0.004pp) nie jest odporny - leave-one-out daje
  6/21, z czego tylko 2 prawdziwe wygrane, a 15 przebiegow przegrywa (do -1.91pp).
- **ryzyko: przewaga jest, i jest powtarzalna.** MaxDD -49.6% vs -55.1%, Sharpe 0.555 vs 0.521,
  a na Sharpe 14/21 w leave-one-out. To jedyny realny efekt tej wersji.
- **przyczyna slabosci jest strukturalna, nie parametryczna.** Top 5 z 9 rankowanych nazw to
  benchmark z lekkim przechyleniem (w 23% miesiecy kupujemy cale uniwersum), a caly zarobek brutto
  na scoringu (+0.55pp) jest zjadany przez rotacje wywolana brakiem histerezy (0.55pp kosztow).

**Nie ma tu czego optymalizowac wagami** - z 9 nazwami w rankingu i 5 slotami zaden zestaw wag nie
zrobi ze v5 strategii selekcji. Ograniczeniem jest rozmiar uniwersum, ten sam, ktory zostal wskazany
jako priorytet po v4. Wersja do porownania pozostaje v4 (+4.78pp CAGR, 21/22 leave-one-out).

---

# Koncepcja v3: bez podmiany po score + trailing stop (uniwersum 22 spolki)

Spec (user): entry `DD >= 25%` + quality gate; max 4 pozycje; holding **36 miesiecy**; bez profit
targetu; **bez comiesiecznej podmiany po score** - nowy kandydat zastepuje pozycje tylko gdy ta (1)
nie przechodzi quality gate albo (2) osiagnela 36 miesiecy. Score sluzy WYLACZNIE do wyboru
kandydata na wolny slot. Plus: `highest_close_since_entry` i **trailing stop** (sprzedaj przy
spadku o np. 20% od szczytu od zakupu).

**v3 nie wymagalo nowego silnika.** Warunki "nie przechodzi quality gate" i "osiagnela 36 miesiecy"
to DOKLADNIE istniejace wyjscia `fundamental_fail` i `timeout`, po ktorych zwolniony slot i tak jest
wypelniany najlepszym kandydatem. Wystarczyla flaga `allow_score_replacement=False` +
`max_holding_months=36`. Trailing stop to nowe pole `Position.highest_close`, aktualizowane
**codziennie** (stop jest zleceniem stojacym - kontrola raz w miesiacu przepuszczalaby obsuniecia
znacznie glebsze niz zadeklarowany prog).

## Wyniki - i dlaczego uniwersum decyduje o wszystkim

| wariant | CAGR | MaxDD | Sharpe | Calmar | transakcji |
|---|---|---|---|---|---|
| v2 (podmiana po score, 24m), uniwersum stale | 10.61% | -65.82% | 0.540 | 0.161 | 114 |
| v2, uniwersum PIT | 8.25% | -48.84% | 0.463 | 0.169 | 63 |
| v3 (bez podmiany, 36m), uniwersum stale | 13.34% | -60.99% | 0.645 | 0.219 | 34 |
| v3, uniwersum PIT | 3.17% | -66.43% | 0.252 | 0.048 | 26 |
| **v3 + trailing stop 20%, uniwersum stale** | **23.34%** | -57.10% | **1.011** | **0.409** | 137 |
| **v3 + trailing stop 20%, uniwersum PIT** | **5.74%** | -47.07% | **0.360** | 0.122 | 130 |
| v3 + trailing stop 30%, uniwersum PIT | 7.84% | -68.65% | 0.425 | 0.114 | 77 |
| v3 + trailing stop 15%, uniwersum PIT | 3.94% | -51.32% | 0.291 | 0.077 | 190 |
| *benchmark: buy&hold 22 spolki (survivorship!)* | *14.56%* | *-69.89%* | *0.634* | *0.208* | - |
| *benchmark: buy&hold uniwersum PIT (uczciwy)* | *9.64%* | *-55.06%* | *0.525* | *0.175* | - |

Dwa czytania tej tabeli:

1. **Na stalej liscie ocalalych v3 + trailing stop wyglada znakomicie**: CAGR 23.34%, Sharpe 1.011,
   Calmar 0.409 - bije survivorship-benchmark o ~9pp CAGR. I NIE jest to artefakt jednej spolki:
   leave-one-out po wszystkich 22 nazwach bije wlasny benchmark **22/22** razy (rozrzut CAGR
   16.28%-25.28%), a usuniecie CDR praktycznie nic nie zmienia (23.17% vs 23.34%) - w przeciwienstwie
   do "odkrycia" z v2, ktore bylo w calosci CDR-owe.
2. **Na uczciwym uniwersum PIT ta sama strategia przegrywa**: 5.74% vs 9.64% benchmarku, Sharpe
   0.360 vs 0.525. Zmiana jednej rzeczy - definicji uniwersum - zabiera 17.6pp CAGR.

## Test kruchosci leave-one-out: wynik jest jednoznaczny w OBU kierunkach

Ten sam test (usun po kolei kazda z 22 spolek, porownaj z benchmarkiem liczonym na tej samej,
pomniejszonej puli) na obu definicjach uniwersum:

| uniwersum | bije wlasny benchmark | rozrzut CAGR | zakres przewagi |
|---|---|---|---|
| **stale (survivorship)** | **22/22** | 9.00pp (16.28%-25.28%) | od +2.32pp do +10.50pp |
| **point-in-time (uczciwe)** | **0/22** | 4.24pp (3.11%-7.35%) | od -1.10pp do -5.08pp |

To nie jest szum. Na obciazonym uniwersum strategia wygrywa ZAWSZE, na uczciwym przegrywa ZAWSZE, a
rozrzut na PIT jest waski (4.24pp) - czyli wynik nie zalezy od zadnej pojedynczej spolki, tylko od
tego, jak zdefiniowane jest uniwersum. Ciekawostka: na PIT najlepszy wariant to ten BEZ CDR
(7.35%, luka tylko -1.10pp) - CDR pogarsza wynik, gdy nie mozna go kupic w latach mikrospolki, bo
strategia lapie go dopiero po duzej czesci wzrostu.

## Skad ta roznica: zwroty siedzialy w nazwach NIEPLYNNYCH

Sweep progu plynnosci (v3, bez trailing stopu):

| prog plynnosci | srednio spolek | CAGR | Sharpe |
|---|---|---|---|
| 0.0 mln (tylko data debiutu) | 11.9 | **11.65%** | 0.594 |
| 0.5 mln | 9.0 | 2.72% | 0.233 |
| 1.0 mln | 7.9 | 2.12% | 0.208 |
| 2.0 mln | 7.0 | 3.17% | 0.252 |
| 5.0 mln | 5.8 | 3.88% | 0.281 |
| 10.0 mln | 4.4 | 4.09% | 0.293 |

Urwisko miedzy progiem 0 i 0.5 mln jest kluczowe: **caly wynik pochodzil z nazw malych i
nieplynnych**. W uniwersum faktycznie "duzych i plynnych" - a takie bylo zalozenie spec - efekt
znika. Do tego te nieplynne nazwy to w tej probce dokladnie te, ktore urosly kilkukrotnie (CDR w
latach mikrospolki, DNP, TEN, TXT, DVL), wiec czesc tego "efektu malych spolek" to po prostu
survivorship w innym przebraniu.

## Trailing stop: mechanicznie dziala, ale zmienia charakter strategii

Statystyki (uniwersum stale, prog 20%): 137 transakcji, **126 wyjsc stopem**, 6 fundamental fail,
tylko **1 timeout 36m**. Trafnosc 45% (61/137), ale sredni zwrot **+21.00%**. Mediana trzymania 126
dni, zero transakcji 0-dniowych (brak churnu).

To klasyczna asymetria trend-followingu: ucinaj straty na -20%, pozwol zwyciezcom rosnac. Ale
konsekwencja jest taka, ze **trailing stop przejal role glownego mechanizmu wyjscia** (92% wyjsc) -
limit 36 miesiecy praktycznie nie dziala, a strategia przestaje byc "cierpliwym value" i staje sie
trend-followingiem z valuowym filtrem wejscia. To ten sam wzorzec, co w v2 (tam role wyjscia przejela
regula podmiany) - warto o tym wiedziec swiadomie, bo spec zaklada cos innego.

## Wniosek

- **Poprawa uniwersum byla wazniejsza niz wszystkie zmiany regul razem.** Ta sama strategia daje
  23.34% albo 5.74% w zaleznosci od tego, czy uniwersum jest uczciwe. Zadna zmiana parametrow nie ma
  takiej sily.
- **v3 > v2 na stalym uniwersum** (13.34% vs 10.61%, Sharpe 0.645 vs 0.540) - usuniecie podmiany po
  score realnie pomoglo, przy 3x mniejszej liczbie transakcji. To potwierdza wczesniejsza diagnoze,
  ze podmiana dzialala jak ukryty profit target.
- **v2 > v3 na uniwersum PIT** (8.25% vs 3.17%) - zaleznosc sie odwraca. Przy waskim uniwersum
  (3-15 spolek) trzymanie pozycji 36 miesiecy bez mozliwosci podmiany jest kosztowne, bo nie ma
  z czego wybierac przy nastepnej okazji.
- **Trailing stop jest jedyna zmiana, ktora przeszla test leave-one-out 22/22** - ale tylko na
  uniwersum obciazonym. Na PIT nie ratuje wyniku.
- Zadna z trzech wersji nie bije uczciwego benchmarku PIT.

---

# Koncepcja v1: "przeceniona + zdrowa, profit target" (odrzucona)

Uniwersum 4 spolki (DNP, CDR, KGH, PKN), okno 2006-03 -> 2026-08. Bramka: dd <= -25% + zdrowe
fundamenty. Wyjscie: +20% od wejscia albo 6 miesiecy.

| | CAGR | MaxDD | Sharpe | Calmar |
|---|---|---|---|---|
| strategia (ekspozycja 31%) | 3.27% | -42.72% | 0.288 | 0.077 |
| buy&hold 4 spolki (100%) | 18.94% | -80.04% | 0.651 | 0.237 |
| **buy&hold skalowany do 31%, zero timingu** | **7.15%** | **-37.22%** | **0.651** | **0.192** |

**Koncepcja niszczy wartosc**: "trzymaj 31% tych spolek na stale, bez zadnego sygnalu" bije ja na
kazdej metryce. Statystyki transakcji wygladaly przy tym niewinnie (47 transakcji, 62% zyskownych,
srednio +6.08%) - dowod, ze sam "win rate" jest mylacym miernikiem.

Sweep 14 wariantow: (1) regula wyjscia ucina zwyciezcow (3m->24m: CAGR 2.38%->8.16%; +10%->+60%:
2.55%->5.91%); (2) filtr fundamentalny realnie pomagal (bez niego 1.98% / MaxDD -62%).
