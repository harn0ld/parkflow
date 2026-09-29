# Łódź SPP: fakty z researchu

Stan na 29.09.2026. Fakty oznaczone **(niepewne)** trzeba zweryfikować przed użyciem w pitchu.
Pliki źródłowe leżą w `data/raw/zdit/` i `data/raw/uchwaly/`.

## Podstawa prawna

- **Uchwała RM nr XIII/329/25 z 15.01.2025** (Dz. Urz. Woj. Łódzkiego poz. 2144) ustala SPP, opłaty i sposób ich pobierania. Zastąpiła LX/1803/22.
  - Tekst: https://dziennik.lodzkie.eu/WDU_E/2025/2144/oryginal/akt.pdf
  - Lokalnie: `data/raw/uchwaly/XIII-329-25-uchwala-spp.pdf` oraz wersja `.txt` do przeszukiwania.
- **Zmiany:** XX/559/25 z 3.09.2025 (poz. 9093) i XXV/717/25 z 17.12.2025 (poz. 11994). Dotyczą abonamentów, zwolnień i listy ulic, **nie zmieniają stawek**.
  - Lokalnie: `data/raw/uchwaly/XX-559-25-zmiana.pdf`, `data/raw/uchwaly/XXV-717-25-zmiana.pdf`
- **Załącznik 1** (lista ulic SPP, ponad 114 pozycji) to skan bez warstwy tekstowej: `data/raw/uchwaly/zal-1-lista-ulic-skan.pdf`
- Zbiór podstaw prawnych: https://uml.lodz.pl/komunikacja-i-transport/kierowca/parkowanie-platne/podstawy-prawne/

## Cennik w czasie

Ten sam cennik obowiązuje w trzech okresach zbiegających się z danymi Visa (I 2025 – VI 2026).

### Okres 1: I – V 2025 (stary cennik, LX/1803/22) **(niepewne)**
Kwoty pochodzą z mediów. Nie jest pewne, czy poprawki z 2024 r. ich nie zmieniły.

| Podstrefa | 30 min | 1. h | 2. h | 3. h | 4.+ h |
|---|---|---|---|---|---|
| A i dawne C | 2,50 | 5,00 | 5,50 | 6,00 | 5,00 |
| B | 2,00 | 4,00 | 4,50 | 5,00 | 4,00 |

Godziny: pn–pt 8:00–18:00.

W `data/cennik_spp.csv` okres I ma `podzial = 2024`: wiersze dotyczą podstref z mapy 2024 (litera w ID parkomatu,
kolumna `podstrefa_2024` w `data/parkomaty.csv`), bo przed reformą obowiązywał stary podział. A i dawne C
(dworzec Fabryczna, dziś B) — stawki A; B — stawki B; D (Bałucki Rynek, dziś C) — przyjęte stawki B **(niepewne)**.
Źródła: https://lodz.pl/artykul/parkingi-w-lodzi-wszystko-o-strefach-parkowania-nowych-parkomatach-i-oplatach-mapa-53565/ · https://uml.lodz.pl/en/komunikacja-i-transport/kierowca/paid-parking/

### Okres 2: 2.06.2025 – 30.09.2025
- Nowa uchwała weszła w życie w głównej części: większa strefa, godziny **pn–pt 7:00–19:00**, nowe podstrefy A/B/C.
- Według § 11 wszyscy płacą stawki, które dziś są stawkami „z ulgą” (tabela niżej, kolumny „z ulgą”).
- Data 1 czy 2.06 jest **(niepewna)**, bo 1.06.2025 wypadał w niedzielę. Dla przeliczeń to bez znaczenia: niedziela jest
  bezpłatna, a pipeline liczy tylko dni robocze. `data/cennik_spp.csv` przypisuje 1.06 do okresu I, 2.06 do II.
- § 11 uchwały: zał. 4 wchodzi w życie „nie wcześniej niż 1 maja 2025”, z wyjątkiem § 1 ust. 3 (stawki bez ulgi)
  — „nie wcześniej niż 1 października 2025”. Stąd okres II = stawki z § 1 ust. 2 dla wszystkich.

Źródła: https://www.rynek-kolejowy.pl/wiadomosci/lodz-od-2-czerwca-wieksza-strefa-platnego-parkowania-i-nowe-oplaty-143718.html · https://transinfo.pl/infotrans/lodz-ze-zmianami-w-strefie-platnego-parkowania-maja-zachecic-do-transportu-publicznego/

