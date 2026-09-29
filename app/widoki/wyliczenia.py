"""Rekomendowana taryfa i jej wyliczenie dla obszaru widocznego na mapie."""

import pandas as pd
import streamlit as st

from app.kontekst import ETYKIETY_BLOKOW, ETYKIETY_SEZONOW, NAZWY_USLUG, Kontekst
from parkflow.dane import kody_wylaczone
from parkflow.mapa import POZIOM, stan_kodow
from parkflow.taryfa import POLITYKA, dominujaca_grupa, przesuniecie_okresu

TYTUL = "Wyliczenia taryf"


def taryfa_sektora(ctx: Kontekst, kod: str, poziom: str):
    grupa = dominujaca_grupa(ctx.agregaty.grupy, kod, ctx.sezon, ctx.blok)
    return grupa, POLITYKA.taryfa(poziom, przesuniecie_min=przesuniecie_okresu(grupa))


def render(ctx: Kontekst) -> None:
    st.subheader("Ile zapłacisz za parkowanie?")
    st.caption(
        f"{ETYKIETY_SEZONOW[ctx.sezon]} · pn–pt {ETYKIETY_BLOKOW[ctx.blok]}. "
        "Propozycja modelu, nie obowiązujący cennik SPP. Kwoty bez ulgi mieszkańca."
    )
    st.caption("Lista obejmuje tylko sektory z wyliczoną presją i co najmniej 30 kartami przyjezdnymi, bez flagi „za mało danych”.")
    komorki = ctx.komorki
    kody = komorki.loc[komorki["spp"].eq(True), "kod"]
    stan = stan_kodow(kody, komorki, kody_wylaczone(ctx.agregaty.katalog)).set_index("kod")
    dostepne = stan.loc[stan["stan"] == POZIOM]
    if dostepne.empty:
        st.info("Brak sektorów SPP z wystarczającymi danymi w wybranym sezonie i bloku.")
        return
    kod = st.selectbox("Sektor (kod pocztowy)", sorted(dostepne.index), key="wyliczenia_kod")
    s = dostepne.loc[kod]
    grupa, taryfa = taryfa_sektora(ctx, kod, s["poziom"])
    st.subheader(f"Sektor {kod}")

    def kwota(wartosc: float) -> str:
        return f"{wartosc:.2f}".replace(".", ",") + " zł"

    etapy = [(f"Pierwsze {taryfa.okres_pref_min} min",
              kwota(taryfa.cena_pref) + (" łącznie" if taryfa.ryczalt else "/godz."))]
    if taryfa.okres_pref_min < taryfa.prog_min:
        etapy.append((f"Po {taryfa.okres_pref_min} min do {taryfa.prog_min} min",
                      kwota(taryfa.stawka_potem) + "/godz."))
    etapy.append((f"Po {max(taryfa.okres_pref_min, taryfa.prog_min)} min",
                  kwota(taryfa.stawka_po_2h) + "/godz."))
    for kolumna, (okres, cena) in zip(st.columns(len(etapy)), etapy):
        kolumna.metric(okres, cena)
    if taryfa.ryczalt:
        st.caption(f"Za postój do {taryfa.okres_pref_min} min płacisz stałe {kwota(taryfa.cena_pref)}, "
                   "także gdy parkujesz krócej. Dalsze opłaty naliczamy za każdą minutę.")
    else:
        st.caption("Opłaty naliczamy za każdą minutę według stawki obowiązującej w danej części postoju.")

    st.markdown("**Łączny koszt całego postoju**")
    czasy = sorted({30, 60, 120, 180, taryfa.okres_pref_min})
    podsumowanie = pd.DataFrame({
        "Czas postoju": [f"{m} min" for m in czasy],
        "Do zapłaty": [kwota(taryfa.koszt(m)) for m in czasy],
    })
    st.dataframe(podsumowanie, hide_index=True, width="stretch")
    st.caption("Kwoty obejmują cały postój od momentu przyjazdu. Taryfa wybrana na początku pozostaje przez cały postój.")

    with st.expander("Skąd te stawki? Dane i szczegółowe wyliczenia"):
        komorka = ctx.komorki.set_index("kod").loc[kod]
        st.write(
            f"Presja: **{komorka['presja']:.3f} samochodo-h**; "
            f"karty przyjezdne: **{int(komorka['karty_przyjezdne'])}**. "
            f"Percentyl presji: **{s['percentyl']:.2f} → {s['poziom']}**."
        )
        st.caption(
            "Ranking obejmuje kody i wszystkie bloki godzinowe w wybranym sezonie. "
            "P1: do 40; P2: powyżej 40 do 70; P3: powyżej 70 do 90; P4: powyżej 90."
        )
        przes = przesuniecie_okresu(grupa)
        mnozniki = POLITYKA.mnozniki[s["poziom"]]
        st.write(
            f"Dominująca grupa według presji: **{NAZWY_USLUG.get(grupa, 'brak danych')}**. "
            f"Okres preferencyjny: {mnozniki.okres_pref_min} min + ({przes}) min "
            f"= **{taryfa.okres_pref_min} min**."
        )
        jednostka = "zł za cały okres (ryczałt)" if taryfa.ryczalt else "zł/h"
        st.write(
            f"Stawka bazowa S = {POLITYKA.stawka_bazowa:.2f} zł. "
            f"Cena preferencyjna: {mnozniki.cena_pref:g} × S = {taryfa.cena_pref:.2f} {jednostka}."
        )
        if taryfa.okres_pref_min < taryfa.prog_min:
            st.write(f"Następnie, do 2 h: {mnozniki.potem:g} × S = {taryfa.stawka_potem:.2f} zł/h.")
        st.write(
            f"Po {max(taryfa.okres_pref_min, taryfa.prog_min)} min: "
            f"{mnozniki.po_2h:g} × S = {taryfa.stawka_po_2h:.2f} zł/h."
        )
        wiersze = []
        for minuty in (60, 120, 180):
            pref = min(minuty, taryfa.okres_pref_min)
            potem = max(0, min(minuty, taryfa.prog_min) - taryfa.okres_pref_min)
            po = max(0, minuty - max(taryfa.okres_pref_min, taryfa.prog_min))
            skladniki = [f"{taryfa.cena_pref:.2f} zł ryczałtu" if taryfa.ryczalt
                         else f"{pref}/60 × {taryfa.cena_pref:.2f}"]
            if potem:
                skladniki.append(f"{potem}/60 × {taryfa.stawka_potem:.2f}")
            if po:
                skladniki.append(f"{po}/60 × {taryfa.stawka_po_2h:.2f}")
            wiersze.append({"Postój": f"{minuty // 60} h", "Wyliczenie [zł]": " + ".join(skladniki),
                            "Łączny koszt [zł]": round(taryfa.koszt(minuty), 2)})
        st.dataframe(pd.DataFrame(wiersze).style.format({"Łączny koszt [zł]": "{:.2f}"}), hide_index=True)
        st.caption("Stawki z wybranego bloku są zachowane przez cały postój. Ryczałt jest należny także za krótszy postój.")
