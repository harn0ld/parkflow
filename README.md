# ParkFlow

Poziomy priorytetu parkingowego P1–P4 dla Łodzi (demo hackathonowe). Decyzje: `SPEC.md`.

```
pipeline/    PySpark: transakcje Visa (datasprint) → agregaty data/agg/*.parquet (próg ≥ 30 kart)
parkflow/    model (czyste pandas): agregaty → tabela P, taryfy, mapa
app/         aplikacja Streamlit (tylko wyświetla wyniki modelu)
scripts/     budowanie danych pomocniczych (kody z PRG, parkomaty, zasięg parkomatów)
data/agg/    prawdziwe agregaty z pipeline'u (w repo, bez danych kartowych)
data/sample/ przykładowe agregaty w tym samym schemacie (docs/kontrakt-agregatow.md)
data/        dane referencyjne: cennik, grupy MCC, wykluczenia, parkomaty, kody pocztowe
tests/       testy pipeline'u (Spark lokalnie) i modelu
```

Wszystkie komendy uruchamiaj **z katalogu głównego repo** (`cd ~/Documents/parkflow`).

## 1. Szybki start: sama aplikacja (5 min)

Agregaty są już w repo (`data/agg/`), więc do obejrzenia demo nie potrzebujesz danych Visa ani Javy.

```bash
cd ~/Documents/parkflow
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app/main.py
```

Otwórz http://localhost:8501. Zakładki: **Mapa**, **Wyliczenia taryf**, **Karta kierowcy**, **Rekomendacje parkingowe**, **Edycja grup intensywności**.
**Rekomendacje parkingowe** wskazują sektory P3/P4 do analizy dodatkowych miejsc lub poprawy
organizacji postoju, z uzasadnieniem i eksportem CSV. Wysoka presja w co najmniej dwóch blokach
oznacza kandydata do sprawdzenia dodatkowych miejsc. To reguła priorytetyzacji analiz;
bez pomiarów zajętości i liczby miejsc nie określa niedoboru ani liczby miejsc do dodania.
W **Edycji grup intensywności** można zmieniać nazwy i opisy grup, dodawać własne grupy oraz
przypisywać sektory z wystarczającymi danymi. Zatwierdź zmiany przyciskami pod formularzami,
a następnie pobierz CSV przypisań dla wybranego sezonu i bloku lub katalog wszystkich grup.
Edycja jest zachowana w sesji przy zmianie sezonu i godzin; nie zmienia taryf ani poziomów modelu.
Po zakończeniu sesji zmiany pozostają wyłącznie w pobranych plikach.
Przełącznik **Przepływ w ciągu dnia** na mapie odtwarza dzień 7→19 (suwak i ▶). Sektory płynnie
przechodzą między czterema blokami, a przejścia są interpolacją wizualną, nie danymi godzinowymi.
Na mapie podpowiedzi zawierają rekomendowane taryfy, a osobna zakładka **Wyliczenia taryf** pokazuje wyliczenia
dla wybranego sektora: poziom P, korektę okresu preferencyjnego i koszt 1, 2 oraz 3 godzin postoju.
To propozycje modelu, nie obowiązujący cennik SPP.
Rekomendacje taryf pokazujemy tylko przy wystarczających danych: wyliczona presja,
co najmniej 30 kart przyjezdnych i brak flagi „za mało danych” w danym sezonie i bloku.
W pasku bocznym: sezon i blok czasu. Aplikacja korzysta wyłącznie z agregatów w `data/agg`.
Na **Mapie** checkbox **Parkomaty** włącza lokalizacje z mapy ZDiT (kolor = podstrefa).
Filtry usług i sklepów pozwalają wybrać grupy (np. małe sklepy spożywcze, gastronomię)
i minimalną liczbę kart przyjezdnych w grupie. Przy kilku grupach można wymagać spełnienia
progu dla dowolnej lub każdej z nich. To miara aktywności klientów Visa, nie liczby lokali.
Mapa pokazuje kody oznaczone jako SPP, bez bufora i kół zmierzonego popytu.
Po najechaniu na obszar widać grupy usług z liczbą kart przyjezdnych w wybranym sezonie i bloku
(co najmniej 30 kart na grupę), od najliczniejszej. Dane nie zawierają nazw konkretnych lokali.
Jeśli brakuje agregatów w `data/agg/`, aplikacja wyświetla komunikat o konieczności przygotowania danych.

