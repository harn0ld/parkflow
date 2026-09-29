"""Pobieranie i wczytywanie PRG (GUGiK) dla miasta: punkty adresowe i granica powiatu grodzkiego.

PRG to dane otwarte (bez licencji, art. 40a ust. 2 pkt 1 Pgik). Podpis w aplikacji: „Źródło: PRG, GUGiK”.
Surowy zip (Łódź 5 MB, 135 MB po rozpakowaniu) trzymamy w `data/raw/prg/` (poza gitem).
Układ PRG: EPSG:2180 (metry). `.prj` ma nazwę ESRI, dlatego wymuszamy CRS po wczytaniu.
"""

import urllib.request
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import wkt
from shapely.geometry.base import BaseGeometry

from parkflow.dane import ROOT
from parkflow.kody import skrocona_nazwa
from parkflow.miasta import LODZ, Miasto

UKLAD = 2180
KATALOG_PRG = ROOT / "data" / "raw" / "prg"


def url_adresy(m: Miasto) -> str:
    return f"https://opendata.geoportal.gov.pl/prg/adresy/PunktyAdresowe/{m.wojewodztwo}/{m.teryt}.zip"


def url_granica(m: Miasto) -> str:
    return f"https://uldk.gugik.gov.pl/?request=GetCountyById&id={m.teryt}&result=geom_wkt,teryt,county&srid={UKLAD}"


def zip_adresy(m: Miasto = LODZ) -> str:
    return f"prg-adresy-{m.teryt}.zip"


def plik_granica(m: Miasto = LODZ) -> str:
    return f"granica-{m.teryt}-uldk.txt"


def ma_dane(katalog: Path, m: Miasto = LODZ) -> bool:
    return (katalog / plik_granica(m)).exists() and (
        (katalog / zip_adresy(m)).exists() or (katalog / f"PRG_PunktyAdresowe_{m.teryt}.shp").exists())


def pobierz(katalog: Path = KATALOG_PRG, nadpisz: bool = False, m: Miasto = LODZ) -> Path:
    """Pobiera zip PRG i granicę z ULDK do `katalog` (jeśli ich brak). Zwraca katalog."""
    katalog.mkdir(parents=True, exist_ok=True)
    for url, nazwa in ((url_adresy(m), zip_adresy(m)), (url_granica(m), plik_granica(m))):
        cel = katalog / nazwa
        if nadpisz or not cel.exists():
            print(f"pobieram {url}")
            urllib.request.urlretrieve(url, cel)
    return katalog


def _warstwa(katalog: Path, nazwa: str, m: Miasto, **kw) -> gpd.GeoDataFrame:
    """Warstwa z rozpakowanego katalogu albo prosto z zipa."""
    shp = katalog / f"{nazwa}.shp"
    zrodlo = shp if shp.exists() else f"zip://{katalog / zip_adresy(m)}!{nazwa}.shp"
    return gpd.read_file(zrodlo, **kw).set_crs(UKLAD, allow_override=True)


def wczytaj_punkty(katalog: Path = KATALOG_PRG, m: Miasto = LODZ) -> gpd.GeoDataFrame:
    """Punkty adresowe: kod, ulica (pełna nazwa), ulica_krotka, geometry (EPSG:2180)."""
    p = _warstwa(katalog, f"PRG_PunktyAdresowe_{m.teryt}", m, columns=["KOD_POCZT", "NAZWA_ULC", "ID_ULIC"])
    u = pd.DataFrame(_warstwa(katalog, f"PRG_Ulice_{m.teryt}", m, columns=["ID_ULIC", "NAZWA_TER1"])
                     .drop(columns="geometry"))
    p = p.merge(u, on="ID_ULIC", how="left")
    krotka = [skrocona_nazwa(n, t) for n, t in zip(p["NAZWA_ULC"], p["NAZWA_TER1"])]
    return gpd.GeoDataFrame(
        {"kod": p["KOD_POCZT"].astype(str), "ulica": p["NAZWA_ULC"].astype(str), "ulica_krotka": krotka},
        geometry=p.geometry, crs=UKLAD,
    )


def wczytaj_granice(katalog: Path = KATALOG_PRG, m: Miasto = LODZ) -> BaseGeometry:
    """Granica miasta (EPSG:2180) z odpowiedzi ULDK: linia 1 = status 0, linia 2 = `SRID=2180;WKT|teryt|nazwa`."""
    linie = (katalog / plik_granica(m)).read_text().splitlines()
    if linie[0].strip() != "0":
        raise ValueError(f"ULDK zwróciło błąd: {linie[0]}")
    return wkt.loads(linie[1].split(";", 1)[1].split("|")[0])
