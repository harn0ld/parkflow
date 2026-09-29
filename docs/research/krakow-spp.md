# Kraków: strefa płatnego parkowania i dane Visa

Stan na 30.09.2026. Odpowiednik [lodz-spp.md](lodz-spp.md) dla drugiego miasta. Kraków liczymy w wersji „lite”: presja z kart przyjezdnych działa jak w Łodzi, ale parkomaty w Visa umiemy umiejscowić tylko w dwóch sektorach.

## Parkomaty: skąd lokalizacje

**[parkomaty.xml ZDMK](https://zdmk.krakow.pl/wp-content/themes/justidea_theme/assets/xml/parkomaty.xml)** zasila [mapę parkomatów ZDMK](https://zdmk.krakow.pl/parkowanie/strefa-platnego-parkowania/mapy/mapa-parkometrow/). Last-Modified: 14.10.2024. Kopia: `data/raw/krakow/parkomaty.xml`.

- 993 parkomaty, każdy z numerem (0001–3370, unikalne), sektorem (20: A1–A20, B5–B30, C7–C22), adresem, modelem i rodzajem płatności kartą, współrzędne WGS84.
- Podstrefa = litera sektora: A 488, C 357, B 148.
- Modele: Flowbird STRADA EVOLUTION II 469, Solari SPAZIO EVO 212, Solari SPAZIO 146, Solari SPAZIOEVO s2 88, Flowbird STRADA PAL 78.
- Karta: zbliżeniowa 808, brak 117, zbliżeniowa i stykowa 68.
- Kod pocztowy parkomatu = kod najbliższego punktu adresowego PRG (jak w Łodzi). 4 parkomaty są > 100 m od adresu (przejścia, place).

Zapasowe źródło: [MSIP, zbiór „ZDMK Parkomaty”](https://msip.krakow.pl/dataset/3165), ta sama warstwa w EPSG:2178. Strona nie podaje linku do pobrania ani licencji.

Budowa: `python scripts/zbuduj_parkomaty_krakow.py` → `data/krakow/parkomaty.csv`, `data/krakow/spp_kody.csv` (284 kody z ≥ 1 parkomatem).

## Parkomaty w danych Visa

Kraków = sklep w Polsce i kod 30-xxx–31-xxx albo brak kodu i miasto „KRAKOW”. 32-xxx to okolice (Wieliczka, Skawina). Pełny plik: **9,44 mln** transakcji z kodami 30–31 (Łódź 6,25 mln), **225 tys.** z MCC 7523.

| Nazwa w Visa | Transakcje | Kod | Lokalizacja |
|---|---|---|---|
| `ZDMK KRAKOW 1` | 34 011 | 31-586 (adres rozliczeniowy) | brak, jedna nazwa na wszystkie parkomaty |
| `PARKOMAT 3058` itd. | 9 193, 161 numerów | prawdziwe kody (31-061, 31-153, …) | **100% numerów jest w parkomaty.xml** |
| `ZDMK SCT`, `ZDMK BIURO STREFY…` | ~600 | 31-625 (biuro strefy) | brak |

- Numerowane parkomaty są tylko w sektorach **A3 (69)** i **A13 (92)**. Zmierzony popyt, opłacony czas postoju i stali bywalcy obejmują więc tylko te sektory.
- `ZDMK KRAKOW 1`: kanał `cp_contactless` 19,3 tys., `mobile` 14,7 tys. Liczy się do kart kierowców (każda opłata 7523 w mieście), ale nie wyznacza startu wizyty.
- **Pułapka:** nazwę `PARKOMAT NNNN` mają też Gdańsk (80-254), Tychy (43-100) i Sochaczew (96-500). Filtr miasta w ekstrakcji to wyklucza.
- **Pułapka:** pod krakowskimi kodami rozliczają się SPP innych miast: `KBU SP Z O O SPP WROCLAW` (~46 tys.), `SPP BIALYSTOK` (15 tys.), `UNICARD S.A.` (28 tys.). To nie jest postój w Krakowie, pipeline je pomija (`parkingi_obce` w `parkflow/miasta.py`).
- Inne duże parkingi: `Galeria Krakowska Parking` 25 tys., `GALERIA KAZIMIERZ PARKING` 4,8 tys., `PARKING WAWEL` 2,6 tys.

## Cennik

Stawki za kolejne godziny od **15.05.2023** ([uchwała CV/2851/23](https://zdmk.krakow.pl/wp-content/uploads/2023/05/uchwala_zmieniajaca-2851-2023.pdf), kopia w `data/raw/krakow/`), bez zmian do końca danych (VI 2026). Potwierdza je [grafika ZDMK od 30.04.2026](https://zdmk.krakow.pl/parkowanie/strefa-platnego-parkowania/informacje-ogolne-i-oplaty/) (`data/raw/krakow/stawki-oplat-od-2026-04-30.png`).

| Godzina | A | B | C |
|---|---|---|---|
| 1. | 9,00 | 8,00 | 7,00 |
| 2. | 10,00 | 9,00 | 8,00 |
| 3. | 11,00 | 10,00 | 9,00 |
| 4. i kolejne | 9,00 | 8,00 | 7,00 |

- Karta Krakowska: A 6/7/8/6, B 5/6/7/5, C 4 zł za każdą godzinę, **tylko w aplikacjach mobilnych** (pkt 2.1a.1 uchwały). Płatność kartą w parkomacie jest zawsze po stawce standardowej, więc pipeline nie stosuje ulgi (`lau_ulgi = None`). Od 30.04.2026 KK ma też bezpłatne niedziele w A.
- Brak minimalnej opłaty w uchwale; w `data/krakow/cennik_spp.csv` `stawka_30min = 0` (minuty liczone proporcjonalnie od pierwszej złotówki). Założenie do sprawdzenia na kwotach z parkomatów.
- Godziny: uchwała z 2023 r. mówi pn–sob 10–20. ZDMK podaje dziś A pn–nd, B i C pn–sob, 9–22; zmiana godzin (uchwały z XII 2025 i III 2026 to skany) nie wpływa na nasze bloki pn–pt 7–19, ale blok 7–10 ma w Krakowie mało opłat.
- Opłata dodatkowa: 400 zł (200 zł w ciągu 7 dni).

## Czego brakuje względem Łodzi

- Zmierzonego popytu dla całej strefy (tylko A3, A13).
- Naturalnego eksperymentu: w Krakowie nie było reformy w 2025 r. Okres „przed reformą” (I–V 2025) to dla Krakowa zwykły okres, bez porównania.
- Listy galerii z własnym parkingiem (`data/krakow/wykluczenia_kody.csv`) — zbudowana z kodów, pod którymi płaci się za parkingi galerii (sekcja wyżej).
