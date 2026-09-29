"""Ręczna edycja grup intensywności i przypisań przed eksportem CSV."""

import pandas as pd
import streamlit as st

from app.kontekst import ETYKIETY_BLOKOW, ETYKIETY_SEZONOW, Kontekst
from parkflow.dane import kody_wylaczone

TYTUL = "Edycja grup intensywności"


def domyslne_grupy() -> pd.DataFrame:
    return pd.DataFrame([
        {"id": "P1", "nazwa": "Niska intensywność", "opis": "Domyślnie sektory z poziomem P1."},
        {"id": "P2", "nazwa": "Umiarkowana intensywność", "opis": "Domyślnie sektory z poziomem P2."},
        {"id": "P3", "nazwa": "Wysoka intensywność", "opis": "Domyślnie sektory z poziomem P3."},
        {"id": "P4", "nazwa": "Bardzo wysoka intensywność", "opis": "Domyślnie sektory z poziomem P4."},
    ])


def sprawdz_grupy(grupy: pd.DataFrame) -> pd.DataFrame:
    wynik = grupy.copy()
    wynik["nazwa"] = wynik["nazwa"].fillna("").str.strip()
    wynik["opis"] = wynik["opis"].fillna("").str.strip()
    if wynik["nazwa"].eq("").any():
        raise ValueError("Każda grupa musi mieć nazwę.")
    if wynik["nazwa"].str.casefold().duplicated().any():
        raise ValueError("Nazwy grup muszą być różne.")
    return wynik


def sektory_do_edycji(ctx: Kontekst) -> pd.DataFrame:
    k = ctx.komorki
    wykluczone = kody_wylaczone(ctx.agregaty.katalog)
    return k.loc[
        k["spp"].eq(True) & ~k["za_malo_danych"] & k["presja"].notna()
        & k["karty_przyjezdne"].ge(30) & ~k["kod"].isin(wykluczone),
        ["kod", "sezon", "blok", "poziom", "presja", "percentyl", "karty_przyjezdne"],
    ].sort_values("kod").reset_index(drop=True)


def przygotuj_eksport(sektory: pd.DataFrame, przypisania: dict[str, str], grupy: pd.DataFrame) -> pd.DataFrame:
    wynik = sektory.rename(columns={"poziom": "poziom_modelu"}).copy()
    wynik["grupa_id"] = wynik["kod"].map(przypisania).fillna(wynik["poziom_modelu"])
    if not wynik["grupa_id"].isin(grupy["id"]).all():
        raise ValueError("Przypisanie wskazuje nieistniejącą grupę.")
    wynik["zmienione_recznie"] = wynik["grupa_id"].ne(wynik["poziom_modelu"])
    return wynik.merge(
        grupy.rename(columns={"id": "grupa_id", "nazwa": "grupa_nazwa", "opis": "grupa_opis"}),
        on="grupa_id", how="left", validate="many_to_one",
    )


