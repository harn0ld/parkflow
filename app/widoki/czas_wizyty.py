"""Widok: mediana czasu wizyty per kod i grupa usług + kalibracja czasów domyślnych (ticket 05)."""

import pandas as pd
import streamlit as st

from app.kontekst import ETYKIETY_BLOKOW, ETYKIETY_SEZONOW, Kontekst
from parkflow.model import czasy_wizyt

TYTUL = "Czas wizyty"


def render(ctx: Kontekst) -> None:
    st.subheader(f"Mediana czasu wizyty [min] · {ETYKIETY_SEZONOW[ctx.sezon]} · przedział godzinowy {ETYKIETY_BLOKOW[ctx.blok]}")
    t = czasy_wizyt(ctx.agregaty.grupy, ctx.sezon, ctx.blok)
    if t.empty:
        st.info("Brak grup usług z ≥ 30 kartami przyjezdnymi w tym sezonie i bloku.")
    else:
        st.dataframe(t.style.format("{:.0f}", na_rep="—"), width="stretch")
    st.caption(
        "Czas wizyty = czas zmierzony (pierwsza → ostatnia transakcja karty w kodzie, przerwy ≤ 90 min; "
        "po opłacie parkingowej od momentu opłaty) + czas domyślny grupy ostatniej transakcji. "
        "„—” = grupa poniżej 30 unikalnych kart przyjezdnych."
    )

    st.subheader("Kalibracja czasów domyślnych")
    k = ctx.agregaty.kalibracja
    if k is None:
        st.info("Brak agg_kalibracja_czasow w wybranym katalogu — przelicz pipeline.")
        return
    widok = pd.DataFrame({
        "Grupa": k["grupa"],
        "Czas domyślny [min]": k["czas_domyslny_min"],
        "Mediana zmierzonego czasu [min]": k["mediana_czasu_zmierzonego_min"],
        "Wizyty wielotransakcyjne": k["wizyty_wielotransakcyjne"],
        "Udział wizyt wielotransakcyjnych": k["udzial_wielotransakcyjnych"],
        "Karty": k["karty"],
    })
    st.dataframe(
        widok.style.format({"Mediana zmierzonego czasu [min]": "{:.0f}", "Udział wizyt wielotransakcyjnych": "{:.0%}"}),
        hide_index=True, width="stretch",
    )
    st.caption(
        "Wizyty z ≥ 2 transakcjami: czas od pierwszej do ostatniej transakcji (bez startu od opłaty), "
        "grupa = grupa ostatniej transakcji. To dolna granica czasu na miejscu — nie obejmuje pobytu po "
        "ostatniej transakcji. Tylko grupy z ≥ 30 kartami."
    )
