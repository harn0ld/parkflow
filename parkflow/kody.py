"""Geometrie, ulice i centroidy kodów pocztowych z punktów adresowych PRG (ticket 02).

Polygon kodu = suma komórek Voronoi jego punktów adresowych, przycięta do granicy miasta
i do bufora wokół punktów (lasy i lotnisko nie dostają ogromnych komórek). Teselacja nie ma
nakładek ani dziur (poza buforem). Kody w Łodzi są drobne i się przeplatają (strony ulicy,
zakresy numerów), więc część kodów wychodzi jako MultiPolygon — to cecha danych.

Centroid kodu = średnia punktów adresowych (geometryczny środek polygonu często leży poza nim).
Wszystkie odległości w układzie metrycznym wejścia (PRG: EPSG:2180).
"""

import geopandas as gpd
import pandas as pd
import shapely
from shapely.geometry.base import BaseGeometry

BUFOR_M = 150
UPROSZCZENIE_M = 5
SEPARATOR_ULIC = "; "


def skrocona_nazwa(pelna: str, rdzen) -> str:
    """Nazwa do tooltipa: rdzeń z PRG (`NAZWA_TER1`), „al. …” dla alei; bez rdzenia — pełna nazwa."""
    if rdzen is None or pd.isna(rdzen) or not str(rdzen).strip():
        return pelna
    return f"al. {rdzen}" if pelna.lower().startswith(("aleja ", "al. ")) else str(rdzen)


def ulice_kodow(punkty: pd.DataFrame, kolumna_ulicy: str = "ulica") -> pd.DataFrame:
    """Punkty (kod, <kolumna_ulicy>, x, y) → per kod: ulice, liczba_ulic, liczba_adresow, x, y.

    `ulice` = nazwy połączone „; ”, od ulicy z największą liczbą adresów (remis: alfabetycznie).
    x, y = średnia współrzędnych punktów kodu.
    """
    licz = punkty.groupby(["kod", kolumna_ulicy]).size().rename("n").reset_index()
    licz = licz.sort_values(["kod", "n", kolumna_ulicy], ascending=[True, False, True])
    ulice = licz.groupby("kod")[kolumna_ulicy].agg(lambda s: SEPARATOR_ULIC.join(s)).rename("ulice")
    g = punkty.groupby("kod")
    wynik = pd.concat([
        ulice,
        licz.groupby("kod").size().rename("liczba_ulic"),
        g.size().rename("liczba_adresow"),
        g["x"].mean(), g["y"].mean(),
    ], axis=1).reset_index()
    return wynik.sort_values("kod", ignore_index=True)


def _jeden_kod_na_punkt(punkty: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Punkty o identycznych współrzędnych → jeden punkt z najczęstszym kodem (remis: najmniejszy kod)."""
    xy = pd.DataFrame({"kod": punkty["kod"].values, "x": punkty.geometry.x.values, "y": punkty.geometry.y.values})
    n = xy.groupby(["x", "y", "kod"]).size().rename("n").reset_index()
    n = n.sort_values(["x", "y", "n", "kod"], ascending=[True, True, False, True]).drop_duplicates(["x", "y"])
    return gpd.GeoDataFrame({"kod": n["kod"].values}, geometry=gpd.points_from_xy(n["x"], n["y"]), crs=punkty.crs)


def polygony_kodow(punkty: gpd.GeoDataFrame, granica: BaseGeometry, bufor_m: float = BUFOR_M,
                   uproszczenie_m: float = UPROSZCZENIE_M) -> gpd.GeoDataFrame:
    """Punkty adresowe (kod, geometry; układ metryczny) → polygony kodów (kod, geometry) w tym samym układzie.

    Voronoi ∩ granica ∩ bufor punktów, suma po kodzie, uproszczenie z zachowaniem wspólnych krawędzi
    (`coverage_simplify`, sąsiednie kody dalej do siebie przylegają).
    """
    pkt = _jeden_kod_na_punkt(punkty)
    komorki = shapely.voronoi_polygons(shapely.MultiPoint(pkt.geometry.values), extend_to=granica, ordered=True)
    maska = shapely.intersection(granica, shapely.union_all(pkt.geometry.buffer(bufor_m).values))
    geom = shapely.get_parts(komorki)
    shapely.prepare(maska)
    brzeg = ~shapely.contains_properly(maska, geom)  # przycinamy tylko komórki na brzegu maski (szybciej)
    geom[brzeg] = shapely.intersection(geom[brzeg], maska)
    kody = gpd.GeoDataFrame({"kod": pkt["kod"].values}, geometry=geom, crs=punkty.crs).dissolve("kod").reset_index()
    kody = kody[~kody.geometry.is_empty]
    if uproszczenie_m:
        kody["geometry"] = shapely.coverage_simplify(kody.geometry.values, uproszczenie_m)
    return kody[["kod", "geometry"]].reset_index(drop=True)
