"""Kandydaci do analizy parkingowej; reguły nie szacują brakującej liczby miejsc."""

import pandas as pd

from parkflow.taryfa import dominujaca_grupa


def rekomendacje(tabela: pd.DataFrame, grupy: pd.DataFrame, sezon: str, blok: str,
                 wykluczone: set[str]) -> pd.DataFrame:
    poprawne = tabela.loc[
        tabela["sezon"].eq(sezon) & tabela["spp"].eq(True)
        & ~tabela["za_malo_danych"] & tabela["karty_przyjezdne"].ge(30)
        & tabela["presja"].notna()
        & ~tabela["kod"].isin(wykluczone)
    ]
    wysokie = poprawne.loc[poprawne["poziom"].isin(["P3", "P4"])]
    wynik = wysokie.loc[wysokie["blok"].eq(blok)].copy()
    wynik["bloki_wysokiej_presji"] = wynik["kod"].map(wysokie.groupby("kod")["blok"].nunique())
    wynik["bloki_z_danymi"] = wynik["kod"].map(poprawne.groupby("kod")["blok"].nunique())
    wynik["grupa"] = [dominujaca_grupa(grupy, kod, sezon, blok) for kod in wynik["kod"]]
    wynik["dzialanie"] = [
        "Sprawdź możliwość zwiększenia liczby miejsc" if n >= 2
        else "Sprawdź organizację parkowania w godzinach szczytu"
        for n in wynik["bloki_wysokiej_presji"]
    ]
    wynik["dodatkowo"] = [
        "Sprawdź rotację i miejsca krótkiego postoju przy sklepach i usługach."
        if grupa in {"szybkie_uslugi", "spozywcze_male"}
        else "Sprawdź możliwość współdzielenia istniejących parkingów i kierowania do wolnych miejsc."
        for grupa in wynik["grupa"]
    ]
    return wynik.sort_values(
        ["bloki_wysokiej_presji", "presja", "kod"], ascending=[False, False, True]
    ).reset_index(drop=True)
