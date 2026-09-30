# ParkFlow – specyfikacja (demo hackathonowe + pilotaż Łódź)

Źródło prawdy dla zespołu. Zastępuje `docs/polityka-parkflow-v0.md` tam, gdzie się różnią. Fakty i źródła: `docs/research/lodz-spp.md`, `docs/research/visa-dane.md`.
Status: **do akceptacji** · 2026-09-29

## 1. Zasada

ParkFlow nie ustala ceny dla miejsca. Model przypisuje każdej **mikrostrefie × blokowi czasu** poziom priorytetu **P1–P4**, a każdy poziom ma z góry opublikowaną taryfę. Harmonogram poziomów publikujemy z wyprzedzeniem i rewidujemy kwartalnie. Nic nie zmienia się w czasie rzeczywistym, a stawka jest blokowana na starcie postoju.

**Cel operacyjny:** docelowe obłożenie ~85% (reguła Shoupa, 1–2 wolne miejsca na odcinku).
**Metryka do pitchu:** obroty lokalnego biznesu (dane Visa).
**Przychód miasta nie jest celem.**

## 2. Zakres

| | |
|---|---|
| Miasto | Łódź. Kody pocztowe 90-xxx–94-xxx, `mrch_ctry_nm = POLAND` (95-xxx to okolice, odrzucamy). **Kraków** w wersji „lite” (IX 2026): kody 30-xxx–31-xxx, ten sam model; zmierzony popyt tylko dla sektorów A3 i A13, bo tylko tam Visa ma numer parkomatu (`docs/research/krakow-spp.md`). Ranking P1–P4 liczony osobno dla każdego miasta. |
| Jednostka | Kod pocztowy (mikrostrefa). Polygony, ulice i centroidy z punktów adresowych PRG (GUGiK). Ulica służy tylko do wyświetlania. |
| Obszar | Obecna SPP + pas buforowy wokół niej. |
| Czas | Pn–pt 7:00–19:00, bloki **7–10 / 10–13 / 13–16 / 16–19**. Weekendy i święta bez opłat, jak dziś w Łodzi. Jeden profil pn–pt. |
| Sezony | **Lato** VI–IX 2025 · **Rok akademicki** X 2025 – VI 2026. |
| Prawo | Demo **pomija** limity art. 13b ustawy o drogach publicznych i mówi to wprost. |

## 3. Dane

### 3.1 Visa (środowisko `datasprint`, 305,5 mln transakcji, I 2025 – VI 2026)
Łódź to 6,47 mln transakcji, z czego 90,6 tys. z MCC 7523 (parkingi).

**Filtry do score (transakcje „wizyty”):**
- `transaction_type ∈ {POS, ATM}`, `cp_flag = 1`, bez `eci` / COF / wpisania ręcznego,
- odrzucamy `tran_id_gmt_tm = 000000`,
- odrzucamy agregatory dostaw po `mrch_nm_raw` (Glovo, Wolt, Uber Eats, Pyszne),
- odrzucamy MPK-LODZ (4111),
- odrzucamy duże formaty z własnym parkingiem (ręczna lista nazw: Auchan, Carrefour hiper, Lidl, Kaufland, Manufaktura, Port Łódź, galerie…),
- odrzucamy Boże Ciało 19.06.2025.

**MCC 7523 wydzielamy przed filtrami** (dla parkingów dopuszczamy także `cp_flag = 0`). MCC 4784 pomijamy (8 transakcji e-TOLL).

**Czas:** `tran_id_gmt_tm` to czas GMT, przeliczamy na Europe/Warsaw z uwzględnieniem DST.

**Kwoty:** `cs_tran_amt / 0,92` daje kwotę w PLN (93% kwot staje się pełnymi groszami).