def render(ctx: Kontekst) -> None:
    st.subheader("Grupy intensywności — edycja przed eksportem")
    st.caption(
        "Zmień grupy i przypisania sektorów, a następnie pobierz CSV. "
        "Zmiany obowiązują w tej sesji i nie zmieniają taryf ani wyników modelu na mapie. "
        "Przed pobraniem pliku zatwierdź edycję przyciskiem pod tabelą."
    )
    if "intensywnosc_grupy" not in st.session_state:
        st.session_state.intensywnosc_grupy = domyslne_grupy()
        st.session_state.intensywnosc_przypisania = {}
        st.session_state.intensywnosc_wersja = 0
    grupy = st.session_state.intensywnosc_grupy
    wersja = st.session_state.intensywnosc_wersja

    st.markdown("**1. Nazwy i opisy grup**")
    with st.form(f"intensywnosc_grupy_form_{wersja}"):
        edycja = st.data_editor(
            grupy, hide_index=True, width="stretch", disabled=["id"],
            column_config={"id": "ID", "nazwa": "Nazwa grupy", "opis": "Opis"},
            key=f"intensywnosc_grupy_editor_{wersja}",
        )
        if st.form_submit_button("Zapisz nazwy i opisy"):
            try:
                st.session_state.intensywnosc_grupy = sprawdz_grupy(edycja)
            except ValueError as e:
                st.error(str(e))
            else:
                st.session_state.intensywnosc_wersja += 1
                st.rerun()

    with st.expander("Dodaj własną grupę"):
        with st.form("intensywnosc_nowa", clear_on_submit=True):
            nazwa = st.text_input("Nazwa nowej grupy", max_chars=80)
            opis = st.text_input("Opis nowej grupy", max_chars=300)
            if st.form_submit_button("Dodaj grupę"):
                identyfikator = f"G{len(grupy) - 3}"
                nowe = pd.concat([grupy, pd.DataFrame([
                    {"id": identyfikator, "nazwa": nazwa, "opis": opis},
                ])], ignore_index=True)
                try:
                    st.session_state.intensywnosc_grupy = sprawdz_grupy(nowe)
                except ValueError as e:
                    st.error(str(e))
                else:
                    st.session_state.intensywnosc_wersja += 1
                    st.rerun()

    st.markdown("**2. Przypisania sektorów**")
    st.caption(
        f"{ETYKIETY_SEZONOW[ctx.sezon]} · {ETYKIETY_BLOKOW[ctx.blok]}. "
        "Tylko sektory SPP z wystarczającymi danymi. "
        "Przypisania zapisujemy osobno dla każdego sezonu i bloku godzinowego."
    )
    sektory = sektory_do_edycji(ctx)
    zakres = (ctx.sezon, ctx.blok)
    przypisania = st.session_state.intensywnosc_przypisania.get(zakres, {})
    etykiety = {r.id: f"{r.id} · {r.nazwa}" for r in grupy.itertuples()}
    if sektory.empty:
        st.info("Brak sektorów z wystarczającymi danymi w tym sezonie i bloku.")
    else:
        widok = sektory[["kod", "poziom", "karty_przyjezdne"]].copy()
        widok["grupa"] = widok["kod"].map(przypisania).fillna(widok["poziom"]).map(etykiety)
        klucz = f"intensywnosc_sektory_{ctx.sezon}_{ctx.blok}_{wersja}"
        with st.form(klucz):
            edycja = st.data_editor(
                widok, hide_index=True, width="stretch",
                disabled=["kod", "poziom", "karty_przyjezdne"],
                column_config={
                    "kod": "Sektor", "poziom": "Poziom modelu", "karty_przyjezdne": "Karty przyjezdne",
                    "grupa": st.column_config.SelectboxColumn(
                        "Przypisana grupa", options=list(etykiety.values()), required=True,
                    ),
                }, key=f"{klucz}_editor",
            )
            if st.form_submit_button("Zapisz przypisania"):
                odwrotne = {nazwa: id for id, nazwa in etykiety.items()}
                if not edycja["grupa"].isin(odwrotne).all():
                    st.error("Wybierz istniejącą grupę dla każdego sektora.")
                else:
                    st.session_state.intensywnosc_przypisania[zakres] = dict(
                        zip(edycja["kod"], edycja["grupa"].map(odwrotne))
                    )
                    st.session_state.intensywnosc_wersja += 1
                    st.rerun()

        st.markdown("**3. Podgląd zatwierdzonych przypisań i eksport**")
        eksport = przygotuj_eksport(sektory, przypisania, grupy)
        st.caption(
            f"{len(eksport)} sektorów · {int(eksport['zmienione_recznie'].sum())} przypisań innych niż wynik modelu. "
            "Eksport obejmuje aktualny sezon i blok godzinowy, wraz z nazwami i opisami grup."
        )
        st.dataframe(eksport[["kod", "poziom_modelu", "grupa_id", "grupa_nazwa", "zmienione_recznie"]],
                     hide_index=True, width="stretch")
        st.download_button(
            "Pobierz przypisania CSV", eksport.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"przypisania_{ctx.sezon}_{ctx.blok}.csv", mime="text/csv",
        )
    st.download_button(
        "Pobierz katalog grup CSV", grupy.to_csv(index=False).encode("utf-8-sig"),
        file_name="grupy_intensywnosci.csv", mime="text/csv",
    )
