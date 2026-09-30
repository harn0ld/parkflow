"""Profil dnia dla odtwarzania mapy: tabela P → kod × blok z presją."""

import math

import pandas as pd

from parkflow.mapa import profil_dnia
from parkflow.model import BLOKI, tabela_p


def strefa(kod, blok, presja, sezon="lato"):
    malo = presja is None
    return dict(kod=kod, blok=blok, sezon=sezon, karty_przyjezdne=math.nan if malo else 100.0,
                presja=math.nan if malo else float(presja), za_malo_danych=malo, spp=True)


def test_profil_dnia_bloki_w_kolejnosci_dnia_a_za_malo_danych_jako_nan():
    agg = pd.DataFrame([
        strefa("90-001", "16-19", 4), strefa("90-001", "07-10", 1), strefa("90-001", "10-13", None),
        strefa("90-002", "13-16", 2), strefa("90-002", "13-16", 3, sezon="rok_akademicki"),
    ])
    profil = profil_dnia(tabela_p(agg), "lato")

    assert list(profil.columns) == list(BLOKI)
    assert profil.loc["90-001", "07-10"] == 1
    assert profil.loc["90-001", "16-19"] == 4
    assert math.isnan(profil.loc["90-001", "10-13"])
    # Brak komórki w agregatach też jest „za mało danych”, a inny sezon nie przecieka.
    assert math.isnan(profil.loc["90-002", "07-10"])
    assert profil.loc["90-002", "13-16"] == 2
