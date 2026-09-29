# Georeferencja mapy parkomatów ZDiT (VI 2024)

Wygenerowane przez `scripts/digitalizuj_parkomaty.py` — nie edytuj ręcznie.

## Metoda
- Transformacja afiniczna piksel → EPSG:2180 (najmniejsze kwadraty), potem WGS84.
- 27 punktów kontrolnych na mapie głównej: 18 skrzyżowań osi ulic PRG (GUGiK) i 9 parkomatów z Legionów (XLSX ZDiT). Piksele skrzyżowań odczytane wizualnie (środek jezdni, ±10 px ≈ ±5 m); piksele parkomatów = środki kropek.
- Skala: 0.512 m/px (oś x obrazu), 0.511 m/px (oś y) — mapa jest w skali, nie schematyczna.
- Wstawka „Rynek Bałucki” ma własną skalę: osobne podobieństwo na 3 skrzyżowaniach PRG. Legenda wykluczona.
- 9 parkomatów z Legionów dostaje współrzędne z XLSX, a nie z transformacji.

## Błąd (cel ≤ 50 m)

| punkty | reszta RMSE | reszta mediana | reszta maks. | LOO RMSE | LOO mediana | LOO maks. |
|---|---|---|---|---|---|---|
| wszystkie, mapa główna (27 pkt) | 15.8 m | 6.4 m | 42.3 m | 17.1 m | 7.8 m | 45.2 m |
| skrzyżowania PRG (18 pkt) | 6.0 m | 3.4 m | 12.6 m | 6.8 m | 3.7 m | 14.2 m |
| parkomaty Legionów (9 pkt) | 26.0 m | 24.1 m | 42.3 m | 28.0 m | 26.3 m | 45.2 m |
| wstawka Rynek Bałucki (3 pkt) | 1.0 m | 1.0 m | 1.2 m | 3.2 m | 2.8 m | 4.2 m |

Leave-one-out: transformacja dopasowana bez danego punktu, błąd = odległość przewidzianej pozycji od prawdziwej.

**Jak czytać:** skrzyżowania mierzą dokładność samej transformacji (mapa jest wierna geometrycznie, błąd kilka metrów). Parkomaty z Legionów mierzą to, co nas interesuje — położenie parkomatu — i mają błąd ~25–45 m, bo kropka jest rysowana obok jezdni z odsunięciem kartograficznym, a współrzędne ZDiT nie zawsze zgadzają się z układem kropek na mapie. Transformacja dopasowana tylko na skrzyżowaniach daje na Legionów praktycznie ten sam błąd, więc to błąd położenia kropek, a nie georeferencji. **Realny błąd parkomatu: ≤ 50 m (typowo 10–30 m).**

Konsekwencja dla kodów pocztowych: kody w Łodzi bywają jedną stroną ulicy, więc część parkomatów może trafić do kodu sąsiedniego (po drugiej stronie jezdni). Dla flagi SPP (kod z parkomatem) i bufora nie ma to znaczenia; dla porównań per parkomat × kod — trzeba o tym pamiętać.

## Punkty kontrolne

