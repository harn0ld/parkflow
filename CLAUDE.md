# ParkFlow

Źródło prawdy o projekcie: `SPEC.md`.

## Agent skills

### Issue tracker

Issues i specyfikacje są w GitHub Issues repo harn0ld/parkflow (przez `gh`). See `docs/agents/issue-tracker.md`.

### Triage labels

Domyślne etykiety: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` w katalogu głównym. See `docs/agents/domain.md`.

## Wiedza projektowa

- `SPEC.md`: decyzje projektowe z uzasadnieniem (źródło prawdy).
- `docs/research/lodz-spp.md`: cennik SPP w 3 okresach, podstrefy, granice, parkomaty, punkty kontrolne, źródła.
- `docs/research/krakow-spp.md`: Kraków („lite”): parkomaty ZDMK z XML, cennik A/B/C, które opłaty w Visa mają numer parkomatu (tylko sektory A3, A13), SPP innych miast pod krakowskimi kodami.
- `docs/research/visa-dane.md`: interpretacja kolumn Visa, współczynnik 0,92, transakcje parkingowe, karty kierowców, pułapki filtrów.
- `docs/polityka-parkflow-v0.md`: oryginalny dokument koncepcyjny (historyczny, SPEC go zastępuje).
- `data/raw/zdit/`: mapa parkomatów JPG, XLSX z 9 współrzędnymi, mapa granic SPP, oryginalny ZIP z Open Data.
- `data/raw/uchwaly/`: uchwała XIII/329/25 (PDF + TXT), zmiany XX/559/25 i XXV/717/25, skan załącznika 1.
- Dane Visa na poziomie karty są wyłącznie w `datasprint`. Do repo trafiają tylko agregaty z progiem 30 kart.

## Praca nad demo

- Spec: `.scratch/parkflow-demo/spec.md` (lustro issue #1). Decyzje projektowe z uzasadnieniem: `SPEC.md`.
- Tickety: `.scratch/parkflow-demo/issues/NN-*.md` (01–12 = GitHub #2–#13). Kanoniczny stan (status, blokady) jest w GitHub Issues. Po zamknięciu issue zaktualizuj też plik md.
- Bierz ticket z frontu: wszystkie jego blokady zamknięte. Na start: 01.
