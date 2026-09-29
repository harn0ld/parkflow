"""Dane warstw mapy: parkomaty (ticket 06) i zmierzony popyt (ticket 07). Czyste pandas."""

import math

import pandas as pd
import pytest

from parkflow.dane import KATALOG_AGG, KODY_ULICE, PARKOMATY, wczytaj_agregaty, wczytaj_kody_ulice, wczytaj_parkomaty
from parkflow.warstwy import PROMIEN_MAX_M, parkomaty_na_mapie, zmierzony_popyt


def popyt(*wiersze):
    return pd.DataFrame(wiersze, columns=["kod", "blok", "sezon", "oplacone_autogodziny", "karty"])


KODY = pd.DataFrame({"kod": ["90-001", "90-002", "90-003"], "ulice": ["Tuwima", None, "Piotrkowska"],
                     "lat": [51.75, 51.76, 51.77], "lon": [19.45, 19.46, 19.47]})


def test_popyt_filtruje_sezon_i_blok_i_dokleja_centroid_kodu():
    agg = popyt(("90-001", "10-13", "lato", 4.0, 40), ("90-001", "13-16", "lato", 9.0, 50),
                ("90-002", "10-13", "rok_akademicki", 1.0, 31))
    df = zmierzony_popyt(agg, KODY, "lato", "10-13")
    assert df[["kod", "lat", "lon", "ulice", "oplacone_autogodziny", "karty"]].to_dict("records") == [
        {"kod": "90-001", "lat": 51.75, "lon": 19.45, "ulice": "Tuwima", "oplacone_autogodziny": 4.0, "karty": 40}]


def test_skala_promienia_wspolna_dla_calej_tabeli_pole_proporcjonalne_do_popytu():
    agg = popyt(("90-001", "10-13", "lato", 4.0, 40), ("90-003", "10-13", "lato", 1.0, 30),
                ("90-001", "13-16", "rok_akademicki", 16.0, 90))
    df = zmierzony_popyt(agg, KODY, "lato", "10-13").set_index("kod")
    assert df.loc["90-001", "promien_m"] == pytest.approx(PROMIEN_MAX_M * math.sqrt(4 / 16))
    assert df.loc["90-003", "promien_m"] == pytest.approx(PROMIEN_MAX_M * math.sqrt(1 / 16))
    assert df.index.tolist() == ["90-001", "90-003"]  # większe koło rysowane pierwsze (pod mniejszym)


def test_popyt_pomija_kody_bez_centroidu_i_zwraca_pusta_tabele_bez_danych():
    agg = popyt(("91-999", "10-13", "lato", 4.0,40))
    assert zmierzony_popyt(agg, KODY, "lato", "10-13").empty
    assert zmierzony_popyt(agg, KODY, "lato", "07-10").empty
    assert zmierzony_popyt(popyt(), KODY, "lato", "10-13").empty


def test_parkomaty_bez_lokalizacji_nie_trafiaja_na_mape():
    p = pd.DataFrame({
        "numer": ["1A", "440C", "612B"], "podstrefa": ["A", "B", None], "podstrefa_2024": ["A", "C", "B"],
        "lat": [51.77, 51.76, None], "lon": [19.45, 19.47, None], "ulica": ["Ogrodowa", "Tuwima", None],
        "kod_pocztowy": ["91-062", "90-001", None],
        "status_lokalizacji": ["mapa_2024", "wspolrzedne_zdit", "lokalizacja nieznana"],
    })
    df = parkomaty_na_mapie(p)
    assert df["numer"].tolist() == ["1A", "440C"]
    assert df["status"].tolist() == ["z mapy ZDiT (VI 2024)", "współrzędne ZDiT"]


def test_prawdziwe_parkomaty_i_popyt_maja_dane_dla_warstw():
    parkomaty = parkomaty_na_mapie(wczytaj_parkomaty(PARKOMATY))
    assert len(parkomaty) >= 400 and set(parkomaty["podstrefa"]) <= {"A", "B", "C"}
    if not (KATALOG_AGG / "agg_parkomaty_strefy.parquet").exists():
        pytest.skip("brak data/agg")
    agg = wczytaj_agregaty(KATALOG_AGG)
    assert agg.popyt is not None and (agg.popyt["karty"] >= 30).all()
    df = zmierzony_popyt(agg.popyt, wczytaj_kody_ulice(KODY_ULICE), "rok_akademicki", "10-13")
    assert len(df) > 0 and df["promien_m"].between(0, PROMIEN_MAX_M).all()