### Okres 3: od 1.10.2025 (obowiązuje do końca danych, VI 2026)
Od tej daty są osobne stawki z ulgą mieszkańca (§ 14 regulaminu) i bez niej. Do strefy doszła Radiostacja jako podstrefa B.

| | A z ulgą | A bez ulgi | B z ulgą | B bez ulgi | C z ulgą / bez ulgi |
|---|---|---|---|---|---|
| do 30 min | 3,00 | 3,50 | 2,50 | 3,00 | 0 zł raz dziennie, potem 2,50 / 3,00 |
| 1. godzina | 6,00 | 6,90 | 5,00 | 6,00 | 5,00 / 6,00 |
| 2. godzina | 7,20 | 8,20 | 6,00 | 7,20 | 6,00 / 7,20 |
| 3. godzina | 8,60 | 9,80 | 7,20 | 8,60 | 7,20 / 8,60 |
| 4. i kolejne | 6,00 | 6,90 | 5,00 | 6,00 | 5,00 / 6,00 |

Źródło: załącznik 4 do uchwały oraz https://uml.lodz.pl/komunikacja-i-transport/kierowca/parkowanie-platne/wnoszenie-oplat-za-poszczegolne-godziny-postoju-platnosci-mobilne/

### Zasady wspólne
- Stawki za kolejne godziny się sumują. Przykład: A bez ulgi, 3 h = 6,90 + 8,20 + 9,80 = 24,90 zł.
- **Naliczanie jest proporcjonalne do czasu postoju.** Minimalna opłata za każde parkowanie to stawka za 30 min (zał. 4, § 1 ust. 4).
- Opłatę wnosi się w ciągu 5 min od zaparkowania. Opłata dodatkowa: 300 zł.
- Weekendy i święta są bezpłatne.
- Progresja (+20% za 2. i 3. godzinę, 4. godzina = 1. godzina) to dokładnie limit ustawowy z art. 13b ustawy o drogach publicznych.
- W podstrefie C pierwsze 30 min kosztuje 0 zł raz dziennie. To gotowy precedens dla taniego krótkiego postoju w ParkFlow.

### Jak używać przy przeliczaniu kwot na minuty (ticket 07)
1. `cs_tran_amt / 0,92` daje kwotę w PLN (patrz `visa-dane.md`).
2. Okres wybieramy według daty transakcji.
3. Podstrefę bierzemy z lokalizacji parkomatu, a nie z litery w ID (patrz niżej).
4. Stawkę z ulgą stosujemy dla kart z `lau_enr = LODZ`, pozostałe bez ulgi.
5. Minuty liczymy odwracając proporcjonalne naliczanie. Błąd ~15% przy złym przypisaniu ulgi podajemy jawnie.
6. Podstrefa C: bilet 0 zł (30 min raz dziennie, od reformy) nie przechodzi przez kartę, więc pierwszy krótki postój
   dnia w C jest w Visa niewidoczny. `stawka_30min` dla C w cenniku to stawka za kolejny taki postój (2,50 / 3,00).

## Podstrefy i granice

- **A** (ścisłe centrum), **B** (reszta Śródmieścia), **C** (Bałucki Rynek i Łagiewnicka). Osobnej „Śródmiejskiej SPP” nie ma.
- **Granice podstrefy A** (zał. 4 do XIII/329/25, ulice graniczne należą do A):
  - od zachodu: Żeromskiego, Gdańska,
  - od północy: Legionów, Ogrodowa, Północna, Rewolucji 1905 r., Narutowicza,
  - od wschodu: Kilińskiego, Sterlinga, pl. Dąbrowskiego (jezdnia wschodnia), al. Rodziny Scheiblerów, Sienkiewicza,
  - od południa: Brzeźna, Radwańska, al. Piłsudskiego, al. Rodziny Poznańskich.
- **B**: pozostałe ulice strefy (zał. 1).
- **Rozszerzenie z 2025 r.** (według prasy):
  - na północ od trasy W-Z, od al. Włókniarzy do ul. Kopcińskiego,
  - okolice ul. Tymienieckiego i ul. Tylnej,
  - al. Unii Lubelskiej i ul. Krakowska,
  - od X 2025 Radiostacja (obszar Kopcińskiego – Małachowskiego – Konstytucyjna – Narutowicza).
