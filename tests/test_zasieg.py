"""Zasięg parkomatu ~500 m na poziomie kodów pocztowych (ticket 08)."""

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from pipeline.parkomaty import do_wgs84
from pipeline.zasieg import ZRODLO_PROMIEN, ZRODLO_SASIEDZI, zasieg_parkomatow

X0, Y0 = 540_000, 400_000  # okolice Łodzi w EPSG:2180


def _kody():
    # Rząd kwadratów 200 m: A [0,200], B [200,400], C [400,600], D [800,1000] (przerwa 200 m).
    xs = {"A": 0, "B": 200, "C": 400, "D": 800}
    return gpd.GeoDataFrame({"kod": list(xs)}, geometry=[box(X0 + x, Y0, X0 + x + 200, Y0 + 200) for x in xs.values()],
                            crs=2180)


def _parkomat(numer, x=None, y=None, kod=None):
    if x is None:
        return {"numer": numer, "lat": None, "lon": None, "kod_pocztowy": kod}
    lat, lon = do_wgs84([X0 + x], [Y0 + y])
    return {"numer": numer, "lat": float(lat[0]), "lon": float(lon[0]), "kod_pocztowy": kod}


def test_codes_whose_polygon_is_within_500_m_of_the_meter():
    z = zasieg_parkomatow(pd.DataFrame([_parkomat("1a", 100, 100, "A")]), _kody())
    assert list(z["kod_pocztowy"]) == ["A", "B", "C"]  # D: krawędź 700 m od parkomatu
    assert list(z["odl_m"]) == [0.0, 100.0, 300.0]
    assert set(z["numer"]) == {"1A"} and set(z["zrodlo"]) == {ZRODLO_PROMIEN}


def test_meter_without_location_falls_back_to_same_or_neighbouring_code():
    z = zasieg_parkomatow(pd.DataFrame([_parkomat("2A", kod="B"), _parkomat("3A")]), _kody())
    assert sorted(z["kod_pocztowy"]) == ["A", "B", "C"]  # 3A: bez lokalizacji i kodu → brak zasięgu
    assert set(z["numer"]) == {"2A"} and set(z["zrodlo"]) == {ZRODLO_SASIEDZI}


def test_reference_table_covers_each_located_meter_with_its_own_code():
    zasieg = pd.read_csv("data/parkomaty_zasieg.csv", dtype={"numer": str, "kod_pocztowy": str})
    parkomaty = pd.read_csv("data/parkomaty.csv", dtype=str).dropna(subset=["kod_pocztowy"])
    para = parkomaty[["numer", "kod_pocztowy"]].merge(zasieg, on=["numer", "kod_pocztowy"])
    assert len(para) == len(parkomaty)
    assert (para["odl_m"] <= 1).all()  # parkomat na krawędzi polygonu (dokładność 1e-6°)
    assert zasieg["odl_m"].max() <= 500
