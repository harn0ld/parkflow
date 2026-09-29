"""Miasta obsługiwane przez ParkFlow: filtr transakcji Visa, parkomaty w danych i ścieżki danych.

Łódź zostaje w historycznych ścieżkach (`data/`, `data/agg/`); kolejne miasta mają własny katalog
`data/<id>/` z tymi samymi nazwami plików. Pliki wspólne (grupy MCC, wykluczenia nazw) są w `data/`.
"""

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DANE = ROOT / "data"


@dataclass(frozen=True)
class Miasto:
    id: str
    nazwa: str
    miejscownik: str  # „w Łodzi”, „w Krakowie”
    teryt: str  # powiat grodzki w PRG (GUGiK)
    prefiksy_kodow: tuple[str, ...]  # dwie pierwsze cyfry kodów pocztowych miasta
    nazwa_visa: str  # `mrch_city_nm_raw` bez polskich znaków, wielkie litery (transakcje bez kodu)
    parkomat_regex: str  # `mrch_nm_raw` wielkimi literami → numer parkomatu SPP w grupie 1
    srodek: tuple[float, float]  # lat, lon widoku mapy
    lau_ulgi: str | None = None  # `lau_enr` posiadacza karty ze stawką ulgową w cenniku SPP
    parkingi_obce: str | None = None  # regex nazw MCC 7523 rozliczanych w mieście, ale z innych miast
    zoom: float = 11.3
    katalog: Path = DANE  # dane referencyjne miasta (cennik, parkomaty, kody)

    @property
    def wojewodztwo(self) -> str:
        return self.teryt[:2]

    @property
    def katalog_agg(self) -> Path:
        return self.katalog / "agg"

    @property
    def kody_geojson(self) -> Path:
        return self.katalog / "kody.geojson"

    @property
    def kody_ulice(self) -> Path:
        return self.katalog / "kody_ulice.csv"

    @property
    def parkomaty(self) -> Path:
        return self.katalog / "parkomaty.csv"

    @property
    def parkomaty_zasieg(self) -> Path:
        return self.katalog / "parkomaty_zasieg.csv"

    @property
    def wykluczenia_kody(self) -> Path:
        return self.katalog / "wykluczenia_kody.csv"


LODZ = Miasto(
    id="lodz", nazwa="Łódź", miejscownik="Łodzi", teryt="1061", prefiksy_kodow=("90", "91", "92", "93", "94"),
    nazwa_visa="LODZ", parkomat_regex=r"^SPP LODZ\s+(\d+[A-Z]?)", srodek=(51.765, 19.46), lau_ulgi="LODZ",
)
# Kraków: w Visa numer ma tylko część parkomatów ZDMK („PARKOMAT 3058”, sektory A3 i A13); reszta opłat
# idzie jako „ZDMK KRAKOW 1” bez numeru. Ulga Karty Krakowskiej działa tylko w aplikacjach, więc
# płatność kartą w parkomacie jest zawsze po stawce standardowej. Pod krakowskimi kodami rozliczają się
# też SPP Wrocławia (KBU), Białegostoku i systemy Unicard — to nie są opłaty za postój w Krakowie.
KRAKOW = Miasto(
    id="krakow", nazwa="Kraków", miejscownik="Krakowie", teryt="1261", prefiksy_kodow=("30", "31"),
    nazwa_visa="KRAKOW", parkomat_regex=r"^PARKOMAT\s+0*(\d+)$", srodek=(50.0614, 19.9383),
    parkingi_obce=r"WROCLAW|BIALYSTOK|^KBU\b|UNICARD", zoom=11.0, katalog=DANE / "krakow",
)

MIASTA = {m.id: m for m in (LODZ, KRAKOW)}
