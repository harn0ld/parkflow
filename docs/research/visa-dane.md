# Dane Visa: co wiemy z eksploracji

Eksplorację zrobił zespół w PySpark w środowisku `datasprint`. Liczby pochodzą z pełnego pliku, chyba że zaznaczono „próbka”.
Parquety z podzbiorem Łodzi (`lodz_all.parquet` 6,47 mln wierszy i `lodz_7523.parquet`) powstały w scratchpadzie innej sesji. **Trzeba je odtworzyć w `datasprint`**, bo nie są w repo. Poziom karty i tak nie może opuszczać `datasprint` (Privacy by Design).

## Skala i zakres
- Plik: **305,5 mln transakcji**, 17,5 GB, **I 2025 – VI 2026** (18 miesięcy).
- **Łódź:** sklep w Polsce + kod 90-xxx–94-xxx (po normalizacji) albo miasto „LODZ” daje **6,47 mln transakcji**.
  - Kody 95-xxx to okolice (Zgierz, Pabianice), więc je odrzucamy.
  - **Pułapka:** filtr `9[0-5]xxx` łapie włoski kod 90015 (Cefalù), co daje ~6,3 tys. fałszywych trafień. Zawsze trzeba dodać `mrch_ctry_nm = POLAND`.
- `mrch_postal_code` ma niejednolity format: `02427` bez myślnika, puste pola, zagraniczne `1016 GD`. Brak w ~3,5% (próbka).

## Kolumny: interpretacja
| Kolumna | Ustalenie |
|---|---|
| `tran_id_gmt_tm` | `HHMMSS` w **GMT**, co potwierdzają godziny parkomatów. `000000` (~5%) oznacza brak godziny, odrzucamy. Latem +2 h, zimą +1 h. |
| `cs_tran_amt` | **Przeskalowane przez 0,92.** Po `/0,92` 93% kwot to pełne grosze (bez dzielenia 42%, inne współczynniki ≤ 19%). Dotyczy całego zbioru. Najczęstsze kwoty w SPP po przeliczeniu: 4,50 / 9,00 / 3,50 / 3,00 / 7,50 zł. Świadomie odwracamy to zaciemnienie (ryzyko w `SPEC.md` §9). |
| `pymt_crd_acct_num_raw` | Hash karty. Służy do unikalnych kart i sekwencji wewnątrz pipeline'u. Nigdy nie wychodzi na zewnątrz. |
| `lau_enr` / `fua_enr` / `pstl_cd_enr` | Najprawdopodobniej szacowane miejsce zamieszkania posiadacza karty (**do potwierdzenia u organizatorów**). Tylko w ~30% pokrywa się z adresem sklepu. Karta ma średnio 1,11 różnych `pstl_cd_enr`, a sklep 1,81 (100 tys. wierszy). |
| `channel_flg` | Próbka: `cp_contactless`, `mobile`, `eci` (e-commerce), `cp_non_contactless`, `cash` (bankomat). |
| `transaction_pos_entry_mode` | `COF` (card-on-file) i ręczne wpisanie to zwykle płatność online lub subskrypcja. |
| `mrch_nm_raw` | Surowa nazwa, np. `ZABKA Z0449`, `MPK-LODZ AUTOMAT 2192` (MCC 4111), `Glovo…`. Służy do wykrywania sieci, dostaw i dużych formatów. |
| `issr_jurn` | `Domestic` / `Intra` (UE) / `Inter`. |
| `report_ctry` | Zawsze 616, bezużyteczna. |
| Waluta | Najpewniej PLN (**do potwierdzenia**). |

Najczęstsze MCC w próbce: 5411 Grocery, 5499 Misc Food, 5812 Restauracje, 5462 Piekarnie, 5814 Fast food, 5912 Apteki.

## Transakcje parkingowe (MCC 7523) w Łodzi
- **90 632** transakcji w Łodzi (2,84 mln w całym pliku, ~0,9% wszystkich). Miesięcznie 4,5–6,8 tys.
- MCC 4784 (opłaty drogowe) to tylko 8 transakcji `MINISTERSTWO FINANSO 01` (e-TOLL), więc go pomijamy.

**Top `mrch_nm_raw`** (razem ~45%):
`Parking` 6532 · `UMED SP. ZO.O` 6038 · `FLOWBIRD APP` 4884 · `POLITECHNIKA LODZKA 02` 4163 · `ICZMP PARKING SZP. GIN.` 4016 · `PARKING OFF PIOTRKOWSKA` 1985 · `PARKING UMED 04` 1707 · `POLITECHNIKA LODZKA 03` 1513 · `Port Lotniczy Lodz` 1362 · `WOJEWODZKI SPEC. SZPITA` 1310.
Inne nazwy: Manufaktura, Galeria Łódzka, ZOO, Monopolis, `PAYBYPHONE`.

