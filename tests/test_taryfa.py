"""Granica 2: tabela P + agg_grupy + polityka → taryfa i karta kierowcy (SPEC §5)."""

from datetime import datetime

import pandas as pd
import pytest

from parkflow.model import tabela_p
from parkflow.taryfa import (
    POLITYKA,
    Polityka,
    blok_dla,
    dominujaca_grupa,
    karta_kierowcy,
    koszt_postoju,
    przesuniecie_okresu,
)

PN_10_30 = datetime(2025, 10, 6, 10, 30)  # poniedziałek


# --- konfiguracja polityki ------------------------------------------------------------------

def test_polityka_s_6_zl_i_tabela_mnoznikow_ze_specu():
    t = {p: POLITYKA.taryfa(p) for p in ("P1", "P2", "P3", "P4")}
    assert POLITYKA.stawka_bazowa == 6.00
    assert (t["P1"].okres_pref_min, t["P1"].cena_pref, t["P1"].ryczalt) == (120, 3.60, False)
    assert (t["P1"].stawka_potem, t["P1"].stawka_po_2h) == (4.80, 4.80)
    assert (t["P2"].okres_pref_min, t["P2"].cena_pref, t["P2"].ryczalt) == (60, 6.00, False)
    assert (t["P2"].stawka_potem, t["P2"].stawka_po_2h) == (7.20, 8.40)
    assert (t["P3"].okres_pref_min, t["P3"].cena_pref, t["P3"].ryczalt) == (45, 3.00, True)
    assert (t["P3"].stawka_potem, t["P3"].stawka_po_2h) == (9.00, 12.00)
    assert (t["P4"].okres_pref_min, t["P4"].cena_pref, t["P4"].ryczalt) == (30, 1.80, True)
    assert (t["P4"].stawka_potem, t["P4"].stawka_po_2h) == (12.00, 18.00)


def test_stawki_skaluja_sie_z_s():
    assert Polityka(stawka_bazowa=10.0).taryfa("P4").stawka_po_2h == 30.00


# --- koszt postoju --------------------------------------------------------------------------

@pytest.mark.parametrize("poziom, minuty, oczekiwany", [
    ("P4", 90, 13.80),   # 1,80 za 30 min + 60 min × 12,00 zł/h
    ("P4", 20, 1.80),    # ryczałt za cały okres, nawet gdy krócej
    ("P4", 150, 28.80),  # 1,80 + 90 min × 12 + 30 min × 18
    ("P1", 180, 12.00),  # 2 h × 3,60 + 1 h × 4,80
    ("P1", 60, 3.60),
    ("P2", 180, 21.60),  # 1 h × 6,00 + 1 h × 7,20 + 1 h × 8,40
    ("P3", 45, 3.00),
    ("P3", 120, 14.25),  # 3,00 + 75 min × 9,00 zł/h
    ("P3", 180, 26.25),  # 14,25 + 1 h × 12,00
    ("P2", 0, 0.00),
])
def test_koszt_postoju(poziom, minuty, oczekiwany):
    assert koszt_postoju(poziom, minuty) == pytest.approx(oczekiwany)


def test_ulga_mieszkanca_085():
    assert koszt_postoju("P4", 90, ulga=True) == pytest.approx(13.80 * 0.85)
    assert koszt_postoju("P1", 180, ulga=True) == pytest.approx(10.20)
    assert POLITYKA.taryfa("P3", ulga=True).stawka_potem == pytest.approx(7.65)


def test_przesuniecie_okresu_preferencyjnego_w_koszcie():
    # P4 skrócony do 15 min: ryczałt 1,80 za 15 min, potem 75 min × 12 zł/h.
    assert koszt_postoju("P4", 90, przesuniecie_min=-15) == pytest.approx(1.80 + 15.00)
    # P4 wydłużony do 45 min: 1,80 + 45 min × 12 zł/h.
    assert koszt_postoju("P4", 90, przesuniecie_min=15) == pytest.approx(1.80 + 9.00)
    # P1 wydłużony do 2 h 15 min: preferencyjna stawka także po 2 h, do końca okresu.
    assert koszt_postoju("P1", 180, przesuniecie_min=15) == pytest.approx(135 / 60 * 3.60 + 45 / 60 * 4.80)
    # P2 skrócony do 45 min: 45 min × 6 + 75 min × 7,20 + 60 min × 8,40.
    assert koszt_postoju("P2", 180, przesuniecie_min=-15) == pytest.approx(4.50 + 9.00 + 8.40)


