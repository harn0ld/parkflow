"""Ręczna edycja grup intensywności i przypisań przed eksportem CSV."""

import pandas as pd
import streamlit as st

from app.kontekst import ETYKIETY_BLOKOW, ETYKIETY_SEZONOW, NAZWY_USLUG, Kontekst
from parkflow.dane import kody_wylaczone
from parkflow.model import POZIOMY
from parkflow.taryfa import POLITYKA, tabela_stawek

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


# Podgląd pokazuje cenę kolejnych godzin (widać, że pierwsza jest najtańsza); CSV ma pełny zestaw
# kolumn z parkflow.taryfa.KOLUMNY_STAWEK.
ETYKIETY_GODZIN = {"godzina_1_zl": "1. godzina [zł]", "godzina_2_zl": "2. godzina [zł]",
                   "godzina_3_zl": "3. godzina [zł]", "koszt_3h_zl": "Razem 3 h [zł]"}


def _zl(v: float) -> str:
    return f"{v:.2f}".replace(".", ",") + " zł"


def stawki_poziomow() -> pd.DataFrame:
    """Proponowane stawki P1–P4 bez przesunięcia okresu: początek postoju i cena kolejnych godzin."""
    wiersze = []
    for poziom in POZIOMY:
        t = POLITYKA.taryfa(poziom)
        koszt = [t.koszt(60 * h) for h in range(4)]
        wiersze.append({"Poziom": poziom, "Początek postoju": opis_startu(t.okres_pref_min, t.cena_pref, t.ryczalt),
                        **{f"{h}. godzina [zł]": round(koszt[h] - koszt[h - 1], 2) for h in (1, 2, 3)},
                        "Razem 3 h [zł]": round(koszt[3], 2)})
    return pd.DataFrame(wiersze)


def opis_startu(okres_min: int, cena: float, ryczalt: bool) -> str:
    """Okres preferencyjny słowami: opłata stała (ryczałt) albo stawka godzinowa."""
    if ryczalt:
        return f"{_zl(cena)} za pierwsze {okres_min} min (opłata stała)"
    return f"{_zl(cena)}/h przez pierwsze {okres_min} min"


def sektory_do_edycji(ctx: Kontekst) -> pd.DataFrame:
    """Sektory SPP z danymi w sezonie i bloku + taryfa wyliczona przez model dla poziomu modelu."""
    k = ctx.komorki
    wykluczone = kody_wylaczone(ctx.agregaty.katalog)
    sektory = k.loc[
        k["spp"].eq(True) & ~k["za_malo_danych"] & k["presja"].notna()
        & k["karty_przyjezdne"].ge(30) & ~k["kod"].isin(wykluczone),
        ["kod", "sezon", "blok", "poziom", "presja", "percentyl", "karty_przyjezdne"],
    ].sort_values("kod").reset_index(drop=True)
    return sektory.join(tabela_stawek(sektory, ctx.agregaty.grupy, ctx.sezon, ctx.blok))


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
        "Podgląd i CSV zawierają stawki wyliczone przez model dla poziomu modelu (bez ulgi mieszkańca). "
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

        st.markdown("**3. Proponowane stawki i eksport**")
        st.dataframe(stawki_poziomow(), hide_index=True, width="content",
                     column_config={f"{h}. godzina [zł]": st.column_config.NumberColumn(format="%.2f")
                                    for h in (1, 2, 3)} | {"Razem 3 h [zł]": st.column_config.NumberColumn(format="%.2f")})
        eksport = przygotuj_eksport(sektory, przypisania, grupy)
        st.caption(
            f"{len(eksport)} sektorów · {int(eksport['zmienione_recznie'].sum())} przypisań innych niż wynik modelu. "
            "Eksport obejmuje aktualny sezon i blok godzinowy, wraz z nazwami i opisami grup "
            "oraz proponowanymi stawkami. Stawki wynikają z poziomu modelu, nie z ręcznie przypisanej grupy."
        )
        podglad = eksport[["kod", "poziom_modelu", "grupa_nazwa", "zmienione_recznie", *ETYKIETY_GODZIN]].copy()
        podglad.insert(4, "start", [opis_startu(o, c, r) for o, c, r in
                                    zip(eksport["okres_pref_min"], eksport["cena_pref_zl"], eksport["ryczalt"])])
        podglad["dominujaca_grupa"] = eksport["dominujaca_grupa"].map(NAZWY_USLUG).fillna("brak danych")
        st.dataframe(
            podglad.rename(columns=ETYKIETY_GODZIN), hide_index=True, width="stretch",
            column_config={
                "kod": "Sektor", "poziom_modelu": "Poziom modelu", "grupa_nazwa": "Przypisana grupa",
                "zmienione_recznie": "Zmienione ręcznie", "start": "Początek postoju (okres preferencyjny)",
                "dominujaca_grupa": "Dominująca grupa usług",
                **{e: st.column_config.NumberColumn(format="%.2f") for e in ETYKIETY_GODZIN.values()},
            },
        )
        st.caption(
            "Wszystkie stawki to propozycja modelu, a nie obowiązujący cennik. Początek postoju jest tańszy, "
            "żeby zachęcić do krótkich wizyt, a kolejne godziny drożeją, żeby zwalniać miejsca. "
            "Opłata stała (ryczałt, P3 i P4) to jedna kwota za cały okres preferencyjny, np. 1,80 zł za pierwsze 30 min, "
            "płacona także przy krótszym postoju; po nim płaci się za każdą minutę. Okres preferencyjny jest "
            "dłuższy lub krótszy o 15 min zależnie od dominującej grupy usług w sektorze. Kwoty bez ulgi mieszkańca. "
            "Okres preferencyjny trwa najwyżej godzinę. "
            "CSV zawiera dodatkowo: długość okresu preferencyjnego, stawki godzinowe do 2 h i po 2 h "
            "oraz koszt 1, 2 i 3 h łącznie."
        )
        st.download_button(
            "Pobierz przypisania CSV", eksport.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"przypisania_{ctx.sezon}_{ctx.blok}.csv", mime="text/csv",
        )
    st.download_button(
        "Pobierz katalog grup CSV", grupy.to_csv(index=False).encode("utf-8-sig"),
        file_name="grupy_intensywnosci.csv", mime="text/csv",
    )