**Parkomaty SPP** (`SPP Lodz <nr>`, np. `SPP Lodz 438B`):
- **38 789 transakcji (43%)** z **617 parkomatów**, najwyżej ~490 na jeden,
- 11,9 tys. unikalnych kart, co sugeruje stałych bywalców,
- godziny odpowiadają działaniu SPP (pn–pt), w weekend prawie zero (193 w soboty, 178 w niedziele).

**Kanał:** `cp_contactless` 51,3% · `mobile` 43,3% · `eci` 4,2% · `cp_non_contactless` 1,2%. `cp_flag = 1` to 94,1%.

**Kody pocztowe NIE wskazują miejsca parkowania:**
- tylko 56 kodów w mieście, top 1 = 35,1%, top 3 = 62,7%, top 10 = 85,3%,
- SPP: 94% transakcji w **93-180** (25 026) i **93-020** (11 329). To adresy operatora lub rozliczeń,
- parkingi prywatne mają 1 kod na operatora (UMED 90-151, ICZMP 93-338, FLOWBIRD APP 90-019), część ma `NULL`.

Lokalizacja SPP pochodzi więc z **numeru parkomatu** (patrz `lodz-spp.md`). Parkingi prywatne dałoby się geokodować po nazwie. `Parking` i aplikacje nie mają lokalizacji.

## Karty kierowców
| | Karty | Z inną transakcją w Łodzi tego dnia |
|---|---|---|
| Wszystkie parkingi (7523) | 23 345 | **13 875 (59,4%)** |
| Tylko SPP | 11 873 | 7 476 (63,0%) |
| Pary karta × dzień z parkowaniem | 85 543 | 43 158 (50,5%) |

Te „inne” transakcje to głównie: Grocery 15,8 tys. · Misc Food 13,9 tys. · Restauracje 7,6 tys. · Fast food 7,2 tys. · Stacje paliw 4,2 tys. · Drogerie i apteki ~3 tys. każda · Piekarnie 2,1 tys.

To powiązanie liczone jest tylko po dniu. Do celu wizyty potrzebne jest okno 0–180 min po opłacie i ~500 m od parkomatu (`SPEC.md` §4.2).

## Filtry wynikające z eksploracji
Pełna lista jest w `SPEC.md` §3.1. Wnioski z danych:
- MCC 7523 wydzielamy **przed** filtrem `eci`/COF/`cp_flag`, bo inaczej giną płatności z aplikacji,
- odrzucamy agregatory dostaw (Glovo…) i MPK-LODZ (4111),
- ATM zostaje jako fizyczna wizyta, mimo że pierwotna notatka zostawiała tylko POS.

## Kody zbiorcze sprzedawców (odkryte przy budowie pipeline'u)
Nie tylko parkomaty mają kod adresu rozliczeniowego zamiast lokalizacji. **7 kodów z > 400 różnymi nazwami sprzedawców obejmuje 44,5% transakcji Łodzi.** Prawdziwe miejsca mają ≤ ~200 nazw (Manufaktura 91-071: 199, Port Łódź 93-457: 185, Galeria Łódzka 90-307: 144).

| Kod | Nazw sprzedawców | Przykłady |
|---|---|---|
| 90-361 | 380 tys. | nazwa unikalna prawie dla każdej transakcji |
| 93-020 | 7,5 tys. | KOFEINA AUTOMATY, Glovo, Biedronki, IKEA, Kaufland, Lidle |
| 91-111 | 6,8 tys. | dziesiątki Lidli z całego miasta, Auchan, PayU*rossmann.pl |
| 93-180 | 3,0 tys. | parkomaty SPP (operator), McDonalds |
| 90-043, 91-117, 90-138 | 550–980 | — |

Pipeline wykrywa je automatycznie (`HUB_MIN_MERCHANTS = 400` w `pipeline/aggregate.py`), wyłącza ze stref i zapisuje listę w `data/agg/kody_zbiorcze.parquet`. Do wykrywania kart kierowców zostają.

Poza tym mimo `cp_flag = 1` w danych są: automaty vendingowe (~368 tys., `AUTOMAT`), sklepy internetowe (`.pl`, `www.`, `PayU*`, ~170 tys.) i MOP-y przy autostradach (~17 tys.). Wykluczamy je wzorcami w `data/wykluczenia.csv`.

Wartości kolumn filtrujących w Łodzi: `transaction_pos_entry_mode` = Tap to pay / Manual key entry (465 tys.) / COF (192 tys.) / Chip / Magstripe; `channel_flg` dodatkowo `recur`, `moto`, `other`; `transaction_type` = POS / ATM / NA (37 tys., odrzucamy).
