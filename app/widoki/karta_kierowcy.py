"""Widok: karta kierowcy — poziom strefy teraz, taryfa, do kiedy obowiązuje, koszt kolejnych godzin."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from app.kontekst import ETYKIETY_SEZONOW, KOLORY_POZIOMOW, Kontekst, etykieta_spp
from parkflow.taryfa import POLITYKA, karta_kierowcy

TYTUL = "Karta kierowcy"
GODZINY = 3
ETYKIETY_GRUP = {
    "szybkie_uslugi": "szybkie usługi", "spozywcze_male": "spożywcze małe", "handel": "handel",
    "gastronomia": "gastronomia", "uslugi_osobiste": "usługi osobiste", "rozrywka_kultura": "rozrywka / kultura",
}


def _kody(ctx: Kontekst) -> list[str]:
    """Kody z danymi najpierw (wg presji w wybranym bloku), potem pozostałe alfabetycznie."""
    k = ctx.komorki.sort_values(["za_malo_danych", "presja", "kod"], ascending=[True, False, True])
    return list(k["kod"])


def render(ctx: Kontekst) -> None:
    st.subheader(f"Karta kierowcy · {ETYKIETY_SEZONOW[ctx.sezon]}")
    teraz = datetime.now(ZoneInfo("Europe/Warsaw")).replace(tzinfo=None, second=0, microsecond=0)

    c1, c2, c3 = st.columns([2, 1, 1])
    kod = c1.selectbox("Strefa (kod pocztowy)", _kody(ctx), key="karta_kod")
    dzien = c2.date_input("Dzień", teraz.date(), key="karta_dzien")
    godzina = c3.time_input("Godzina", teraz.time(), step=900, key="karta_godzina")
    ulga = st.toggle("Jestem mieszkańcem (ulga ×0,85)", key="karta_ulga")

    k = karta_kierowcy(ctx.tabela, ctx.agregaty.grupy, kod, ctx.sezon, datetime.combine(dzien, godzina))
    if k.bezplatne:
        st.success(f"**{k.kod}** · {k.komunikat}")
        return
    if k.adnotacja:
        st.info("Za mało danych w wybranym sezonie i godzinie — brak rekomendowanej taryfy.")
        return

    rgb = KOLORY_POZIOMOW[k.poziom]
    st.markdown(
        f"<div style='border-left:8px solid rgb{rgb};padding:0.6em 1em;background:rgba{(*rgb, 0.12)};"
        f"font-size:1.15em'>{k.komunikat_ulga if ulga else k.komunikat}</div>",
        unsafe_allow_html=True,
    )

    t = k.taryfa_ulga if ulga else k.taryfa
    m = st.columns(4)
    m[0].metric("Poziom", k.poziom)
    m[1].metric("Obowiązuje do", k.do_godziny)
    m[2].metric("Okres preferencyjny", f"{t.okres_pref_min} min",
                delta=f"{k.przesuniecie_min:+d} min" if k.przesuniecie_min else None, delta_color="off")
    m[3].metric("Dominująca grupa usług", ETYKIETY_GRUP.get(k.grupa, "—"))

    koszty = pd.DataFrame({
        "Godzina postoju": [f"{i + 1}." for i in range(GODZINY)],
        "Bez ulgi [zł]": k.koszty_godzin(GODZINY),
        "Z ulgą mieszkańca [zł]": k.koszty_godzin(GODZINY, ulga=True),
    })
    koszty.loc[len(koszty)] = ["Razem", *koszty.iloc[:, 1:].sum().round(2)]
    st.dataframe(koszty.style.format({c: "{:.2f}" for c in koszty.columns[1:]}), hide_index=True)

    obszar = ctx.tabela.loc[ctx.tabela["kod"] == kod, "spp"].iloc[0]
    st.caption(
        f"Obszar: {etykieta_spp(obszar)}. Stawka blokowana na starcie postoju. "
        f"S = {POLITYKA.stawka_bazowa:.2f} zł; okres preferencyjny −15 min przy dominacji szybkich usług, "
        "+15 min przy usługach osobistych i rozrywce (dominująca = największa presja w bloku). "
        "Sezon z paska bocznego; święta nie są uwzględniane."
    )
