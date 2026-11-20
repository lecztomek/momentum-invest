# Panel strategii BEST17 + GPM UK

Statyczna strona pod GitHub Pages. **Nic tu nie liczy strategii** — sygnały wylicza
silnik w Pythonie (`strategies_v2/`) uruchamiany przez GitHub Actions, a strona
wyłącznie czyta gotowe pliki JSON z `docs/data/`.

## Uruchomienie lokalnie

Strona czyta dane przez `fetch`, więc musi być serwowana po HTTP — otwarcie
`index.html` z dysku nie zadziała.

    cd docs && python3 -m http.server 8000

## Pliki

| Plik | Co zawiera | Kto zapisuje |
|---|---|---|
| `index.html` | szkielet widoków | ręcznie |
| `app.css` | style, motyw ciemny jednowariantowy | ręcznie |
| `app.js` | render i wykresy (moduł ES, bez bibliotek) | ręcznie |
| `data/signals.json` | sygnał obu transz, historia, ranking, kanarek | pipeline |
| `data/performance.json` | miesięczne stopy zwrotu strategii | pipeline |
| `data/prices.json` | instrumenty źródłowe i stan feedu | pipeline |
| `data/portfolio.json` | kapitał, stan posiadania, krzywa wartości | docelowo baza |
| `.nojekyll` | wylacza Jekylla na Pages (serwuje pliki bez przetwarzania) | — |

Zadnego pliku w `docs/` nie generuje sie w trakcie wdrozenia - co w repo, to na stronie.

`data/portfolio.json` jest tu tylko dla prototypu — docelowo te dane są prywatne
i idą do bazy (per użytkownik), a nie do repozytorium.

## Publikacja

Settings → Pages → Source: **Deploy from a branch** → galaz `main`, folder **`/docs`**.
Adres: `https://<uzytkownik>.github.io/momentum-invest/`.

GitHub przebudowuje strone sam po kazdym pushu na `main`, wiec osobny workflow
wdrazajacy nie jest potrzebny. Pipeline cenowy bedzie commitowal pliki do
`docs/data/` i to wystarczy, zeby strona pokazala nowe dane.

## Stan

Prototyp. Wszystkie liczby w `data/` są przykładowe.
