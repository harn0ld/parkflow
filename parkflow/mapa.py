"""Stan kodów na mapie dla wybranego sezonu i bloku (ticket 02). Czyste pandas, bez geometrii."""

from collections.abc import Iterable

import pandas as pd

from parkflow.model import BLOKI, ZA_MALO_DANYCH

POZIOM = "poziom"
ZA_MALO = "za_malo_danych"
WYLACZONY = "wylaczony"


def stan_kodow(kody: Iterable[str], komorki: pd.DataFrame, wylaczone: dict[str, str]) -> pd.DataFrame:
    """Kody z mapy + komórki tabeli P (jeden sezon i blok) → kod, stan, poziom, adnotacja, opis, spp, percentyl.

    - kod wyłączony (zbiorczy / galeria): stan `wylaczony`, bez poziomu, opis z `wylaczone`;
    - kod bez komórki w tabeli P (brak transakcji Visa) albo komórka „za mało danych”: stan `za_malo_danych`,
      poziom P1 (jak w modelu), adnotacja „za mało danych”;
    - pozostałe: stan `poziom`, poziom z tabeli P.
    """
    kody = pd.Series(list(dict.fromkeys(kody)), dtype=str, name="kod")
    k = komorki[["kod", "poziom", "adnotacja", "spp", "percentyl"]].drop_duplicates("kod")
    df = pd.DataFrame({"kod": kody}).merge(k, on="kod", how="left")
    brak = df["poziom"].isna()
    df.loc[brak, "poziom"] = "P1"
    df.loc[brak, "adnotacja"] = ZA_MALO_DANYCH
    df["stan"] = POZIOM
    df.loc[df["adnotacja"] == ZA_MALO_DANYCH, "stan"] = ZA_MALO
    df["opis"] = df["kod"].map(wylaczone).fillna("")
    wyl = df["kod"].isin(set(wylaczone))
    df.loc[wyl, "stan"] = WYLACZONY
    df.loc[wyl, ["poziom", "adnotacja"]] = ""
    df["adnotacja"] = df["adnotacja"].fillna("")
    return df[["kod", "stan", "poziom", "adnotacja", "opis", "spp", "percentyl"]]


def profil_dnia(tabela: pd.DataFrame, sezon: str) -> pd.DataFrame:
    """Tabela P jednego sezonu → kod × blok (kolejność `BLOKI`) z presją; NaN = „za mało danych”.

    Wejście dla odtwarzania dnia na mapie: przejścia między blokami interpoluje dopiero widok.
    """
    sel = tabela[tabela["sezon"] == sezon]
    presja = sel["presja"].where(sel["adnotacja"] != ZA_MALO_DANYCH)
    return (sel.assign(presja=presja)
            .pivot(index="kod", columns="blok", values="presja")
            .reindex(columns=list(BLOKI)))
