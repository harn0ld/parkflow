"""Granica 2: agregaty → tabela P (spec, Testing Decisions). Czyste pandas, bez Sparka."""

import math

import pandas as pd
import pytest

from parkflow.dane import KATALOG_AGG, KATALOG_SAMPLE, KONTRAKT, sprawdz_kontrakt, wczytaj_agregaty
from parkflow.model import BLOKI, SEZONY, ZA_MALO_DANYCH, czasy_wizyt, harmonogram, tabela_p


def strefa(kod, presja, blok="10-13", sezon="lato", karty=100.0, spp=True):
    """Wiersz agg_strefy; `presja=None` oznacza komórkę poniżej progu 30 kart."""
    if presja is None:
        return dict(kod=kod, blok=blok, sezon=sezon, karty_przyjezdne=math.nan, presja=math.nan,
                    za_malo_danych=True, spp=spp)
    return dict(kod=kod, blok=blok, sezon=sezon, karty_przyjezdne=karty, presja=float(presja),
                za_malo_danych=False, spp=spp)


def poziomy(tab, sezon="lato", blok="10-13"):
    sel = tab[(tab["sezon"] == sezon) & (tab["blok"] == blok)]
    return dict(zip(sel["kod"], sel["poziom"]))


def kody(n, prefix="90-0"):
    return [f"{prefix}{i:02d}" for i in range(1, n + 1)]


# Presje na granicach progów 0,05 / 0,15 / 0,30: próg należy do niższego poziomu.
PRESJE = [0.0, 0.05, 0.051, 0.15, 0.151, 0.30, 0.301, 2.0]
POZIOMY_PRESJI = ["P1", "P1", "P2", "P2", "P3", "P3", "P4", "P4"]


def test_poziom_ze_stalych_progow_presji():
    agg = pd.DataFrame([strefa(k, p) for k, p in zip(kody(8), PRESJE)])
    got = poziomy(tabela_p(agg))
    assert [got[k] for k in kody(8)] == POZIOMY_PRESJI


def test_poziom_nie_zalezy_od_innych_komorek():
    # Ta sama presja daje ten sam poziom niezależnie od reszty miasta (bez normalizacji do rozkładu).
    sama = poziomy(tabela_p(pd.DataFrame([strefa("90-001", 0.2)])))
    z_tlumem = poziomy(tabela_p(pd.DataFrame([strefa("90-001", 0.2)] + [strefa(k, 5.0) for k in kody(9, "91-0")])))
    assert sama["90-001"] == z_tlumem["90-001"] == "P3"


def test_sezony_z_tym_samym_progiem():
    # Rok akademicki ma presję 10× wyższą, więc ma wyższe poziomy — progi są wspólne dla sezonów.
    rows = [strefa("90-001", 0.02, sezon="lato"), strefa("90-001", 0.2, sezon="rok_akademicki")]
    tab = tabela_p(pd.DataFrame(rows))
    assert (poziomy(tab, "lato")["90-001"], poziomy(tab, "rok_akademicki")["90-001"]) == ("P1", "P3")


def test_percentyl_informacyjny_w_miescie_i_sezonie():
    agg = pd.DataFrame([strefa(k, p) for k, p in zip(kody(4), [0.01, 0.02, 0.03, 0.04])])
    tab = tabela_p(agg)
    sel = tab[(tab["blok"] == "10-13") & (tab["sezon"] == "lato")].set_index("kod")
    assert sel["percentyl"].tolist() == [25.0, 50.0, 75.0, 100.0]
    assert set(sel["poziom"]) == {"P1"}  # najwyższy percentyl nie podnosi poziomu


def test_za_malo_danych_daje_p1_z_adnotacja_i_nie_liczy_sie_do_percentyli():
    rows = [strefa(k, p) for k, p in zip(kody(8), PRESJE)]
    rows += [strefa(k, None) for k in kody(5, prefix="91-0")]
    tab = tabela_p(pd.DataFrame(rows))
    got = poziomy(tab)
    assert [got[k] for k in kody(8)] == POZIOMY_PRESJI
    malo = tab[tab["kod"].str.startswith("91-") & (tab["blok"] == "10-13") & (tab["sezon"] == "lato")]
    assert (malo["poziom"] == "P1").all()
    assert (malo["adnotacja"] == ZA_MALO_DANYCH).all()
    assert malo["za_malo_danych"].all() and malo["percentyl"].isna().all()
    assert (tab.loc[~tab["za_malo_danych"], "adnotacja"] == "").all()


def test_komorka_ponizej_30_kart_jest_za_malo_danych_nawet_bez_flagi():
    rows = [strefa("90-010", 1.0), strefa("91-001", 1000, karty=29.0)]
    tab = tabela_p(pd.DataFrame(rows))
    row = tab[(tab["kod"] == "91-001") & (tab["blok"] == "10-13") & (tab["sezon"] == "lato")].iloc[0]
    assert (row["poziom"], row["adnotacja"]) == ("P1", ZA_MALO_DANYCH)
    assert poziomy(tab)["90-010"] == "P4"


