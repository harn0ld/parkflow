"""Zasięg parkomatu (ticket 08): kody pocztowe, w których zakup może być celem wizyty po opłacie.

SPEC §4.2: cel wizyty to zakup 0–180 min po opłacie „~500 m od parkomatu”. Sklepy znamy tylko
z kodu pocztowego, więc promień przybliżamy na poziomie kodów:

- parkomat z lokalizacją → kody, których polygon (teselacja Voronoi punktów adresowych PRG,
  `data/kody.geojson`) leży w odległości ≤ 500 m od parkomatu. Polygon, a nie centroid: sklep może
  stać w dowolnym miejscu kodu, a centroid dużego kodu bywa daleko od jego krawędzi przy parkomacie.
  Kod, w którym stoi parkomat, zawsze ma odległość 0. W centrum to zwykle kilkanaście–kilkadziesiąt
  kodów, więc kolumna `odl_m` zostaje w tabeli, gdyby trzeba było zawęzić promień bez przeliczania geometrii.
- parkomat bez lokalizacji, ale z kodem → awaryjnie „ten sam lub sąsiedni kod” (polygony stykają się,
  tolerancja `SASIEDZTWO_M` na uproszczenie krawędzi).
- parkomat bez lokalizacji i bez kodu → brak zasięgu (jego opłata nie wyznacza startu wizyty,
  ale karta nadal jest kartą kierowcy).

Tabelę buduje `scripts/zbuduj_zasieg_parkomatow.py` → `data/parkomaty_zasieg.csv`
(numer, kod_pocztowy, odl_m, zrodlo). Pipeline (`pipeline/aggregate.py`) łączy opłatę z wizytą, gdy
kod wizyty jest w zasięgu parkomatu; bez tabeli wraca do „tego samego kodu”.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import shapely

from pipeline.parkomaty import do_2180

PROMIEN_M = 500
SASIEDZTWO_M = 1.0
UKLAD = 2180

ZRODLO_PROMIEN = "promien_500m"
ZRODLO_SASIEDZI = "ten_sam_lub_sasiedni_kod"

KOLUMNY = ["numer", "kod_pocztowy", "odl_m", "zrodlo"]


def zasieg_parkomatow(parkomaty: pd.DataFrame, kody: gpd.GeoDataFrame, promien_m: float = PROMIEN_M,
                      sasiedztwo_m: float = SASIEDZTWO_M) -> pd.DataFrame:
    """Parkomaty (numer, lat, lon, kod_pocztowy) + polygony kodów (kod, geometry) → tabela zasięgu.

    Zwraca kolumny `KOLUMNY`, posortowane po numerze i odległości.
    """
    kody = kody.to_crs(UKLAD)[["kod", "geometry"]].reset_index(drop=True)
    p = parkomaty.copy()
    p["numer"] = p["numer"].astype(str).str.upper()
    ma_xy = p["lat"].notna() & p["lon"].notna()

    czesci = []
    zxy = p[ma_xy]
    if len(zxy):
        x, y = do_2180(zxy["lat"], zxy["lon"])
        pkt = gpd.GeoDataFrame({"numer": zxy["numer"].values}, geometry=gpd.points_from_xy(x, y), crs=UKLAD)
        kand = gpd.sjoin(pkt.assign(geometry=pkt.buffer(promien_m)), kody, predicate="intersects")
        # Bufor to wielokąt, więc dokładna odległość punkt → polygon jeszcze raz.
        kand["odl_m"] = shapely.distance(pkt.geometry.values[kand.index], kody.geometry.values[kand["index_right"]])
        wynik = kand[["numer", "kod", "odl_m"]]
        czesci.append(wynik[wynik["odl_m"] <= promien_m].assign(zrodlo=ZRODLO_PROMIEN))

    bez = p[~ma_xy & p["kod_pocztowy"].notna()]
    if len(bez):
        wlasne = kody.merge(bez[["numer", "kod_pocztowy"]], left_on="kod", right_on="kod_pocztowy")
        sasiedzi = gpd.sjoin(
            gpd.GeoDataFrame(wlasne[["numer"]], geometry=wlasne.geometry.buffer(sasiedztwo_m), crs=UKLAD),
            kody, predicate="intersects",
        )
        rodzina = pd.concat([
            bez[["numer", "kod_pocztowy"]].rename(columns={"kod_pocztowy": "kod"}),  # także kod bez polygonu
            sasiedzi[["numer", "kod"]],
        ])
        czesci.append(rodzina.assign(odl_m=float("nan"), zrodlo=ZRODLO_SASIEDZI))

    if not czesci:
        return pd.DataFrame(columns=KOLUMNY)
    out = (
        pd.concat(czesci, ignore_index=True)
        .rename(columns={"kod": "kod_pocztowy"})
        .sort_values(["numer", "kod_pocztowy", "odl_m"])
        .drop_duplicates(["numer", "kod_pocztowy"])
    )
    out["odl_m"] = out["odl_m"].round(1)
    return out.sort_values(["numer", "odl_m", "kod_pocztowy"], ignore_index=True)[KOLUMNY]
