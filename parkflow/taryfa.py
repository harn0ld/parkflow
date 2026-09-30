"""Taryfy P1–P4 i karta kierowcy (SPEC §5). Czyste funkcje, bez I/O.

Polityka cenowa to dane (`Polityka`, domyślnie `POLITYKA`): stawka bazowa S = 6,00 zł i tabela
mnożników S dla P1–P4. Taryfa poziomu ma trzy odcinki liczone od startu postoju:

1. okres preferencyjny (P1 i P2 1 h, P3 45 min, P4 30 min; po przesunięciu najwyżej 1 h):
   P1/P2 stawka godzinowa naliczana proporcjonalnie, P3/P4 ryczałt „za cały okres” (należny także
   przy krótszym postoju);
2. „następnie”: stawka godzinowa od końca okresu preferencyjnego do 2 h postoju;
3. „po 2 h”: stawka godzinowa od 2 h postoju.

Naliczanie po okresie preferencyjnym jest proporcjonalne do minut. Stawka jest blokowana na
starcie postoju: poziom z chwili startu obowiązuje przez cały postój.

Przesunięcie okresu preferencyjnego (±15 min) zależy od dominującej grupy usług w komórce
kod × sezon × blok (`agg_grupy`):

- dominująca grupa = grupa z największą `presja` (samochodo-godziny przyjezdnych, czyli udział
  w zapotrzebowaniu na miejsca, a nie liczba klientów); remis → więcej `karty_przyjezdne`,
  potem kolejność alfabetyczna nazwy grupy; brak wierszy (grupy < 30 kart) → brak przesunięcia;
- skraca o 15 min: `szybkie_uslugi` (czas domyślny wizyty 15 min);
- wydłuża o 15 min: `uslugi_osobiste` (90 min) i `rozrywka_kultura` (120 min), ale nie ponad
  `max_okres_pref_min` (1 h) — tańszy początek postoju rekomendujemy najwyżej na godzinę;
- bez zmian: `spozywcze_male`, `handel`, `gastronomia` (w dokumencie v0 „średni okres”).

Przesunięcie zmienia tylko długość okresu preferencyjnego; cena ryczałtu i stawki się nie zmieniają.
Ulga mieszkańca: mnożnik ×0,85 na wszystkich kwotach. Kwoty zaokrąglamy do grosza na końcu.
"""

from dataclasses import dataclass, field, replace
from datetime import datetime

import pandas as pd

from parkflow.model import BLOKI, ZA_MALO_DANYCH

GODZINY_SPP = (7, 19)  # pn–pt; święta pomijamy (demo)
BEZPLATNE = "Parkowanie bezpłatne (strefa płatna działa pn–pt 7–19)."


@dataclass(frozen=True)
class Mnozniki:
    """Jeden wiersz tabeli SPEC §5: długość okresu pref. i ceny jako wielokrotności S."""

    okres_pref_min: int
    cena_pref: float  # ×S za godzinę albo za cały okres (ryczalt)
    ryczalt: bool
    potem: float  # ×S/h do 2 h
    po_2h: float  # ×S/h od 2 h


@dataclass(frozen=True)
class Taryfa:
    """Taryfa w złotych dla jednego poziomu (po przesunięciu i ewentualnej uldze)."""

    poziom: str
    okres_pref_min: int
    cena_pref: float  # zł/h albo zł za cały okres (ryczalt)
    ryczalt: bool
    stawka_potem: float  # zł/h
    stawka_po_2h: float  # zł/h
    prog_min: int = 120  # „po 2 h”

    def koszt(self, minuty: float) -> float:
        """Koszt postoju trwającego `minuty` (bez zaokrąglenia)."""
        if minuty <= 0:
            return 0.0
        okres = self.okres_pref_min
        if self.ryczalt:
            koszt = self.cena_pref
        else:
            koszt = min(minuty, okres) / 60 * self.cena_pref
        potem = max(0.0, min(minuty, self.prog_min) - okres)
        po = max(0.0, minuty - max(okres, self.prog_min))
        return koszt + potem / 60 * self.stawka_potem + po / 60 * self.stawka_po_2h


