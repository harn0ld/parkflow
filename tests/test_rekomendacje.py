import pandas as pd

from parkflow.rekomendacje import rekomendacje


def test_rekomendacje_uwzgledniaja_jakosc_danych_i_powtarzalnosc():
    def row(kod, blok="10-13", poziom="P4", **zmiany):
        return dict(kod=kod, sezon="lato", blok=blok, poziom=poziom,
                    spp=True, za_malo_danych=False, karty_przyjezdne=50,
                    presja=0.5, percentyl=95) | zmiany

    tabela = pd.DataFrame([
        row("trwaly"), row("trwaly", "07-10", "P3", percentyl=80),
        row("szczyt"), row("szczyt", "07-10", za_malo_danych=True),
        row("malo", karty_przyjezdne=29), row("bufor", spp=False),
        row("ukryty"), row("niski", poziom="P2", percentyl=60),
        row("inny_sezon", sezon="rok_akademicki"),
    ])
    wynik = rekomendacje(tabela, pd.DataFrame(), "lato", "10-13", {"ukryty"})
    assert list(wynik.kod) == ["trwaly", "szczyt"]
    assert list(wynik.bloki_wysokiej_presji) == [2, 1]
    assert list(wynik.bloki_z_danymi) == [2, 1]
    assert "zwiększenia" in wynik.iloc[0].dzialanie
    assert "godzinach szczytu" in wynik.iloc[1].dzialanie
    assert rekomendacje(tabela, pd.DataFrame(), "lato", "16-19", set()).empty