### 3.2 Transakcje parkingowe (7523) w Łodzi
| Typ | Udział | Lokalizacja | Rola |
|---|---|---|---|
| `SPP Lodz <nr>` (617 parkomatów) | 43% | numer parkomatu → współrzędne (§3.3). Kod pocztowy to adres operatora (93-180, 93-020), **nie miejsce** | kalibracja, warstwa zmierzonego popytu, czas postoju, karty kierowców |
| Parkingi prywatne i instytucjonalne (UMED, ICZMP, PŁ, Port Lotniczy, OFF Piotrkowska, szpitale…) | ~30% | 1 kod na operatora | **tylko** wykrywanie kart kierowców, nie wchodzą do score |
| Aplikacje / ogólne (`FLOWBIRD APP`, `PAYBYPHONE`, `Parking`) | reszta | brak | **tylko** wykrywanie kart kierowców |

### 3.3 Dane miejskie
- **Parkomaty:** mapa JPG ZDiT z VI 2024 (Open Data Łódź, „Parkingi i parkomaty.zip”) zawiera ~440 numerów. Digitalizujemy ją do `data/parkomaty.csv`. ~177 parkomatów z rozszerzenia 2025 dostaje status „lokalizacja nieznana”. Równolegle składamy do ZDiT wniosek o pełną listę ze współrzędnymi (na pilotaż).
- **Cennik SPP** (uchwała XIII/329/25 + zmiany): trzy okresy, trzy podstrefy, stawki z ulgą i bez. Zapisany w `data/cennik_spp.csv`.

| Okres | Godziny | Uwagi |
|---|---|---|
| I–V 2025 | 8–18 | stary cennik (LX/1803/22), kwoty niepewne |
| 2.06.2025 – 30.09.2025 | 7–19 | nowa strefa, podstrefy A/B/C, jedna stawka |
| od 1.10.2025 | 7–19 | stawki z ulgą mieszkańca i bez niej, dochodzi Radiostacja (B) |

Naliczanie jest proporcjonalne, minimum to stawka za 30 min.

## 4. Model

### 4.1 Kierowcy i przyjezdni
- **Przyjezdny:** `pstl_cd_enr` ≠ kod sprzedawcy. Karty bez `pstl_cd_enr` liczymy jako przyjezdne.
- **Karta kierowcy:** karta z transakcją 7523 w Łodzi tego dnia. Takich kart jest 13 875, w tym 7 476 z SPP.
- **Współczynnik kierowców** `d[MCC_grupa, strefa]`: odsetek kart przyjezdnych, które są kartami kierowców. Liczony w SPP i stosowany także w buforze. W buforze to **dolne oszacowanie**, bo przy darmowym parkingu ludzie częściej przyjeżdżają autem.

### 4.2 Wizyta i czas wizyty
- **Wizyta:** transakcje jednej karty w tym samym kodzie tego samego dnia z przerwą ≤ 90 min.
- **Wizyta po opłacie parkingowej:** zakupy w oknie 0–180 min po opłacie, w promieniu ~500 m od parkomatu. Dopóki nie mamy współrzędnych, „ten sam lub sąsiedni kod”. Stacje paliw (5541/5542) nie liczą się jako cel wizyty. Start wizyty = moment opłaty.
- **Czas wizyty:** zmierzony czas (pierwsza → ostatnia transakcja, albo opłata → ostatnia) + czas domyślny grupy ostatniej transakcji. Wizyta z jedną transakcją dostaje sam czas domyślny.
- **Opłacony czas postoju** (SPP): kwota / 0,92 → cennik z daty transakcji → minuty. Podstrefę bierzemy z lokalizacji parkomatu, a nie z litery w ID. Karty z `lau_enr = LODZ` rozliczamy stawką z ulgą, pozostałe bez ulgi. Błąd przybliżenia (~15%) podajemy jawnie.

**Grupy usług i czasy domyślne** (do kalibracji na wizytach wielotransakcyjnych):