# --- przesunięcie wg dominującej grupy ------------------------------------------------------

@pytest.mark.parametrize("grupa, przesuniecie", [
    ("szybkie_uslugi", -15),
    ("spozywcze_male", 0),
    ("handel", 0),
    ("gastronomia", 0),
    ("uslugi_osobiste", 15),
    ("rozrywka_kultura", 15),
    (None, 0),
])
def test_przesuniecie_okresu_wg_grupy(grupa, przesuniecie):
    assert przesuniecie_okresu(grupa) == przesuniecie


def grupa(kod, g, presja, karty=50, blok="10-13", sezon="lato"):
    return dict(kod=kod, blok=blok, sezon=sezon, grupa=g, karty_przyjezdne=karty,
                wspolczynnik_kierowcow=0.2, mediana_czasu_wizyty_min=45.0, presja=presja, spp=True)


def test_dominujaca_grupa_to_najwieksza_presja_w_komorce():
    agg = pd.DataFrame([
        grupa("90-001", "szybkie_uslugi", 1.0, karty=500),  # najwięcej kart, ale mała presja
        grupa("90-001", "uslugi_osobiste", 3.0, karty=40),
        grupa("90-001", "handel", 2.0),
        grupa("90-001", "szybkie_uslugi", 9.0, blok="16-19"),  # inny blok
        grupa("90-002", "rozrywka_kultura", 9.0),  # inny kod
    ])
    assert dominujaca_grupa(agg, "90-001", "lato", "10-13") == "uslugi_osobiste"
    assert dominujaca_grupa(agg, "90-001", "lato", "16-19") == "szybkie_uslugi"
    assert dominujaca_grupa(agg, "90-001", "rok_akademicki", "10-13") is None


def test_dominujaca_grupa_remis_rozstrzygaja_karty_potem_nazwa():
    agg = pd.DataFrame([grupa("90-001", "handel", 2.0, karty=40), grupa("90-001", "gastronomia", 2.0, karty=60)])
    assert dominujaca_grupa(agg, "90-001", "lato", "10-13") == "gastronomia"
    agg = pd.DataFrame([grupa("90-001", "handel", 2.0), grupa("90-001", "gastronomia", 2.0)])
    assert dominujaca_grupa(agg, "90-001", "lato", "10-13") == "gastronomia"


# --- blok i karta kierowcy ------------------------------------------------------------------

@pytest.mark.parametrize("chwila, blok", [
    (datetime(2025, 10, 6, 7, 0), "07-10"),
    (datetime(2025, 10, 6, 9, 59), "07-10"),
    (datetime(2025, 10, 6, 10, 0), "10-13"),
    (datetime(2025, 10, 10, 18, 59), "16-19"),  # piątek
    (datetime(2025, 10, 6, 19, 0), None),
    (datetime(2025, 10, 6, 6, 59), None),
    (datetime(2025, 10, 11, 12, 0), None),  # sobota
    (datetime(2025, 10, 12, 12, 0), None),  # niedziela
])
def test_blok_dla_chwili(chwila, blok):
    assert blok_dla(chwila) == blok


def strefa(kod, blok, presja, sezon="lato"):
    return dict(kod=kod, blok=blok, sezon=sezon, karty_przyjezdne=100.0, presja=float(presja),
                za_malo_danych=False, spp=True)


