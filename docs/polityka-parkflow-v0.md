# PARKFLOW – POLITYKA PARKINGOWA (v0)

> Oryginalny dokument koncepcyjny zespołu, zapisany bez zmian treści. Zastępuje go `SPEC.md`: tam, gdzie się różnią, obowiązuje SPEC. Najważniejsze różnice: harmonogram publikowany zamiast zmian w czasie rzeczywistym, jednostka = kod pocztowy, presja z samochodo-godzin przyjezdnych zamiast obłożenia w %, typ usługi wpływa tylko na okres preferencyjny, a nie na poziom P.

## 1. Główna zasada

ParkFlow nie ustala dowolnej ceny dla każdego miejsca parkingowego.

System działa na podstawie wcześniej zdefiniowanej i publicznie dostępnej polityki parkingowej miasta.

Najpierw analizujemy każde miejsce lub strefę parkingową, następnie przypisujemy jej określony poziom priorytetu, a dopiero poziom priorytetu określa taryfę.

Schemat:

```
DANE
↓
ANALIZA OBSZARU
↓
POZIOM OBŁOŻENIA + AKTYWNOŚĆ GOSPODARCZA + CHARAKTER OBSZARU
↓
PARKING PRIORITY
↓
PRZYPISANA POLITYKA PARKINGOWA
↓
TARYFA
```

## 2. Dlaczego potrzebujemy poziomów priorytetu?

Nie chcemy sytuacji, w której kierowca przyjeżdża w dane miejsce i nie rozumie, dlaczego parking kosztuje określoną kwotę.

Dlatego ParkFlow powinien posiadać kilka jasno zdefiniowanych poziomów.

Przykładowo:

- P1 – LOW PRIORITY
- P2 – STANDARD PRIORITY
- P3 – HIGH PRIORITY
- P4 – CRITICAL PRIORITY

Każdy poziom ma:

- jasno określone kryteria,
- konkretny przedział obłożenia,
- określoną politykę cenową,
- określony preferowany czas postoju,
- określoną progresję ceny.

Dzięki temu system jest przewidywalny i transparentny.

## 3. Occupancy Level – poziom obłożenia

Jednym z głównych parametrów jest poziom wykorzystania dostępnych miejsc parkingowych.

Przykładowa klasyfikacja:

- **LEVEL 1 – LOW OCCUPANCY (0–50%)**: duża liczba wolnych miejsc.
- **LEVEL 2 – MODERATE OCCUPANCY (50–70%)**: parking zaczyna być intensywniej wykorzystywany, ale znalezienie miejsca nadal nie powinno być dużym problemem.
- **LEVEL 3 – HIGH OCCUPANCY (70–85%)**: dostępność miejsc zaczyna być ograniczona.
- **LEVEL 4 – CRITICAL OCCUPANCY (85–100%)**: parking jest praktycznie pełny i potrzebne jest zwiększenie rotacji.

Dokładne wartości progowe powinny zostać później skalibrowane na podstawie danych.

## 4. Samo obłożenie nie wystarczy

ParkFlow nie powinien ustalać priorytetu wyłącznie na podstawie liczby zajętych miejsc.

Drugim kluczowym elementem jest COMMERCIAL ACTIVITY, czyli aktywność gospodarcza w otoczeniu parkingu.

Wykorzystujemy tutaj dane Visa:

- liczbę transakcji,
- MCC,
- strukturę działalności,
- godziny aktywności,
- dni tygodnia.

Przykład:

- **Parking A:** 90% occupancy, LOW commercial activity
- **Parking B:** 90% occupancy, VERY HIGH commercial activity, dominujące quick services / grocery

Parking B może wymagać większej rotacji, ponieważ jedno miejsce parkingowe może potencjalnie obsługiwać wielu klientów lokalnych biznesów.

## 5. Parking Priority Score

Dla każdego miejsca/strefy tworzymy PARKING PRIORITY SCORE.

Na jego wartość mogą wpływać:

- **OCCUPANCY**: jak bardzo parking jest zajęty?
- **COMMERCIAL ACTIVITY**: jak duża jest aktywność gospodarcza wokół?
- **BUSINESS TYPE / MCC**: czy dominują szybkie usługi czy aktywności wymagające dłuższego pobytu?
- **TIME OF DAY**: jaka jest aktualna charakterystyka obszaru?
- **DAY OF WEEK**: jak zmienia się zapotrzebowanie w poszczególnych dniach?
- **PARKING CAPACITY**: ile miejsc jest dostępnych?

## 6. Parking Priority Levels

Na podstawie Parking Priority Score przypisujemy poziom:

- P1 – LOW
- P2 – STANDARD
- P3 – HIGH
- P4 – CRITICAL

## 7. P1 – LOW PRIORITY

Charakterystyka:

- niskie obłożenie,
- niska presja parkingowa,
- niewielka potrzeba zwiększania rotacji.

Cel: nie ma potrzeby wypychania samochodów z parkingu.

Polityka:

- niska cena,
- długi okres podstawowej taryfy,
- niewielka progresja ceny.

## 8. P2 – STANDARD PRIORITY

Charakterystyka:

- umiarkowane obłożenie,
- normalna aktywność gospodarcza,
- dostępność miejsc nadal jest dobra.

Cel: utrzymanie równowagi między dostępnością a możliwością dłuższego parkowania.

Polityka:

