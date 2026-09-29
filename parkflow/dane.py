"""Wczytywanie agregatów pipeline'u i kontrakt ich schematu (docs/kontrakt-agregatow.md).

Domyślnie `data/agg/` (prawdziwe agregaty z pipeline'u), a gdy ich brak — `data/sample/`
(ręcznie zbudowane przykładowe agregaty w tym samym schemacie).
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
KATALOG_AGG = ROOT / "data" / "agg"
KATALOG_SAMPLE = ROOT / "data" / "sample"
# Geometrie i ulice kodów z PRG (ticket 02, scripts/zbuduj_kody.py).
KODY_GEOJSON = ROOT / "data" / "kody.geojson"
KODY_ULICE = ROOT / "data" / "kody_ulice.csv"
WYKLUCZENIA_KODY = ROOT / "data" / "wykluczenia_kody.csv"
# Parkomaty SPP z digitalizacji mapy ZDiT (ticket 06, scripts/digitalizuj_parkomaty.py).
PARKOMATY = ROOT / "data" / "parkomaty.csv"

# Kolumny w kolejności pipeline'u → rodzaj typu pandas. `spp` jest nullable: pusta, dopóki
# pipeline nie dostanie data/spp_kody.csv (ticket 02).
KONTRAKT: dict[str, dict[str, str]] = {
    "agg_strefy": {
        "kod": "string", "blok": "string", "sezon": "string",
        "karty_przyjezdne": "float", "presja": "float", "za_malo_danych": "bool", "spp": "bool?",
    },
    "agg_grupy": {
        "kod": "string", "blok": "string", "sezon": "string", "grupa": "string",
        "karty_przyjezdne": "int", "wspolczynnik_kierowcow": "float", "mediana_czasu_wizyty_min": "float",
        "presja": "float", "spp": "bool?",
    },
    "agg_kalibracja_czasow": {
        "grupa": "string", "czas_domyslny_min": "int", "wizyty_wielotransakcyjne": "int", "karty": "int",
        "udzial_wielotransakcyjnych": "float", "mediana_czasu_zmierzonego_min": "float",
    },
    "agg_parkomaty_strefy": {
        "kod": "string", "blok": "string", "sezon": "string", "oplacone_autogodziny": "float", "karty": "int",
    },
}

# Agregaty, których może brakować (np. data/agg policzone przed ticketem 05) — wtedy pole jest None.
OPCJONALNE = {"agg_kalibracja_czasow", "agg_parkomaty_strefy"}

_TYPY = {
    "string": pd.api.types.is_string_dtype,
    "float": pd.api.types.is_float_dtype,
    "int": pd.api.types.is_integer_dtype,
    "bool": pd.api.types.is_bool_dtype,
}


def sprawdz_kontrakt(df: pd.DataFrame, nazwa: str) -> None:
    """Rzuca ValueError, jeśli `df` nie ma kolumn i typów z KONTRAKT[nazwa]."""
    oczekiwane = KONTRAKT[nazwa]
    if list(df.columns) != list(oczekiwane):
        raise ValueError(f"{nazwa}: kolumny {list(df.columns)}, oczekiwano {list(oczekiwane)}")
    for kol, typ in oczekiwane.items():
        s = df[kol]
        if typ.endswith("?"):
            if s.isna().all():
                continue
            typ = typ[:-1]
            s = s.dropna()
            if typ == "bool" and s.map(lambda v: isinstance(v, bool)).all():
                continue
        if not _TYPY[typ](s):
            raise ValueError(f"{nazwa}.{kol}: typ {s.dtype}, oczekiwano {typ}")


@dataclass
class Agregaty:
    strefy: pd.DataFrame  # agg_strefy
    grupy: pd.DataFrame  # agg_grupy
    katalog: Path
    kalibracja: pd.DataFrame | None = None  # agg_kalibracja_czasow (opcjonalny)
    popyt: pd.DataFrame | None = None  # agg_parkomaty_strefy: zmierzony popyt (opcjonalny)

    @property
    def przykladowe(self) -> bool:
        return self.katalog.resolve() == KATALOG_SAMPLE.resolve()


def wczytaj_agregaty(katalog: Path | str | None = None, kandydaci: list[Path] | None = None) -> Agregaty:
    """Wczytuje agregaty z KONTRAKT z `katalog` albo z pierwszego istniejącego kandydata."""
    if katalog is None:
        kandydaci = kandydaci or [KATALOG_AGG, KATALOG_SAMPLE]
        katalog = next((k for k in kandydaci if (Path(k) / "agg_strefy.parquet").exists()), None)
        if katalog is None:
            raise FileNotFoundError(f"Brak agg_strefy.parquet w: {', '.join(map(str, kandydaci))}")
    katalog = Path(katalog)
    tabele = {}
    for nazwa in KONTRAKT:
        plik = katalog / f"{nazwa}.parquet"
        if nazwa in OPCJONALNE and not plik.exists():
            tabele[nazwa] = None
            continue
        df = pd.read_parquet(plik)
        sprawdz_kontrakt(df, nazwa)
        tabele[nazwa] = df
    return Agregaty(strefy=tabele["agg_strefy"], grupy=tabele["agg_grupy"], katalog=katalog,
                    kalibracja=tabele["agg_kalibracja_czasow"], popyt=tabele["agg_parkomaty_strefy"])


def wczytaj_kody_ulice(plik: Path | str = KODY_ULICE) -> pd.DataFrame:
    """data/kody_ulice.csv: kod, ulice, ulice_pelne, liczba_ulic, liczba_adresow, lat, lon."""
    return pd.read_csv(plik, dtype={"kod": str, "ulice": str, "ulice_pelne": str})


def wczytaj_parkomaty(plik: Path | str = PARKOMATY) -> pd.DataFrame:
    """data/parkomaty.csv: numer, podstrefa, podstrefa_2024, lat, lon, ulica, kod_pocztowy, status_lokalizacji, …"""
    return pd.read_csv(plik, dtype={"numer": str, "podstrefa": str, "podstrefa_2024": str, "ulica": str,
                                    "kod_pocztowy": str, "status_lokalizacji": str})


def kody_wylaczone(katalog: Path | str = KATALOG_AGG) -> dict[str, str]:
    """Kody wyłączone ze stref → opis, do neutralnego oznaczenia na mapie.

    Kody zbiorcze (`kody_zbiorcze.parquet` z katalogu agregatów; data/sample go nie ma)
    i galerie z własnym parkingiem (data/wykluczenia_kody.csv).
    """
    wynik: dict[str, str] = {}
    plik = Path(katalog) / "kody_zbiorcze.parquet"
    if plik.exists():
        z = pd.read_parquet(plik)
        wynik.update({kod: f"kod zbiorczy: adres rozliczeniowy {f'{n:,}'.replace(',', ' ')} sprzedawców, nie miejsce"
                      for kod, n in zip(z["kod"], z["sprzedawcy"])})
    if WYKLUCZENIA_KODY.exists():
        w = pd.read_csv(WYKLUCZENIA_KODY, dtype=str)
        wynik.update({kod: f"wyłączony ze stref: {nazwa} (duży format z własnym parkingiem)"
                      for kod, nazwa in zip(w["kod_pocztowy"], w["nazwa"])})
    return wynik
