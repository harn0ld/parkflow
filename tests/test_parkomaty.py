"""Ticket 06: logika digitalizacji parkomatów (numery, georeferencja, kod pocztowy)."""

import numpy as np
import pandas as pd
import pytest

from pipeline import parkomaty as P


# ---------- numery ----------

@pytest.mark.parametrize("tekst, litera, numer", [
    ("438B", "B", 438),
    ("12A", "A", 12),
    ("B5A", "A", 5),  # pionowa kreska ramki przed cyframi
    ("D67A", "A", 67),
    ("2178", "B", 217),  # B przeczytane jako 8
    (" 99B\n", "B", 99),
    ("440D", "D", 440),
])
def test_parsuj_etykiete_poprawne(tekst, litera, numer):
    assert P.parsuj_etykiete(tekst, litera) == numer


@pytest.mark.parametrize("tekst, litera", [
    ("", "A"),
    ("A", "A"),
    ("12B", "A"),  # litera ≠ kolor ramki
    ("441B", "B"),  # poza zakresem mapy
    ("0A", "A"),
    ("23A3BB", "B"),
    ("1274", "A"),  # 8 → B tylko dla ramek B
])
def test_parsuj_etykiete_odrzuca(tekst, litera):
    assert P.parsuj_etykiete(tekst, litera) is None


def test_numer_id_jak_w_danych_visa():
    assert P.numer_id(438, "B") == "438B"


def test_waliduj_numery():
    w = P.waliduj_numery(pd.Series([1, 2, 2, 441, np.nan] + list(range(4, 441))))
    assert w["duplikaty"] == [2]
    assert w["poza_zakresem"] == [441]
    assert w["brakujace"] == [3]


def test_rozstrzygnij_odczyty_manual_wygrywa_i_konflikty_odpadaja():
    o = pd.DataFrame([
        (0, 10, "ocr"), (0, 11, "manual"),  # manual nadpisuje OCR tej kropki
        (1, 11, "ocr"),  # numer zajęty ręcznie → OCR odpada
        (2, 20, "ocr"), (3, 20, "ocr"),  # jeden numer w dwóch kropkach → oba odpadają
        (4, 30, "ocr"), (4, 31, "ocr"),  # dwie różne liczby w jednej kropce → odpada
        (5, 40, "ocr"), (5, 40, "ocr"),  # zgodne detektory → jeden wiersz
    ], columns=["kropka", "numer", "zrodlo"])
    r = P.rozstrzygnij_odczyty(o)
    assert r.values.tolist() == [[0, 11, "manual"], [5, 40, "ocr"]]


def test_rozstrzygnij_odczyty_blad_w_recznych():
    o = pd.DataFrame([(0, 1, "manual"), (1, 1, "manual")], columns=["kropka", "numer", "zrodlo"])
    with pytest.raises(ValueError):
        P.rozstrzygnij_odczyty(o)


# ---------- georeferencja ----------

def _afiniczna_testowa():
    # ~0,5 m/px, lekki obrót, oś y obrazu w dół (northing maleje)
    return np.array([[0.50, -0.05], [0.04, -0.51], [530000.0, 435000.0]])


def test_dopasuj_afiniczna_odtwarza_transformacje():
    m = _afiniczna_testowa()
    px = np.array([[0, 0], [1000, 0], [0, 1000], [800, 900], [300, 200]], float)
    xy = P.zastosuj_afiniczna(m, px)
    np.testing.assert_allclose(P.dopasuj_afiniczna(px, xy), m, atol=1e-6)


def test_bledy_georeferencji_zero_dla_dokladnych_i_loo_wykrywa_zly_punkt():
    m = _afiniczna_testowa()
    rng = np.random.default_rng(0)
    px = rng.uniform(0, 6000, (12, 2))
    xy = P.zastosuj_afiniczna(m, px)
    b = P.bledy_georeferencji(px, xy)
    assert b.reszta_m.max() < 1e-6 and b.loo_m.max() < 1e-6
    xy[3] += [40, 0]  # jeden punkt kontrolny przesunięty o 40 m
    b = P.bledy_georeferencji(px, xy)
    assert b.loo_m.idxmax() == 3
    assert b.loo_m[3] > b.reszta_m[3]  # LOO nie „chowa” błędu w dopasowaniu