@dataclass(frozen=True)
class Polityka:
    stawka_bazowa: float = 6.00
    mnozniki: dict[str, Mnozniki] = field(default_factory=lambda: {
        "P1": Mnozniki(60, 0.6, False, 0.8, 0.8),
        "P2": Mnozniki(60, 1.0, False, 1.2, 1.4),
        "P3": Mnozniki(45, 0.5, True, 1.5, 2.0),
        "P4": Mnozniki(30, 0.3, True, 2.0, 3.0),
    })
    ulga: float = 0.85
    prog_min: int = 120
    max_okres_pref_min: int = 60  # okres preferencyjny po przesunięciu nie dłuższy niż 1 h
    przesuniecia: dict[str, int] = field(default_factory=lambda: {
        "szybkie_uslugi": -15,
        "uslugi_osobiste": 15,
        "rozrywka_kultura": 15,
    })

    def taryfa(self, poziom: str, ulga: bool = False, przesuniecie_min: int = 0) -> Taryfa:
        m = self.mnozniki[poziom]
        s = self.stawka_bazowa * (self.ulga if ulga else 1.0)
        return Taryfa(
            poziom=poziom,
            okres_pref_min=min(m.okres_pref_min + przesuniecie_min, self.max_okres_pref_min),
            cena_pref=round(m.cena_pref * s, 2),
            ryczalt=m.ryczalt,
            stawka_potem=round(m.potem * s, 2),
            stawka_po_2h=round(m.po_2h * s, 2),
            prog_min=self.prog_min,
        )


POLITYKA = Polityka()


def koszt_postoju(poziom: str, minuty: float, ulga: bool = False, przesuniecie_min: int = 0,
                  polityka: Polityka = POLITYKA) -> float:
    """Koszt postoju [zł, do grosza] na poziomie z chwili startu, z ulgą mieszkańca lub bez."""
    return round(polityka.taryfa(poziom, ulga, przesuniecie_min).koszt(minuty), 2)


def przesuniecie_okresu(grupa: str | None, polityka: Polityka = POLITYKA) -> int:
    """Przesunięcie okresu preferencyjnego [min] dla dominującej grupy usług (0 bez grupy)."""
    return polityka.przesuniecia.get(grupa, 0) if grupa else 0


def dominujaca_grupa(agg_grupy: pd.DataFrame, kod: str, sezon: str, blok: str) -> str | None:
    """Grupa o największej presji w komórce kod × sezon × blok; remis → więcej kart, potem nazwa."""
    if agg_grupy.empty:
        return None
    g = agg_grupy[(agg_grupy["kod"] == kod) & (agg_grupy["sezon"] == sezon) & (agg_grupy["blok"] == blok)]
    g = g.dropna(subset=["presja"])
    if g.empty:
        return None
    g = g.sort_values(["presja", "karty_przyjezdne", "grupa"], ascending=[False, False, True])
    return str(g["grupa"].iloc[0])


KOLUMNY_STAWEK = ["dominujaca_grupa", "okres_pref_min", "ryczalt", "cena_pref_zl", "stawka_potem_zl",
                  "stawka_po_2h_zl", "godzina_1_zl", "godzina_2_zl", "godzina_3_zl",
                  "koszt_1h_zl", "koszt_2h_zl", "koszt_3h_zl"]


def tabela_stawek(sektory: pd.DataFrame, agg_grupy: pd.DataFrame, sezon: str, blok: str,
                  polityka: "Polityka" = POLITYKA) -> pd.DataFrame:
    """Kod + poziom (jeden sezon i blok) → taryfa modelu w złotych, bez ulgi, jak w „Wyliczeniach taryf”.

    Okres preferencyjny przesunięty wg dominującej grupy usług komórki. `cena_pref_zl` to zł/h albo
    zł za cały okres, gdy `ryczalt`; `stawka_potem_zl` jest pusta, gdy okres preferencyjny trwa do
    progu 2 h lub dłużej (odcinka „następnie” nie ma). `godzina_N_zl` to cena N-tej godziny postoju
    (różnica kosztów), `koszt_Nh_zl` — łączny koszt N godzin. Wiersze i indeks jak w `sektory`.
    """
    wiersze = []
    for kod, poziom in zip(sektory["kod"], sektory["poziom"]):
        grupa = dominujaca_grupa(agg_grupy, kod, sezon, blok)
        t = polityka.taryfa(poziom, przesuniecie_min=przesuniecie_okresu(grupa, polityka))
        wiersze.append({
            "dominujaca_grupa": grupa, "okres_pref_min": t.okres_pref_min, "ryczalt": t.ryczalt,
            "cena_pref_zl": t.cena_pref,
            "stawka_potem_zl": t.stawka_potem if t.okres_pref_min < t.prog_min else None,
            "stawka_po_2h_zl": t.stawka_po_2h,
            **{f"godzina_{h}_zl": round(t.koszt(60 * h) - t.koszt(60 * (h - 1)), 2) for h in (1, 2, 3)},
            **{f"koszt_{h}h_zl": round(t.koszt(60 * h), 2) for h in (1, 2, 3)},
        })
    return pd.DataFrame(wiersze, columns=KOLUMNY_STAWEK, index=sektory.index)