| punkt | układ | źródło | px x | px y | reszta [m] | LOO [m] |
|---|---|---|---|---|---|---|
| Kilińskiego × Północna | mapa | osie ulic PRG | 3415 | 552 | 9.3 | 11.5 |
| Nowomiejska × Północna | mapa | osie ulic PRG | 2445 | 705 | 12.6 | 14.2 |
| Gdańska × Legionów | mapa | osie ulic PRG | 1584 | 1322 | 4.5 | 4.9 |
| Żeligowskiego × Legionów | mapa | osie ulic PRG | 249 | 2032 | 3.0 | 3.4 |
| Kilińskiego × Narutowicza | mapa | osie ulic PRG | 3714 | 2367 | 9.1 | 10.4 |
| Kościuszki × Zielona | mapa | osie ulic PRG | 2385 | 2570 | 2.8 | 2.9 |
| Żeligowskiego × 6 Sierpnia | mapa | osie ulic PRG | 437 | 3292 | 4.0 | 4.5 |
| Targowa × Tuwima | mapa | osie ulic PRG | 4815 | 3312 | 4.0 | 5.0 |
| Kilińskiego × Tuwima | mapa | osie ulic PRG | 4080 | 3427 | 2.5 | 2.8 |
| Pogonowskiego × Struga | mapa | osie ulic PRG | 1092 | 3898 | 1.7 | 1.9 |
| Sienkiewicza × Nawrot | mapa | osie ulic PRG | 3614 | 4212 | 3.4 | 3.7 |
| Piotrkowska × Piłsudskiego | mapa | osie ulic PRG | 3130 | 4953 | 12.4 | 13.2 |
| Kilińskiego × Wigury | mapa | osie ulic PRG | 4690 | 5310 | 1.2 | 1.4 |
| Wólczańska × Żwirki | mapa | osie ulic PRG | 2643 | 5785 | 3.4 | 3.7 |
| Piotrkowska × Radwańska | mapa | osie ulic PRG | 3349 | 6381 | 1.4 | 1.6 |
| Piotrkowska × Czerwona | mapa | osie ulic PRG | 3577 | 7835 | 6.4 | 7.8 |
| Politechniki × Wróblewskiego | mapa | osie ulic PRG | 2207 | 8235 | 2.7 | 3.6 |
| Piotrkowska × Sieradzka | mapa | osie ulic PRG | 3742 | 8900 | 2.6 | 3.4 |
| parkomat 12A | mapa | XLSX ZDiT | 1908 | 1282 | 41.6 | 44.7 |
| parkomat 13B | mapa | XLSX ZDiT | 1365 | 1386 | 42.3 | 45.2 |
| parkomat 14B | mapa | XLSX ZDiT | 1198 | 1486 | 17.9 | 19.2 |
| parkomat 17B | mapa | XLSX ZDiT | 810 | 1718 | 27.0 | 29.2 |
| parkomat 18B | mapa | XLSX ZDiT | 833 | 1658 | 10.5 | 11.3 |
| parkomat 19B | mapa | XLSX ZDiT | 521 | 1844 | 26.1 | 28.6 |
| parkomat 20B | mapa | XLSX ZDiT | 594 | 1846 | 24.1 | 26.3 |
| parkomat 21B | mapa | XLSX ZDiT | 407 | 1957 | 7.7 | 8.5 |
| parkomat 22B | mapa | XLSX ZDiT | 388 | 1924 | 9.0 | 10.0 |
| Łagiewnicka × Org. WiN | wstawka | osie ulic PRG | 660 | 285 | 1.0 | 2.8 |
| Łagiewnicka × Zawiszy Czarnego | wstawka | osie ulic PRG | 660 | 465 | 1.2 | 2.4 |
| Zgierska × Bałucki Rynek (płd.) | wstawka | osie ulic PRG | 395 | 462 | 0.7 | 4.2 |

## Digitalizacja numerów

- Kropek na mapie: 428 (w tym wstawka: 2).
- Numer z OCR: 212, z ręcznego odczytu (`data/raw/zdit/parkomaty_odczyty_reczne.csv`): 216.
- Kropki bez numeru: 0.
- Numery 1–440 nieobecne na mapie: 2, 3, 15, 148, 152, 153, 154, 171, 211, 266, 268, 269.
- Duplikaty: brak.
- ID z danych Visa bez lokalizacji: 190 (status „lokalizacja nieznana”; źródło listy: `data/parkomaty_visa_id.csv`). Pipeline łączy po dokładnym ID, więc ID bez litery (nowe parkomaty > 440, ale też np. `312` obok `312B` z mapy) nie dziedziczy lokalizacji — nie wiemy, czy to to samo urządzenie.
- Wszystkie kropki sprawdzone odczytem wizualnym kafli. Ręczny CSV zawiera tylko te, dla których OCR nie dał numeru (`brak_ocr`), dał numer sprzeczny lub błędny (`korekta_ocr`) albo segmentacja zgubiła kropkę przykrytą linią (`kropka_niewykryta`, piksel podany ręcznie).
- Litera w numerze to podstrefa z mapy 2024 (kolor kropki). `podstrefa` w `data/parkomaty.csv` to podstrefa obecna: A → A, B → B, dawne C (Fabryczna) → B, D (Bałucki Rynek) → C.

## Kody SPP (`data/spp_kody.csv`)

Reguła: kod pocztowy jest kodem SPP, gdy ma co najmniej jeden zlokalizowany parkomat z mapy 2024 (kod najbliższego punktu adresowego PRG). Wynik: 207 kodów. Pozostałe kody z danych to bufor. Ograniczenia: mapa nie obejmuje rozszerzenia SPP z 2025 r. (kody z nowych parkomatów wypadają do bufora), a kody „po drugiej stronie ulicy” bez własnego parkomatu też.