| Grupa | Przykładowe MCC | Czas domyślny |
|---|---|---|
| Szybkie usługi | piekarnie 5462, kioski, apteki 5912, kawiarnie, ATM | 15 min |
| Spożywcze małe | 5411 (poza dużymi formatami), 5499 | 20 min |
| Handel | retail, drogerie 5977 | 45 min |
| Gastronomia | 5812, 5814 | 75 min |
| Usługi osobiste | fryzjer, kosmetyka, medyczne | 90 min |
| Rozrywka / kultura | kino, teatr, muzea | 120 min |

Pełne mapowanie MCC → grupa jest w `data/mcc_groups.csv`.

### 4.3 Score
```
presja[strefa, blok, sezon] = mediana_po_tygodniach(
    Σ_grupa  unikalne_karty_przyjezdne[grupa] × d[grupa, strefa] × czas_wizyty[grupa]
)   # samochodo-godziny
```
- Minimum 30 unikalnych kart przyjezdnych na komórkę w okresie. Poniżej tego komórka dostaje **P1 z adnotacją „za mało danych”**.
- Bez wygładzania między blokami.
- Kwota transakcji nie wchodzi do score.
- Udział Visa w rynku ignorujemy, bo percentyle są odporne na jednolity mnożnik.
- **Kalibracja w SPP:** porównanie `presja` z opłaconymi auto-godzinami z parkomatów w tej samej strefie i bloku. Jeśli korelacja < 0,5, w SPP przełączamy się na score z parkomatów, a bufor pokazujemy jako ranking bez rekomendacji.

### 4.4 Poziomy
Percentyle presji w obrębie Łodzi, liczone osobno dla każdego sezonu:

| Poziom | Percentyl |
|---|---|
| P1 | 0–40 |
| P2 | 40–70 |
| P3 | 70–90 |
| P4 | 90–100 |

Po uzyskaniu danych o pojemności (pilotaż) przechodzimy na progi obłożenia 50 / 70 / 85%.

Typ usługi **nie wpływa** na poziom P. Wpływa tylko na okres preferencyjny.

## 5. Taryfy

P1–P4 **zastępują** podstrefy A/B/C. **S = 6,00 zł** (dzisiejsze B bez ulgi za 1. godzinę).

| | Okres preferencyjny | Cena w okresie pref. | Następnie | Po 2 h |
|---|---|---|---|---|
| P1 | 1 h | 3,60 zł/h (0,6·S) | 4,80 zł/h (0,8·S) | 4,80 zł/h |
| P2 | 1 h | 6,00 zł/h (S) | 7,20 zł/h (1,2·S) | 8,40 zł/h (1,4·S) |
| P3 | 45 min | 3,00 zł za cały okres (0,5·S) | 9,00 zł/h (1,5·S) | 12,00 zł/h (2·S) |
| P4 | 30 min | 1,80 zł za cały okres (0,3·S) | 12,00 zł/h (2·S) | 18,00 zł/h (3·S) |

- Okres preferencyjny trwa **najwyżej 1 h** (IX 2026: P1 skrócony z 2 h; tańszy początek postoju rekomendujemy tylko na pierwszą godzinę).
- Okres preferencyjny przesuwa się o ±15 min zależnie od dominującej grupy usług w strefie i bloku (krócej dla szybkich usług, dłużej dla usług osobistych i rozrywki), ale po wydłużeniu nie przekracza 1 h.
- Ulga mieszkańca: mnożnik ×0,85 na każdym poziomie.
- Stawka jest blokowana na starcie postoju.

**Komunikat dla kierowcy:**
> „Ta strefa ma teraz poziom P3 (do 13:00). Pierwsze 45 min kosztuje 3,00 zł, potem 9,00 zł/h, po 2 h 12,00 zł/h.”

## 6. Output

**Aplikacja** (Streamlit + pydeck), jedna aplikacja z trzema widokami:
1. **Mapa miasta:** kody pocztowe pokolorowane poziomami P, suwak bloku, przełącznik sezonu. Warstwy:
   - zmierzony popyt z parkomatów,
   - parkingi poza SPP (jeśli starczy czasu),
   - udział stałych bywalców.
