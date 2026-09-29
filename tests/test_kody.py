"""Ticket 02: kody pocztowe z punktów PRG (ulice, centroidy, polygony) i stan kodów na mapie."""

import json

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, box

from parkflow.dane import KATALOG_AGG, KODY_GEOJSON, KODY_ULICE, kody_wylaczone, wczytaj_kody_ulice
from parkflow.kody import polygony_kodow, skrocona_nazwa, ulice_kodow
from parkflow.mapa import POZIOM, WYLACZONY, ZA_MALO, stan_kodow
from parkflow.model import ZA_MALO_DANYCH


def punkty(rows):
    """rows: (kod, ulica, x, y)."""
    return pd.DataFrame(rows, columns=["kod", "ulica", "x", "y"])


def test_ulice_kodow_centroid_to_srednia_punktow_a_ulice_od_najliczniejszej():
    p = punkty([
        ("90-001", "Tuwima", 0, 0), ("90-001", "Welta", 10, 0), ("90-001", "Welta", 20, 30),
        ("90-002", "Piotrkowska", 100, 100),
    ])
    t = ulice_kodow(p).set_index("kod")
    assert t.loc["90-001", "ulice"] == "Welta; Tuwima"
    assert (t.loc["90-001", "x"], t.loc["90-001", "y"]) == (10, 10)
    assert t.loc["90-001", "liczba_adresow"] == 3 and t.loc["90-001", "liczba_ulic"] == 2
    assert t.loc["90-002", "ulice"] == "Piotrkowska"
    assert list(t.index) == ["90-001", "90-002"]


def test_ulice_kodow_remis_alfabetycznie():
    p = punkty([("90-001", "Zachodnia", 0, 0), ("90-001", "Andrzeja", 1, 1)])
    assert ulice_kodow(p)["ulice"].item() == "Andrzeja; Zachodnia"


def test_skrocona_nazwa():
    assert skrocona_nazwa("Aleja Marszałka Józefa Piłsudskiego", "Piłsudskiego") == "al. Piłsudskiego"
    assert skrocona_nazwa("Gen. Franciszka Kleeberga", "Kleeberga") == "Kleeberga"
    assert skrocona_nazwa("Plac Wolności", None) == "Plac Wolności"


def _siatka():
    """Dwa kody: lewa połowa siatki 90-001, prawa 90-002; plus odległy punkt 90-003. Granica: kwadrat 0–1000."""
    rows = [("90-001" if x < 500 else "90-002", Point(x, y)) for x in range(100, 900, 100) for y in range(100, 600, 100)]
    rows.append(("90-003", Point(900, 900)))
    return gpd.GeoDataFrame(pd.DataFrame(rows, columns=["kod", "geometry"]), crs=2180), box(0, 0, 1000, 1000)


def test_polygony_kodow_teselacja_bez_nakladek_w_granicy_i_buforze():
    pkt, granica = _siatka()
    k = polygony_kodow(pkt, granica, bufor_m=150, uproszczenie_m=0).set_index("kod")
    assert sorted(k.index) == ["90-001", "90-002", "90-003"]
    assert k.geometry.is_valid.all()
    # każdy punkt leży w polygonie swojego kodu
    for kod, p in zip(pkt["kod"], pkt.geometry):
        assert k.loc[kod, "geometry"].buffer(1e-6).contains(p)
    # bez nakładek, w granicy, w buforze punktów
    assert k.area.sum() == pytest.approx(k.union_all().area)
    assert granica.buffer(1e-6).contains(k.union_all())
    assert pkt.buffer(150).union_all().buffer(1e-6).contains(k.union_all())
    # podział lewa/prawa idzie środkiem między kolumnami punktów (x = 450)
    assert k.loc["90-001", "geometry"].bounds[2] == pytest.approx(450)


def test_polygony_kodow_duplikat_wspolrzednych_trafia_do_najczestszego_kodu():
    pkt = gpd.GeoDataFrame({"kod": ["90-001", "90-001", "90-002", "90-003"]},
                           geometry=[Point(100, 100), Point(100, 100), Point(100, 100), Point(400, 100)], crs=2180)
    k = polygony_kodow(pkt, box(0, 0, 500, 200), bufor_m=1000, uproszczenie_m=0)
    assert sorted(k["kod"]) == ["90-001", "90-003"]
    assert k.area.sum() == pytest.approx(500 * 200)


def test_polygony_kodow_uproszczenie_zachowuje_przyleganie():
    pkt, granica = _siatka()
    k = polygony_kodow(pkt, granica, bufor_m=150, uproszczenie_m=20)
    assert k.geometry.is_valid.all()
    assert k.area.sum() == pytest.approx(k.union_all().area)


def komorka(kod, poziom, za_malo=False, spp=True):
    return dict(kod=kod, poziom=poziom, adnotacja=ZA_MALO_DANYCH if za_malo else "", spp=spp,
                percentyl=float("nan") if za_malo else 50.0)


def test_stan_kodow():
    komorki = pd.DataFrame([komorka("90-001", "P3"), komorka("90-002", "P1", za_malo=True)])
    s = stan_kodow(["90-001", "90-002", "90-003", "91-071"], komorki,
                   {"91-071": "wyłączony ze stref: Manufaktura"}).set_index("kod")
    assert s.loc["90-001", ["stan", "poziom", "adnotacja"]].tolist() == [POZIOM, "P3", ""]
    assert s.loc["90-002", ["stan", "poziom", "adnotacja"]].tolist() == [ZA_MALO, "P1", ZA_MALO_DANYCH]
    # brak komórki w tabeli P (brak transakcji) = za mało danych
    assert s.loc["90-003", ["stan", "poziom", "adnotacja"]].tolist() == [ZA_MALO, "P1", ZA_MALO_DANYCH]
    assert s.loc["91-071", ["stan", "poziom", "opis"]].tolist() == [WYLACZONY, "", "wyłączony ze stref: Manufaktura"]


def test_kody_wylaczone_zawieraja_zbiorcze_i_galerie():
    w = kody_wylaczone()
    assert "91-071" in w and "Manufaktura" in w["91-071"]
    zbiorcze = pd.read_parquet(KATALOG_AGG / "kody_zbiorcze.parquet")["kod"]
    assert set(zbiorcze) <= set(w)


@pytest.mark.skipif(not KODY_GEOJSON.exists(), reason="brak data/kody.geojson (scripts/zbuduj_kody.py)")
def test_zbudowane_pliki_kodow_sa_spojne():
    ulice = wczytaj_kody_ulice(KODY_ULICE)
    gj = json.loads(KODY_GEOJSON.read_text())
    kody = [f["properties"]["kod"] for f in gj["features"]]
    assert ulice["kod"].str.fullmatch(r"9[0-4]-\d{3}").all()
    assert set(kody) == set(ulice["kod"]) and len(kody) == len(set(kody))
    assert ulice["lat"].between(51.6, 51.9).all() and ulice["lon"].between(19.3, 19.7).all()
    assert KODY_GEOJSON.stat().st_size < 10e6
