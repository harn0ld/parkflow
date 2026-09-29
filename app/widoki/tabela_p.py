"""Widok: tabela poziomów P dla wybranego bloku i sezonu + harmonogram sezonu."""

import pandas as pd
import streamlit as st

from app.kontekst import ETYKIETY_BLOKOW, ETYKIETY_SEZONOW, KOLORY_POZIOMOW, Kontekst, etykieta_spp
from parkflow.model import POZIOMY, harmonogram

TYTUL = "Tabela P"


def _kolor(v) -> str:
    rgb = KOLORY_POZIOMOW.get(v)
    return f"background-color: rgba{(*rgb, 0.35)}" if rgb else ""


def render(ctx: Kontekst) -> None:
    komorki = ctx.komorki
    st.subheader(f"Poziomy P · {ETYKIETY_SEZONOW[ctx.sezon]} · przedział godzinowy {ETYKIETY_BLOKOW[ctx.blok]}")

    kolumny = st.columns(len(POZIOMY) + 1)
    for kol, p in zip(kolumny, POZIOMY):
        kol.metric(p, int(((komorki["poziom"] == p) & ~komorki["za_malo_danych"]).sum()))
    kolumny[-1].metric("Za mało danych (P1)", int(komorki["za_malo_danych"].sum()))

    ukryj = st.toggle("Ukryj komórki z za małą liczbą danych", value=True)
    widok = komorki[~komorki["za_malo_danych"]] if ukryj else komorki
    widok = pd.DataFrame({
        "Kod": widok["kod"],
        "Poziom": widok["poziom"],
        "Obszar": widok["spp"].map(etykieta_spp),
        "Presja [samochodo-h]": widok["presja"],
        "Percentyl": widok["percentyl"],
        "Karty przyjezdne": widok["karty_przyjezdne"],
        "Uwagi": widok["adnotacja"],
    }).sort_values("Presja [samochodo-h]", ascending=False, na_position="last")
    st.dataframe(
        widok.style.map(_kolor, subset=["Poziom"]).format(
            {"Presja [samochodo-h]": "{:.3f}", "Percentyl": "{:.0f}", "Karty przyjezdne": "{:.0f}"}, na_rep="—"
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        f"Poziom = percentyl presji wśród wszystkich komórek kod × blok w {ctx.miasto.miejscownik} w danym sezonie: "
        "P1 ≤ 40 < P2 ≤ 70 < P3 ≤ 90 < P4. Komórki poniżej 30 unikalnych kart przyjezdnych "
        "dostają P1 z adnotacją „za mało danych”."
    )

    with st.expander(f"Harmonogram sezonu (kod × blok) — {ETYKIETY_SEZONOW[ctx.sezon]}"):
        h = harmonogram(ctx.tabela, ctx.sezon).rename(columns=ETYKIETY_BLOKOW)
        st.dataframe(h.style.map(_kolor), width="stretch")
        st.download_button(
            "Pobierz CSV", h.to_csv().encode("utf-8"), file_name=f"harmonogram_P_{ctx.sezon}.csv", mime="text/csv"
        )