## 2. Pełny przebieg: od surowych danych Visa do agregatów

Potrzebne tylko, gdy chcesz przeliczyć `data/agg/` (np. po zmianie filtrów, cennika albo parkomatów).

### 2.1. Java 17 (wymagana przez PySpark)

```bash
brew install openjdk@17
export JAVA_HOME=/opt/homebrew/opt/openjdk@17    # w każdej nowej sesji terminala albo w ~/.zshrc
```

### 2.2. Wyciągnięcie Łodzi z pełnego pliku (raz, ~25 min)

Plik `datasprint_sample_data.parquet` (17,5 GB, 305 mln transakcji) leży w katalogu głównym i jest w `.gitignore`.

```bash
PARKFLOW_DRIVER_MEMORY=8g .venv/bin/python -m pipeline.extract_lodz \
    datasprint_sample_data.parquet data/interim/lodz_all.parquet
```

Wynik: `data/interim/lodz_all.parquet` (~6,3 mln transakcji). **To dane na poziomie karty — nigdy ich nie commituj**
(`data/interim/` jest w `.gitignore`; SPEC §7).

Podgląd wartości kolumn filtrujących (same liczności): `.venv/bin/python -m pipeline.inspect_lodz`.

### 2.3. Agregaty (~2 min)

```bash
PARKFLOW_DRIVER_MEMORY=8g .venv/bin/python -m pipeline.aggregate data/interim/lodz_all.parquet data/agg
```

Wynik w `data/agg/`: `agg_strefy`, `agg_grupy`, `agg_parkomaty`, `agg_parkomaty_strefy`, `agg_spp_okres`,
`agg_stali`, `agg_kalibracja_czasow`, `kody_zbiorcze`. Opis kolumn: `docs/kontrakt-agregatow.md`.
Pipeline czyta dane referencyjne z `data/` (`--data` zmienia katalog).

### 2.3a. Kraków

Kraków ma własny katalog `data/krakow/` (kody, parkomaty ZDMK, cennik, galerie) i agregaty w
`data/krakow/agg/`. Grupy MCC i wykluczenia nazw są wspólne (`data/`). Źródła i ograniczenia:
`docs/research/krakow-spp.md` (numer parkomatu w Visa mają tylko sektory A3 i A13).

```bash
PARKFLOW_DRIVER_MEMORY=8g .venv/bin/python -m pipeline.extract_lodz \
  datasprint_sample_data.parquet data/interim/krakow_all.parquet --miasto krakow
PARKFLOW_DRIVER_MEMORY=8g .venv/bin/python -m pipeline.aggregate \
  data/interim/krakow_all.parquet data/krakow/agg --miasto krakow

# dane referencyjne Krakowa (tylko do odbudowy)
.venv/bin/python scripts/zbuduj_kody.py --miasto krakow
.venv/bin/python scripts/zbuduj_parkomaty_krakow.py          # parkomaty.xml ZDMK → parkomaty.csv, spp_kody.csv
.venv/bin/python scripts/zbuduj_zasieg_parkomatow.py --miasto krakow
```

Gdy są agregaty Krakowa, w pasku bocznym aplikacji pojawia się wybór miasta.

### 2.4. Dane referencyjne (tylko gdy trzeba je odbudować)

Są w repo; odbudowujesz je tylko po zmianie źródeł. Kolejność ma znaczenie:

```bash
# kody pocztowe z PRG → data/kody.geojson, data/kody_ulice.csv (pobiera PRG do data/raw/prg/, poza gitem)
.venv/bin/python scripts/zbuduj_kody.py

# parkomaty z mapy ZDiT → data/parkomaty.csv, data/spp_kody.csv, docs/parkomaty-georeferencja.md
# (wymaga tesseract: brew install tesseract; ręczne odczyty w data/raw/zdit/parkomaty_odczyty_reczne.csv)
.venv/bin/python scripts/digitalizuj_parkomaty.py

# zasięg 500 m parkomat → kody → data/parkomaty_zasieg.csv (po zmianie parkomatów albo kodów)
.venv/bin/python scripts/zbuduj_zasieg_parkomatow.py
```

Po każdej z tych zmian przelicz agregaty (krok 2.3).

| Plik | Co zawiera | Źródło |
|---|---|---|
| `data/mcc_groups.csv` | MCC → grupa usług + czas domyślny | SPEC §4.2 |
| `data/cennik_spp.csv` | cennik SPP w 3 okresach × podstrefa × ulga | `docs/research/lodz-spp.md` |
| `data/wykluczenia.csv` | wzorce nazw: dostawy, duże formaty, automaty, online | eksploracja danych |
| `data/wykluczenia_kody.csv` | kody galerii z własnym parkingiem | eksploracja danych |
| `data/parkomaty.csv`, `data/spp_kody.csv` | lokalizacja parkomatów, kody SPP | `scripts/digitalizuj_parkomaty.py` |
| `data/parkomaty_visa_id.csv` | 617 ID parkomatów z Visa (bez kart) | pipeline |

## 3. Testy

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@17
.venv/bin/python -m pytest tests -q
```

Same testy modelu (bez Javy): `.venv/bin/python -m pytest tests/test_model.py tests/test_taryfa.py -q`.
Test dymny schematu na prawdziwym pliku (czyta tylko stopkę i 500 wierszy):
`PARKFLOW_SAMPLE=datasprint_sample_data.parquet .venv/bin/python -m pytest tests/test_smoke_datasprint.py -q`.

Przykładowe agregaty (`data/sample/`) odbudujesz przez `.venv/bin/python data/sample/zbuduj.py`.

## 4. Typowe problemy

| Objaw | Rozwiązanie |
|---|---|
| `Unable to locate a Java Runtime` | krok 2.1 (`brew install openjdk@17` i `export JAVA_HOME=...`) |
| `No module named 'pipeline'` / `'parkflow'` | uruchamiasz z podkatalogu albo bez `-m`; wejdź do katalogu głównego i użyj `python -m pipeline....` |
| `PYTHON_VERSION_MISMATCH` (worker 3.14 vs driver 3.13) | używaj `.venv/bin/python`; pipeline ustawia `PYSPARK_PYTHON` na bieżący interpreter |
| `permission denied: ...py` | skrypty uruchamiaj przez interpreter: `.venv/bin/python skrypt.py` |
| Spark kończy się `OutOfMemory` | zwiększ `PARKFLOW_DRIVER_MEMORY` (np. `12g`) albo zmniejsz `PARKFLOW_CORES` |
| mapa w aplikacji jest pusta | przeglądarka bez WebGL; otwórz w zwykłym Chrome/Safari |
| aktywne środowisko conda (`(datasprint)`) | nie przeszkadza, o ile wołasz `.venv/bin/python`; samo `python` użyje condy |

Zmienne środowiskowe Sparka: `PARKFLOW_DRIVER_MEMORY` (np. `8g`), `PARKFLOW_CORES` (domyślnie wszystkie),
`PARKFLOW_SHUFFLE` (partycje, domyślnie 64), `SPARK_MASTER` (uruchomienie na klastrze zamiast lokalnie).

## 5. Uruchomienie w `datasprint`

Ten sam kod działa na klastrze: ustaw `SPARK_MASTER` (albo uruchom przez `spark-submit`), wskaż pełny plik
w kroku 2.2 i katalog wyjściowy w kroku 2.3. Poza środowisko chronione wynoś wyłącznie `data/agg/`.