def blok_dla(chwila: datetime) -> str | None:
    """Blok dla chwili (czas lokalny); None poza pn–pt 7–19 (parkowanie bezpłatne)."""
    if chwila.weekday() >= 5 or not GODZINY_SPP[0] <= chwila.hour < GODZINY_SPP[1]:
        return None
    return BLOKI[(chwila.hour - GODZINY_SPP[0]) // 3]


def _koniec_bloku(blok: str) -> str:
    return f"{int(blok.split('-')[1]):02d}:00"


def _zl(kwota: float) -> str:
    return f"{kwota:.2f}".replace(".", ",") + " zł"


def _czas(minuty: int) -> str:
    if minuty <= 60:
        return f"{minuty} min"
    h, m = divmod(minuty, 60)
    if h and m:
        return f"{h} h {m} min"
    return f"{h} h" if h else f"{m} min"


def opis_taryfy(t: Taryfa) -> str:
    """„Pierwsze 45 min kosztuje 3,00 zł, potem 9,00 zł/h, po 2 h 12,00 zł/h.”"""
    cena = _zl(t.cena_pref) + ("" if t.ryczalt else "/h")
    tekst = f"Pierwsze {_czas(t.okres_pref_min)} kosztuje {cena}"
    if t.okres_pref_min < t.prog_min:
        tekst += f", potem {_zl(t.stawka_potem)}/h"
        if t.stawka_po_2h != t.stawka_potem:
            tekst += f", po {_czas(t.prog_min)} {_zl(t.stawka_po_2h)}/h"
    else:
        tekst += f", potem {_zl(t.stawka_po_2h)}/h"
    return tekst + "."


@dataclass(frozen=True)
class KartaKierowcy:
    kod: str
    sezon: str
    chwila: datetime
    blok: str | None = None  # None = poza godzinami SPP
    poziom: str | None = None
    adnotacja: str = ""
    do_godziny: str | None = None  # do kiedy obowiązuje bieżący poziom (koniec ciągu bloków)
    grupa: str | None = None  # dominująca grupa usług
    przesuniecie_min: int = 0
    taryfa: Taryfa | None = None
    taryfa_ulga: Taryfa | None = None

    @property
    def bezplatne(self) -> bool:
        return self.blok is None

    @property
    def komunikat(self) -> str:
        return self._komunikat(self.taryfa)

    @property
    def komunikat_ulga(self) -> str:
        return self._komunikat(self.taryfa_ulga)

    def _komunikat(self, t: Taryfa | None) -> str:
        if self.bezplatne:
            return BEZPLATNE
        return f"Ta strefa ma teraz poziom {self.poziom} (do {self.do_godziny}). {opis_taryfy(t)}"

    def koszty_godzin(self, n: int = 3, ulga: bool = False) -> list[float]:
        """Koszt każdej z kolejnych `n` godzin postoju rozpoczętego teraz [zł]."""
        if self.bezplatne:
            return [0.0] * n
        t = self.taryfa_ulga if ulga else self.taryfa
        return [round(t.koszt(60 * (i + 1)) - t.koszt(60 * i), 2) for i in range(n)]


def karta_kierowcy(tabela: pd.DataFrame, agg_grupy: pd.DataFrame, kod: str, sezon: str, chwila: datetime,
                   polityka: Polityka = POLITYKA) -> KartaKierowcy:
    """Karta kierowcy dla strefy `kod` w chwili `chwila` (tabela = `parkflow.model.tabela_p`).

    Poziom i adnotacja z tabeli P dla bloku chwili; „do godziny” = koniec ostatniego z kolejnych
    bloków o tym samym poziomie; taryfa z polityki z przesunięciem wg dominującej grupy usług.
    """
    blok = blok_dla(chwila)
    if blok is None:
        return KartaKierowcy(kod=kod, sezon=sezon, chwila=chwila)

    wiersze = tabela[(tabela["kod"] == kod) & (tabela["sezon"] == sezon)].set_index("blok")
    poziom = wiersze.at[blok, "poziom"]
    adnotacja = wiersze.at[blok, "adnotacja"]
    koniec = blok
    for nastepny in BLOKI[BLOKI.index(blok) + 1:]:
        if wiersze.at[nastepny, "poziom"] != poziom:
            break
        koniec = nastepny

    grupa = dominujaca_grupa(agg_grupy, kod, sezon, blok)
    przes = przesuniecie_okresu(grupa, polityka)
    return KartaKierowcy(
        kod=kod, sezon=sezon, chwila=chwila, blok=blok, poziom=poziom,
        adnotacja=adnotacja if adnotacja == ZA_MALO_DANYCH else "",
        do_godziny=_koniec_bloku(koniec), grupa=grupa, przesuniecie_min=przes,
        taryfa=polityka.taryfa(poziom, False, przes), taryfa_ulga=polityka.taryfa(poziom, True, przes),
    )
