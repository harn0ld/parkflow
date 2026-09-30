# Kontrakt agregatów (pipeline → model)

Interfejs między pipeline'em PySpark (`pipeline/aggregate.py`, uruchamiany w `datasprint`) a modelem (`parkflow/`).
Źródłem kontraktu jest to, co pipeline faktycznie produkuje: `data/agg/*.parquet` i docstring `pipeline/aggregate.py`.
Kod pilnujący schematu: `parkflow/dane.py` (`KONTRAKT`, `sprawdz_kontrakt`), test: `tests/test_model.py`.

- **Prawdziwe agregaty:** `data/agg/` (wynik pipeline'u na pełnych danych; próg ≥ 30 unikalnych kart).
- **Przykładowe agregaty:** `data/sample/` — ten sam schemat, liczby zmyślone, 16 kodów, oba sezony, wszystkie bloki.
  Generator: `python data/sample/zbuduj.py`. Na nich działają testy modelu i aplikacja bez dostępu do `datasprint`.
- Aplikacja i `wczytaj_agregaty()` czytają domyślnie `data/agg/`, a gdy go brak — `data/sample/`.

## Słowniki

| Pole | Wartości |
|---|---|
| `kod` | kod pocztowy sprzedawcy `9X-XXX` (Łódź 90–94). Bez kodów zbiorczych (`kody_zbiorcze`) i galerii z własnym parkingiem (`data/wykluczenia_kody.csv`). |
| `blok` | `07-10`, `10-13`, `13-16`, `16-19` (czas lokalny Europe/Warsaw, pn–pt bez świąt) |
| `sezon` | `lato` (VI–IX 2025), `rok_akademicki` (X 2025 – VI 2026) |
| `grupa` | `szybkie_uslugi`, `spozywcze_male`, `handel`, `gastronomia`, `uslugi_osobiste`, `rozrywka_kultura` (`data/mcc_groups.csv`) |

## `agg_grupy` — kod × blok × sezon × grupa usług

Wiersz istnieje tylko dla grup z ≥ 30 unikalnymi kartami przyjezdnymi (grupy poniżej progu nie są eksportowane).

| Kolumna | Typ | Znaczenie |
|---|---|---|
| `kod`, `blok`, `sezon`, `grupa` | string | klucz komórki |
| `karty_przyjezdne` | int | unikalne karty przyjezdne (`pstl_cd_enr` ≠ kod sprzedawcy lub brak) w sezonie, ≥ 30 |
| `wspolczynnik_kierowcow` | float 0–1 | odsetek par karta×dzień z opłatą parkingową (MCC 7523) w Łodzi tego dnia. W buforze: współczynnik z SPP dla grupy (dolne oszacowanie). |
| `mediana_czasu_wizyty_min` | float | mediana czasu wizyty [min] (zmierzony + czas domyślny grupy) |
| `presja` | float | mediana po tygodniach roboczych sezonu z (karty tygodnia × współczynnik × czas / 60) — **samochodo-godziny/tydzień**; tygodnie bez wizyt liczą się jako 0 |
| `spp` | bool, nullable | `true` = obecna SPP, `false` = bufor; **pusta**, dopóki pipeline nie dostanie `data/spp_kody.csv` (ticket 02) |

## `agg_strefy` — kod × blok × sezon (wejście modelu tabeli P)

| Kolumna | Typ | Znaczenie |
|---|---|---|
| `kod`, `blok`, `sezon` | string | klucz komórki |
| `karty_przyjezdne` | float, nullable | unikalne karty przyjezdne w komórce (wszystkie grupy); pusta, gdy < 30 |
| `presja` | float, nullable | mediana po tygodniach z Σ presji grup (także grup < 30 kart) [samochodo-h]; pusta, gdy < 30 kart |
| `za_malo_danych` | bool | `true`, gdy komórka ma < 30 unikalnych kart przyjezdnych |
| `spp` | bool, nullable | jak w `agg_grupy` |

Uwagi:
- Siatka jest **rzadka**: komórka bez wizyt przyjezdnych nie ma wiersza. Model uzupełnia pełną siatkę kod × 4 bloki × 2 sezony i traktuje brak jako „za mało danych”.
- `presja` strefy ≠ Σ `presja` z `agg_grupy` (mediana sumy vs suma median, plus grupy < 30 kart). W danych przykładowych jest równa sumie dla prostoty.
- Kwota transakcji nie wchodzi do presji. Udział Visa w rynku ignorujemy (SPEC §4.3: przy stałych progach zakładamy podobny udział w miastach i w czasie).

## `agg_kalibracja_czasow` — grupa usług (kalibracja czasów domyślnych, ticket 05)

Opcjonalny: `wczytaj_agregaty()` zwraca `kalibracja = None`, gdy pliku brak (agregaty sprzed ticketu 05).
Te same wizyty co w presji (przyjezdne, dni robocze sezonów, w blokach), tylko z ≥ 2 transakcjami.
Wiersz istnieje tylko dla grup z ≥ 30 unikalnymi kartami takich wizyt.

| Kolumna | Typ | Znaczenie |
|---|---|---|
| `grupa` | string | grupa usług wizyty (= grupa ostatniej transakcji) |
| `czas_domyslny_min` | int | obecny czas domyślny grupy z `data/mcc_groups.csv` |
| `wizyty_wielotransakcyjne` | int | liczba wizyt z ≥ 2 transakcjami (oba sezony) |
| `karty` | int | unikalne karty tych wizyt, ≥ 30 |
| `udzial_wielotransakcyjnych` | float 0–1 | udział wizyt wielotransakcyjnych wśród wszystkich wizyt grupy |
| `mediana_czasu_zmierzonego_min` | float | mediana czasu pierwsza → ostatnia transakcja [min], bez startu od opłaty parkingowej i bez czasu domyślnego |

## `agg_parkomaty_strefy` — kod × blok × sezon (zmierzony popyt, ticket 07)

Opcjonalny: `wczytaj_agregaty()` zwraca `popyt = None`, gdy pliku brak. Warstwa „Zmierzony popyt” na mapie.
Opłaty MCC 7523 w parkomatach SPP (`SPP Lodz <nr>`) w dni robocze sezonu, w blokach; kod = kod pocztowy
lokalizacji parkomatu z `data/parkomaty.csv` (parkomaty „lokalizacja nieznana” nie wchodzą).
Minuty: `cs_tran_amt / 0,92` → `data/cennik_spp.csv` z dnia opłaty, podstrefy parkomatu i ulgi (`lau_enr = LODZ`).
Wiersz istnieje tylko dla komórek z ≥ 30 unikalnymi kartami płacącymi.

| Kolumna | Typ | Znaczenie |
|---|---|---|
| `kod`, `blok`, `sezon` | string | klucz komórki |
| `oplacone_autogodziny` | float | mediana po tygodniach roboczych sezonu z Σ opłaconych minut / 60 — **auto-godziny/tydzień**, jak `presja`; tygodnie bez opłat liczą się jako 0 |
| `karty` | int | unikalne karty płacące w parkomatach kodu w sezonie i bloku, ≥ 30 |

## Pozostałe agregaty pipeline'u (poza tym kontraktem, dla kolejnych ticketów)

Opisane w docstringu `pipeline/aggregate.py`; model ich jeszcze nie czyta, więc nie mają wersji przykładowej.

| Plik | Klucz | Kolumny | Uwagi |
|---|---|---|---|
| `agg_parkomaty` | parkomat × okres × blok | `podstrefa`, `platnosci`, `karty`, `mediana_minut`, `autogodziny_tydz_mediana`, … | `kod` pusty bez `data/parkomaty.csv` |
| `agg_stali` | parkomat × sezon | `kod`, `karty`, `udzial_stalych` | stali bywalcy, tylko informacyjnie |
| `agg_spp_okres` | okres × blok × podstrefa | `platnosci`, `mediana_minut`, `udzial_powyzej_2h`, … | naturalny eksperyment (ticket 12) |
| `kody_zbiorcze` | kod | `sprzedawcy`, `transakcje` | kody > 400 sprzedawców, wyłączone ze stref |

## Prywatność

Żaden plik nie zawiera identyfikatora karty ani sekwencji transakcji (SPEC §7). Każda liczba kart w eksporcie jest ≥ 30.