- standardowa cena,
- umiarkowany czas preferencyjny,
- umiarkowana progresja.

## 9. P3 – HIGH PRIORITY

Charakterystyka:

- wysokie obłożenie,
- wysoka aktywność gospodarcza,
- ograniczona dostępność miejsc.

Cel: zwiększenie rotacji.

Polityka:

- bardzo tani krótki postój,
- następnie szybszy wzrost ceny,
- długotrwałe parkowanie staje się wyraźnie droższe.

Chcemy zachęcić kierowcę: „Przyjedź, załatw swoją sprawę i zwolnij miejsce kolejnej osobie.”

## 10. P4 – CRITICAL PRIORITY

Charakterystyka:

- bardzo wysokie obłożenie,
- bardzo duża aktywność,
- bardzo ograniczona dostępność miejsc,
- szczególnie duża potrzeba rotacji.

Cel: maksymalizacja dostępności miejsc dla krótkich wizyt.

Polityka:

- tani krótki postój,
- krótki okres preferencyjny,
- szybka progresja ceny,
- długotrwałe parkowanie jest zdecydowanie mniej opłacalne.

## 11. MCC wpływa na długość preferencyjnego postoju

Priority Level mówi nam, JAK BARDZO potrzebujemy rotacji.

MCC pomaga odpowiedzieć, JAK DŁUGO użytkownik realnie potrzebuje miejsca.

Przykład:

- QUICK SERVICES / BAKERY → krótki okres preferencyjny
- GROCERY / RETAIL → średni okres
- PERSONAL SERVICES → dłuższy okres
- RESTAURANTS / ENTERTAINMENT → odpowiednio dostosowany okres

Dzięki temu nie traktujemy jednakowo parkingu przy piekarni i parkingu przy restauracjach.

## 12. Macierz ParkFlow

Ostatecznie możemy stworzyć prostą macierz polityki:

- LOW OCCUPANCY + LOW ACTIVITY → P1
- MEDIUM OCCUPANCY + MEDIUM ACTIVITY → P2
- HIGH OCCUPANCY + HIGH ACTIVITY → P3
- CRITICAL OCCUPANCY + HIGH COMMERCIAL ACTIVITY → P4

Model nie ustala więc bezpośrednio ceny.

Model ustala PARKING PRIORITY, a polityka miasta określa PRIORITY → TARIFF.

## 13. Przykład działania

Parking X:

- Occupancy: 91%
- Commercial Activity: VERY HIGH
- Dominant MCC: Grocery + Quick Services
- Time: Tuesday, 12:00
- Parking Priority: P4 – CRITICAL
- Recommended preferred parking period: 30 min

Polityka miasta dla P4:

- 0–30 min → VERY LOW PRICE
- 30–60 min → STANDARD/HIGHER PRICE
- 60–120 min → HIGH PRICE
- 120+ min → VERY HIGH PRICE

## 14. Transparentność dla mieszkańca

To jest bardzo ważny element ParkFlow.

Użytkownik powinien wiedzieć:

- jaki poziom ma dana strefa,
- ile kosztuje parking,
- jak długo obowiązuje preferencyjna cena,
- ile będzie kosztowała kolejna godzina,
- w jakich godzinach obowiązuje dana polityka.

Nie chcemy: „AI zdecydowało, że teraz płacisz 13,47 zł.”

Chcemy: „Ta strefa ma obecnie poziom P3. W strefie P3 pierwsze 30 minut kosztuje X zł, następnie obowiązuje taryfa Y.”

Dzięki temu dynamiczny system pozostaje przewidywalny.

## 15. Dynamiczność bez chaosu

Dynamiczne nie muszą być same ceny.

Dynamiczny może być PRIORITY LEVEL.

Przykładowo, Parking X:

- 06:00–10:00 → P1
- 10:00–16:00 → P3
- 16:00–20:00 → P4
- 20:00–24:00 → P2

Każdy poziom ma wcześniej ustaloną taryfę.

Dzięki temu ParkFlow reaguje na zmieniające się funkcjonowanie miasta, ale kierowca nadal zna zasady.

## 16. Ostateczna architektura decyzji

```
VISA DATA
+
CITY PARKING DATA
↓
ZONE / PARKING PROFILE
↓
OCCUPANCY
COMMERCIAL ACTIVITY
MCC PROFILE
DAY & TIME
↓
PARKING PRIORITY SCORE
↓
P1 / P2 / P3 / P4
↓
CITY PARKING POLICY
↓
PREDEFINED TARIFF
↓
LOW-COST SHORT PARKING
PROGRESSIVE LONG-TERM PRICING
```

## 17. Najważniejsza zasada ParkFlow

**PARKFLOW DOES NOT RANDOMLY CHANGE PRICES.**

**PARKFLOW DYNAMICALLY ASSIGNS PARKING PRIORITIES.**

**EACH PRIORITY HAS A CLEAR AND PREDEFINED PRICING POLICY.**

Dzięki temu rozwiązanie jednocześnie pozostaje:

- DYNAMICZNE – reaguje na rzeczywiste wykorzystanie miasta,
- TRANSPARENTNE – kierowca zna zasady,
- PRZEWIDYWALNE – taryfy wynikają z określonych poziomów,
- DATA-DRIVEN – poziomy są wyznaczane na podstawie danych,
- ACTIONABLE – miasto otrzymuje konkretną rekomendację, którą może wdrożyć.