2. **Karta kierowcy:** poziom, taryfa, do kiedy obowiązuje, koszt kolejnej godziny.
3. **Panel miasta:** tabela P (strefa × blok × sezon) jako gotowy załącznik do uchwały oraz 3–5 rekomendacji.

**Rekomendacja rozszerzenia SPP:** kod buforowy, którego presja ≥ mediana presji w obecnej SPP.

**Stali bywalcy:** ta sama karta, ≥ 3 dni robocze w tygodniu, ten sam parkomat, opłacony postój > 4 h. Pokazujemy **udział per strefa, tylko informacyjnie**. Bez rekomendacji i bez wpływu na taryfę.

**Slajdy dowodowe:**
- **Naturalny eksperyment:** I–V 2025 vs VI 2025+. Jak reforma SPP z 2025 zmieniła opłacony czas postoju i rotację. Na poziomie parkomatów, a jeśli ich nie zdigitalizujemy, na poziomie całej SPP.
- Kalibracja proxy względem parkomatów.

## 7. Privacy by Design

ParkFlow nie identyfikuje ani nie ujawnia posiadaczy kart.

Zahaszowane identyfikatory kart służą wyłącznie wewnątrz pipeline'u analitycznego, do wykrywania sekwencji transakcji tej samej karty potrzebnych do szacowania wzorców mobilności.

Sekwencje na poziomie karty nigdy nie opuszczają chronionej warstwy przetwarzania. Nie są wyświetlane, eksportowane ani udostępniane przez API.

Transaction data → Internal sequence analysis → Privacy aggregation → Dashboard

Na zewnątrz trafiają wyłącznie agregaty **kod pocztowy × blok × grupa MCC** z progiem **≥ 30 unikalnych kart** na grupę. W interfejsie ParkFlow nie ma żadnej trajektorii, historii transakcji ani identyfikatora karty, także w demo.

## 8. Poza zakresem demo

- limity ustawowe,
- pojemność SPP i obłożenie w % (Indigo podaje ~10 000 miejsc, liczba bez daty),
- klasteryzacja,
- walidacja na wstrzymanych tygodniach,
- osobny profil piątku,
- geokodowanie parkingów prywatnych (jeśli starczy czasu, trafia na mapę),
- pogoda,
- komunikacja miejska.

## 9. Ryzyka i otwarte kwestie

- Rekonstrukcja kwot przez 0,92 odwraca zaciemnienie danych wprowadzone przez organizatora. Świadomie ją stosujemy. Trzeba się przygotować na pytanie jury.
- Znaczenie kolumn `*_enr` (miejsce zamieszkania?) nie jest potwierdzone przez organizatorów.
- Stawki z I–V 2025 są niepewne, bo pochodzą z mediów.
- Mapa parkomatów pochodzi z 2024 r. i nie obejmuje rozszerzenia z 2025 r.

## 10. Zadania

| # | Zadanie | Kto | Wynik |
|---|---|---|---|
| 1 | Digitalizacja i georeferencja mapy parkomatów | Claude | `data/parkomaty.csv` + raport błędu |
| 2 | Polygony, ulice i centroidy kodów z PRG | Claude | `data/kody.geojson`, `data/kody_ulice.csv` |
| 3 | Cennik SPP (3 okresy) | Claude | `data/cennik_spp.csv` |
| 4 | Mapowanie MCC → grupa + czasy domyślne | Claude | `data/mcc_groups.csv` |
| 5 | Kod PySpark: filtry → wizyty → karty kierowców → agregaty z progiem 30 | Claude pisze, zespół uruchamia w `datasprint` | `pipeline/` → `agg_*.parquet` |
| 6 | Score, percentyle, taryfy, rekomendacje (na agregatach) | Claude | `parkflow/model.py` |
| 7 | Aplikacja Streamlit na danych przykładowych w docelowym schemacie | Claude | `app/` |
| 8 | Wniosek do ZDiT o listę parkomatów | Zespół | e-mail |
| 9 | Pytania do organizatorów: `*_enr`, waluta | Zespół | — |