def test_afiniczna_wymaga_trzech_punktow():
    with pytest.raises(ValueError):
        P.dopasuj_afiniczna(np.zeros((2, 2)), np.zeros((2, 2)))


def test_dopasuj_podobienstwo_skala_i_odbicie_osi_y():
    px = np.array([[0, 0], [100, 0], [0, 100]], float)
    xy = np.array([[1000, 2000], [1050, 2000], [1000, 1950]], float)  # 0,5 m/px, y w dół
    m = P.dopasuj_podobienstwo(px, xy)
    np.testing.assert_allclose(P.zastosuj_afiniczna(m, [[200, 200]])[0], [1100, 1900], atol=1e-6)
    assert P.skala_m_na_px(m) == pytest.approx((0.5, 0.5))


def test_wgs84_2180_w_obie_strony():
    x, y = P.do_2180(51.77336, 19.43866)
    assert 529000 < x < 533000 and 430000 < y < 437000  # Łódź w PUWG 1992
    lat, lon = P.do_wgs84(x, y)
    assert lat == pytest.approx(51.77336, abs=1e-7) and lon == pytest.approx(19.43866, abs=1e-7)


# ---------- kod pocztowy ----------

def test_przypisz_kod_najblizszy_punkt_adresowy():
    adresy = np.array([[0, 0], [100, 0], [0, 100]], float)
    kody = np.array(["90-001", "90-002", "91-003"])
    r = P.przypisz_kod(np.array([[10, 5], [90, 10], [5, 70]], float), adresy, kody)
    assert r.kod_pocztowy.tolist() == ["90-001", "90-002", "91-003"]
    assert r.odl_adres_m.iloc[0] == pytest.approx(11.2, abs=0.05)


def test_kody_spp_to_kody_z_parkomatem():
    p = pd.DataFrame({
        "numer": ["1A", "2A", "3B", "500"],
        "kod_pocztowy": ["90-001", "90-001", "90-002", None],  # 500: lokalizacja nieznana
    })
    r = P.kody_spp(p)
    assert r.values.tolist() == [["90-001", 2], ["90-002", 1]]


ZDMK_XML = """﻿<?xml version="1.0" encoding="utf-8"?>
<folder>
<placemark>
        <name>Sektor A13</name>
        <card>zbliżeniowa</card>
        <model>Solari SPAZIO EVO</model>
        <parkingmeter>0042</parkingmeter>
        <address>ul. Szlak 5-7</address>
        <coordinates><latitude>50.0704</latitude><longitude>19.9336</longitude></coordinates>
</placemark>
<placemark>
        <name>Sektor C7</name>
        <card>brak</card>
        <model>Flowbird STRADA PAL</model>
        <parkingmeter>3058</parkingmeter>
        <address>ul. Kalwaryjska 1</address>
        <coordinates><latitude>50.0441</latitude><longitude>19.9460</longitude></coordinates>
</placemark>
</folder>"""


def test_parsuj_zdmk_numer_bez_zer_i_podstrefa_z_sektora():
    df = P.parsuj_zdmk(ZDMK_XML)
    assert df["numer"].tolist() == ["42", "3058"]
    assert df["sektor"].tolist() == ["A13", "C7"]
    assert df["podstrefa"].tolist() == ["A", "C"]
    assert df.loc[1, ["adres", "model", "karta"]].tolist() == ["ul. Kalwaryjska 1", "Flowbird STRADA PAL", "brak"]
    assert df.loc[0, ["lat", "lon"]].tolist() == [50.0704, 19.9336]