- Mapa strefy: https://uml.lodz.pl/komunikacja-i-transport/kierowca/parkowanie-platne/mapa-strefy/ (blokuje automatyczne pobieranie).

## Parkomaty

- **Źródło:** Open Data Łódź, zbiór „Parkingi i parkomaty” (ZDiT, aktualizacja 20.12.2024, poziom otwartości 2/5).
  - Strona: https://otwarte.miasto.lodz.pl/dane-przestrzenne/
  - Plik: https://otwarte.miasto.lodz.pl/wp-content/uploads/2025/01/parkingi-i-parkomaty.zip
  - Oryginał lokalnie: `data/raw/zdit/parkingi-i-parkomaty-oryginal.zip`
- **Mapa parkomatów** `data/raw/zdit/mapa-parkomatow-2024-06.jpg`:
  - raster 6623×9363 px z czerwca 2024, **bez georeferencji**,
  - ~440 numerów od 1A do 440D, kolor kropki oznacza podstrefę (fiolet = A, zielony = B),
  - mapa jest czysta i prawie wektorowa, więc segmentacja kolorów + OCR (tesseract) działa; sprawdzone na wycinku,
  - przykłady: 438B (Piotrkowska przy pl. Niepodległości), 267A (okolice Tuwima / Sienkiewicza).
- **Mapa granic SPP:** `data/raw/zdit/mapa-spp-zal1.jpg` (+ `.cdr`).
- **Współrzędne tylko 9 parkomatów** (ul. Legionów) w `data/raw/zdit/wspolrzedne-parkomatow-legionow.xlsx`. To punkty kontrolne do georeferencji:

| Numer | Odcinek | Posesja | Strona | Lat | Lon |
|---|---|---|---|---|---|
| 21B | Żeligowskiego – Pogonowskiego | 82 | Płd. | 51.77336 | 19.43866 |
| 20B | Żeligowskiego – Pogonowskiego | 70 | Płd. | 51.77399 | 19.44042 |
| 22B | Pogonowskiego – Żeligowskiego | 81 | Płn. | 51.77342 | 19.43862 |
| 17B | Pogonowskiego – Żeromskiego | 66 | Płd. | 51.77435 | 19.44141 |
| 18B | Cmentarna – Św. Jerzego | 61 | Płn. | 51.77466 | 19.44212 |
| 19B | Cmentarna – Św. Jerzego | 75 | Płn. | 51.77391 | 19.44000 |
| 13B | Żeromskiego – Gdańska | 44 | Płd. | 51.77558 | 19.44557 |
| 14B | Żeromskiego – Gdańska | 48 | Płd. | 51.77556 | 19.44486 |
| 12A | Gdańska – Zachodnia | 24 | Płd. | 51.77630 | 19.44939 |

- **Litery w ID nie są wiarygodną podstrefą.** Na mapie z 2024 r. oznaczają podstrefę z tamtego czasu: A, B, C (dworzec Fabryczna), D (Bałucki Rynek). Od VI 2025 dawne C weszło do B, a Bałucki Rynek jest teraz C **(niepewne)**. Podstrefę bierzemy z lokalizacji.
- **Brakujące parkomaty:** operator Indigo podaje 617 urządzeń, a w danych Visa jest 617 różnych ID. Na mapie jest ~440, więc parkomaty z rozszerzenia 2025 dostają status „lokalizacja nieznana”. Źródło: https://www.park-indigo.pl/reference/miejska-strefa-platnego-parkowania/
- **Pełna lista ze współrzędnymi** nie jest dostępna jako open data. Nie ma jej na dane.gov.pl, a geoportal https://nowa.mapa.lodz.pl/ nie został sprawdzony. XLSX z Legionów dowodzi, że ZDiT takie dane ma, więc na pilotaż składamy wniosek o udostępnienie.

## Podaż miejsc
- „Prawie 10 000 miejsc postojowych” według Indigo. Liczba jest **bez daty** i nie wiadomo, czy obejmuje rozszerzenie z 2025 r. Oficjalnej liczby UMŁ nie znaleziono.
- W demo nie liczymy obłożenia w %. Ta liczba służy tylko do kontekstu w pitchu.
