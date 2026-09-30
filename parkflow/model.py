"""Model: agregaty strefy → tabela poziomów P1–P4 (SPEC §4.3–4.4).

Czyste funkcje na pandas, bez I/O. Wejście to `agg_strefy` w kontrakcie pipeline'u
(docs/kontrakt-agregatow.md).

Reguły:
- poziom = stałe progi presji (`PROGI_PRESJI`, samochodo-godziny w bloku, mediana tygodni):
  P1 ≤ 0,05 < P2 ≤ 0,15 < P3 ≤ 0,30 < P4 — ten sam próg w każdym mieście, sezonie i bloku,
  więc poziom nie zależy od tego, jak wypadają inne sektory (bez normalizacji do rozkładu);
- `percentyl` zostaje tylko jako informacja (odsetek komórek sezonu w mieście z presją ≤ tej,
  remisy dostają najniższą rangę); nie wpływa na poziom;
- komórka z flagą `za_malo_danych`, bez presji, z < 30 kartami albo nieobecna w agregatach
  dostaje P1 z adnotacją „za mało danych”;
- bez wygładzania między blokami.
"""

import numpy as np
import pandas as pd

BLOKI = ("07-10", "10-13", "13-16", "16-19")
SEZONY = ("lato", "rok_akademicki")
POZIOMY = ("P1", "P2", "P3", "P4")
# Progi presji P1|P2, P2|P3, P3|P4 [samochodo-h w bloku 3 h, tygodniowo, karty Visa]. Okrągłe wartości
# dobrane raz na danych Łodzi i Krakowa 2025/26 (≈ mediana, 80. i 93. percentyl), potem stałe.
PROGI_PRESJI = (0.05, 0.15, 0.30)
MIN_KART = 30
ZA_MALO_DANYCH = "za mało danych"

KOLUMNY_TABELI_P = [
    "kod", "sezon", "blok", "poziom", "adnotacja", "percentyl", "presja", "karty_przyjezdne",
    "za_malo_danych", "spp",
]


def _pelna_siatka(agg: pd.DataFrame) -> pd.DataFrame:
    """Każdy kod z agregatów × wszystkie bloki × oba sezony; brakujące komórki bez danych."""
    siatka = pd.MultiIndex.from_product(
        [sorted(agg["kod"].unique()), SEZONY, BLOKI], names=["kod", "sezon", "blok"]
    ).to_frame(index=False)
    out = siatka.merge(agg, on=["kod", "sezon", "blok"], how="left")
    # Flaga SPP jest cechą kodu, nie komórki: uzupełniamy ją z pozostałych wierszy kodu.
    spp_kodu = agg.groupby("kod")["spp"].agg(lambda s: s.dropna().iloc[0] if s.notna().any() else None)
    out["spp"] = out["kod"].map(spp_kodu)
    return out


def tabela_p(agg_strefy: pd.DataFrame) -> pd.DataFrame:
    """agg_strefy (kod × blok × sezon) → tabela P.

    Zwraca po jednym wierszu na kod × sezon × blok (pełna siatka) z kolumnami `KOLUMNY_TABELI_P`:
    `poziom` P1–P4 z progów `PROGI_PRESJI`, `adnotacja` („za mało danych” albo ""),
    `percentyl` 0–100 w mieście i sezonie (informacyjnie; NaN bez danych).
    """
    df = _pelna_siatka(agg_strefy)
    malo = (
        df["za_malo_danych"].fillna(True).astype(bool)
        | df["presja"].isna()
        | ~(df["karty_przyjezdne"] >= MIN_KART)
    )
    df["za_malo_danych"] = malo

    ok = df[~malo]
    ranga = ok.groupby("sezon")["presja"].rank(method="min")
    n = ok.groupby("sezon")["presja"].transform("size")
    klasa = sum((ok["presja"] > p).astype(int) for p in PROGI_PRESJI)

    df["percentyl"] = (100 * ranga / n).reindex(df.index)
    df["poziom"] = pd.Series(np.array(POZIOMY)[klasa.to_numpy()], index=ok.index).reindex(df.index).fillna("P1")
    df["adnotacja"] = np.where(malo, ZA_MALO_DANYCH, "")
    df.loc[malo, ["presja", "karty_przyjezdne"]] = np.nan

    df["sezon"] = pd.Categorical(df["sezon"], SEZONY, ordered=True)
    df["blok"] = pd.Categorical(df["blok"], BLOKI, ordered=True)
    df = df.sort_values(["sezon", "blok", "kod"]).reset_index(drop=True)
    df["sezon"] = df["sezon"].astype(str)
    df["blok"] = df["blok"].astype(str)
    return df[KOLUMNY_TABELI_P]


def harmonogram(tabela: pd.DataFrame, sezon: str) -> pd.DataFrame:
    """Tabela P jednego sezonu jako harmonogram kod × blok (format załącznika do uchwały)."""
    sel = tabela[tabela["sezon"] == sezon]
    return sel.pivot(index="kod", columns="blok", values="poziom").reindex(columns=list(BLOKI))


def czasy_wizyt(agg_grupy: pd.DataFrame, sezon: str, blok: str) -> pd.DataFrame:
    """Mediana czasu wizyty [min] jednego sezonu i bloku jako tabela kod × grupa usług.

    Pusta komórka = grupa poniżej progu 30 kart (pipeline jej nie eksportuje) albo brak wizyt.
    """
    sel = agg_grupy[(agg_grupy["sezon"] == sezon) & (agg_grupy["blok"] == blok)]
    out = sel.pivot(index="kod", columns="grupa", values="mediana_czasu_wizyty_min")
    out.columns.name = None
    return out.sort_index()