def test_brakujaca_komorka_to_za_malo_danych_a_tabela_jest_pelna():
    # Pipeline nie emituje komórek bez wizyt; tabela P ma mieć kod × wszystkie bloki × oba sezony.
    agg = pd.DataFrame([strefa("90-001", 5.0), strefa("90-002", 7.0, blok="13-16", sezon="rok_akademicki")])
    tab = tabela_p(agg)
    assert len(tab) == 2 * len(BLOKI) * len(SEZONY)
    brak = tab[(tab["kod"] == "90-001") & (tab["sezon"] == "rok_akademicki")]
    assert (brak["poziom"] == "P1").all() and (brak["adnotacja"] == ZA_MALO_DANYCH).all()
    assert tab.loc[tab["kod"] == "90-001", "spp"].eq(True).all()


def test_remisy_w_percentylu_dostaja_najnizsza_range():
    # Sześć zer i 4 wyższe: zera mają percentyl 10% (nie 60%).
    presje = [0, 0, 0, 0, 0, 0, 0.1, 0.2, 0.3, 0.4]
    tab = tabela_p(pd.DataFrame([strefa(k, p) for k, p in zip(kody(10), presje)]))
    sel = tab[(tab["blok"] == "10-13") & (tab["sezon"] == "lato")].set_index("kod")
    assert sel.loc[kody(6), "percentyl"].eq(10.0).all()
    assert [poziomy(tab)[k] for k in kody(10)] == ["P1"] * 6 + ["P2", "P3", "P3", "P4"]


def test_harmonogram_kod_x_blok():
    rows = [strefa(k, p, blok=b) for b in BLOKI for k, p in zip(kody(8), PRESJE)]
    h = harmonogram(tabela_p(pd.DataFrame(rows)), "lato")
    assert list(h.columns) == list(BLOKI)
    assert h.loc["90-008"].tolist() == ["P4"] * 4
    assert h.loc["90-001", "07-10"] == "P1"


def test_czasy_wizyt_kod_x_grupa_dla_sezonu_i_bloku():
    def g(kod, grupa, czas, blok="10-13", sezon="lato"):
        return dict(kod=kod, blok=blok, sezon=sezon, grupa=grupa, karty_przyjezdne=40,
                    wspolczynnik_kierowcow=0.1, mediana_czasu_wizyty_min=czas, presja=1.0, spp=True)
    agg = pd.DataFrame([
        g("90-002", "gastronomia", 95.0), g("90-001", "gastronomia", 80.0), g("90-001", "handel", 50.0),
        g("90-001", "handel", 999.0, blok="13-16"), g("90-001", "handel", 999.0, sezon="rok_akademicki"),
    ])
    t = czasy_wizyt(agg, "lato", "10-13")
    assert list(t.index) == ["90-001", "90-002"] and list(t.columns) == ["gastronomia", "handel"]
    assert t.loc["90-001", "handel"] == 50.0 and t.loc["90-002", "gastronomia"] == 95.0
    assert math.isnan(t.loc["90-002", "handel"])


# ---------- kontrakt i dane przykładowe ----------

@pytest.mark.parametrize("nazwa", list(KONTRAKT))
def test_przykladowe_agregaty_maja_schemat_pipeline(nazwa):
    sample = pd.read_parquet(KATALOG_SAMPLE / f"{nazwa}.parquet")
    sprawdz_kontrakt(sample, nazwa)
    if (KATALOG_AGG / f"{nazwa}.parquet").exists():
        real = pd.read_parquet(KATALOG_AGG / f"{nazwa}.parquet")
        sprawdz_kontrakt(real, nazwa)
        assert list(sample.columns) == list(real.columns)


def test_model_na_przykladowych_agregatach():
    agg = wczytaj_agregaty(KATALOG_SAMPLE)
    tab = tabela_p(agg.strefy)
    n_kodow = tab["kod"].nunique()
    assert 12 <= n_kodow <= 20
    assert len(tab) == n_kodow * len(BLOKI) * len(SEZONY)
    for sezon in SEZONY:
        assert set(tab.loc[tab["sezon"] == sezon, "poziom"]) == {"P1", "P2", "P3", "P4"}
    assert (tab["adnotacja"] == ZA_MALO_DANYCH).any()


def test_wczytaj_agregaty_spada_na_sample_gdy_brak_agg(tmp_path):
    agg = wczytaj_agregaty(kandydaci=[tmp_path / "nie_ma", KATALOG_SAMPLE])
    assert agg.katalog == KATALOG_SAMPLE
    assert set(agg.strefy.columns) == set(KONTRAKT["agg_strefy"])


def test_brak_opcjonalnej_kalibracji_daje_none(tmp_path):
    for nazwa in ("agg_strefy", "agg_grupy"):
        (tmp_path / f"{nazwa}.parquet").write_bytes((KATALOG_SAMPLE / f"{nazwa}.parquet").read_bytes())
    assert wczytaj_agregaty(tmp_path).kalibracja is None
    assert wczytaj_agregaty(KATALOG_SAMPLE).kalibracja is not None