@pytest.fixture
def tabela():
    # 20 komórek sezonu: 10-13 presje 1..10, 13-16 presje i − 0,5, z wyjątkiem 90-009 (0,1).
    # 90-010: P4 w 10-13 i 13-16, 16-19 brak danych (P1). 90-009: P3 w 10-13 (18/20 = 90%), P1 w 13-16.
    # 90-001: P1 w 10-13, 13-16 i (za mało danych) 16-19.
    rows = [strefa(f"90-0{i:02d}", "10-13", i) for i in range(1, 11)]
    rows += [strefa(f"90-0{i:02d}", "13-16", 0.1 if i == 9 else i - 0.5) for i in range(1, 11)]
    return tabela_p(pd.DataFrame(rows))


def test_karta_kierowcy_komunikat_jak_w_specu(tabela):
    grupy = pd.DataFrame([grupa("90-009", "handel", 1.0)])
    k = karta_kierowcy(tabela, grupy, "90-009", "lato", PN_10_30)
    assert k.poziom == "P3"
    assert k.do_godziny == "13:00"
    assert k.komunikat == (
        "Ta strefa ma teraz poziom P3 (do 13:00). Pierwsze 45 min kosztuje 3,00 zł, "
        "potem 9,00 zł/h, po 2 h 12,00 zł/h."
    )


def test_karta_kierowcy_poziom_trwa_przez_kolejne_bloki_o_tym_samym_poziomie(tabela):
    poziomy = tabela[(tabela["kod"] == "90-010") & (tabela["sezon"] == "lato")].set_index("blok")["poziom"]
    assert poziomy["10-13"] == poziomy["13-16"] == "P4"
    k = karta_kierowcy(tabela, pd.DataFrame([]), "90-010", "lato", PN_10_30)
    assert k.do_godziny == "16:00"


def test_karta_kierowcy_przesuniecie_i_ulga(tabela):
    grupy = pd.DataFrame([grupa("90-010", "uslugi_osobiste", 5.0), grupa("90-010", "handel", 1.0)])
    k = karta_kierowcy(tabela, grupy, "90-010", "lato", PN_10_30)
    assert (k.poziom, k.grupa, k.przesuniecie_min) == ("P4", "uslugi_osobiste", 15)
    assert k.taryfa.okres_pref_min == 45
    assert k.komunikat.startswith("Ta strefa ma teraz poziom P4 (do 16:00). Pierwsze 45 min kosztuje 1,80 zł")
    assert k.taryfa_ulga.cena_pref == pytest.approx(1.53)
    assert "1,53 zł" in k.komunikat_ulga


def test_karta_kierowcy_p1_bez_osobnej_stawki_po_2h(tabela):
    k = karta_kierowcy(tabela, pd.DataFrame([]), "90-001", "lato", PN_10_30)
    assert k.komunikat == (
        "Ta strefa ma teraz poziom P1 (do 19:00). Pierwsze 2 h kosztuje 3,60 zł/h, potem 4,80 zł/h."
    )


def test_karta_kierowcy_za_malo_danych_to_p1_z_adnotacja(tabela):
    k = karta_kierowcy(tabela, pd.DataFrame([]), "90-005", "lato", datetime(2025, 10, 6, 8, 0))
    assert (k.poziom, k.adnotacja) == ("P1", "za mało danych")


def test_karta_kierowcy_poza_godzinami_parkowanie_bezplatne(tabela):
    for chwila in (datetime(2025, 10, 11, 12, 0), datetime(2025, 10, 6, 19, 30)):
        k = karta_kierowcy(tabela, pd.DataFrame([]), "90-010", "lato", chwila)
        assert k.bezplatne and k.poziom is None
        assert k.komunikat == "Parkowanie bezpłatne (strefa płatna działa pn–pt 7–19)."


def test_koszty_kolejnych_godzin(tabela):
    k = karta_kierowcy(tabela, pd.DataFrame([]), "90-010", "lato", PN_10_30)
    # P4: 1,80 + 30 min × 12 = 7,80; potem 12,00; po 2 h 18,00.
    assert k.koszty_godzin(3) == pytest.approx([7.80, 12.00, 18.00])
    assert k.koszty_godzin(3, ulga=True) == pytest.approx([7.80 * 0.85, 12.00 * 0.85, 18.00 * 0.85])
