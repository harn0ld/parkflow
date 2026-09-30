"""Czytelne uzasadnienia kandydatów do zmian w organizacji parkowania."""

import streamlit as st

from app.kontekst import ETYKIETY_BLOKOW, ETYKIETY_SEZONOW, NAZWY_USLUG, Kontekst
from app.ustawienia import KODY_UKRYTE
from parkflow.dane import kody_wylaczone, wczytaj_kody_ulice
from parkflow.rekomendacje import rekomendacje

TYTUL = "Rekomendacje parkingowe"


def render(ctx: Kontekst) -> None:
    st.subheader("Gdzie warto poprawić dostępność parkowania?")
    st.caption(f"{ETYKIETY_SEZONOW[ctx.sezon]} · {ETYKIETY_BLOKOW[ctx.blok]}")
    st.info(
        "To lista sektorów do sprawdzenia w terenie. Dane Visa pokazują aktywność i modelową presję, "
        "ale nie liczbę ani zajętość miejsc. Nie wyliczamy, ile miejsc brakuje."
    )
    wynik = rekomendacje(
        ctx.tabela, ctx.agregaty.grupy, ctx.sezon, ctx.blok,
        set(kody_wylaczone(ctx.agregaty.katalog)) | KODY_UKRYTE,
    )
    if wynik.empty:
        st.info("Brak sektorów P3/P4 z wystarczającymi danymi w wybranym sezonie i godzinach.")
        return
    if ctx.miasto.kody_ulice.exists():
        ulice = wczytaj_kody_ulice(ctx.miasto.kody_ulice).set_index("kod")["ulice"]
        wynik["ulice"] = wynik["kod"].map(ulice).fillna("")
    else:
        wynik["ulice"] = ""
    st.caption(
        "Najpierw sektory z wysoką presją w większej liczbie bloków godzinowych, "
        "potem z wyższą presją w aktualnie wybranym bloku. "
        "Lista uwzględnia tylko SPP i sektory z wystarczającymi danymi."
    )
    st.dataframe(wynik[["kod", "poziom", "bloki_z_danymi", "dzialanie"]].rename(columns={
        "kod": "Sektor", "poziom": "Poziom", "bloki_z_danymi": "Bloki z danymi", "dzialanie": "Co sprawdzić",
    }), hide_index=True, width="stretch")
    kod = st.selectbox("Zobacz rekomendację dla sektora", list(wynik["kod"]), key="rekomendacja_kod")
    r = wynik.set_index("kod").loc[kod]
    st.subheader(f"{kod} · {r['dzialanie']}")
    if r["ulice"]:
        st.write(f"**Ulice w sektorze:** {r['ulice']}")
    st.write(
        f"**Dlaczego ten sektor?** Poziom {r['poziom']} przy presji {r['presja']:.3f} samochodo-h "
        f"(próg P3 to 0,15, P4 to 0,30). Wysoka presja występuje w {r['bloki_wysokiej_presji']} "
        f"z {r['bloki_z_danymi']} bloków z wystarczającymi danymi (łącznie są 4 bloki). "
        f"W wybranym bloku odnotowano {int(r['karty_przyjezdne'])} kart przyjezdnych."
    )
    st.write(f"**Dominująca grupa usług:** {NAZWY_USLUG.get(r['grupa'], 'brak danych grupowych')}.")
    st.markdown("**Proponowane następne kroki**")
    st.write("1. Policz dostępne miejsca i zmierz ich zajętość oraz czas postoju w wskazanych godzinach.")
    if r["bloki_wysokiej_presji"] >= 2:
        st.write(
            "2. Jeśli pomiary potwierdzą utrzymujący się brak miejsc, sprawdź możliwość udostępnienia "
            "istniejących parkingów lub dodania miejsc. Zweryfikuj dostępną przestrzeń, "
            "bezpieczeństwo pieszych, dostawy i dostępność."
        )
    else:
        st.write("2. Sprawdź, czy problem skupia się w wybranych godzinach i czy pomoże zmiana organizacji postoju.")
    st.write(f"3. {r['dodatkowo']}")
    with st.expander("Jak powstaje rekomendacja?"):
        st.write(
            "To prosta reguła do ustalania kolejności analiz: P3/P4 w wybranym bloku kwalifikuje sektor. "
            "P3/P4 w co najmniej dwóch blokach tego sezonu wskazuje kandydata do sprawdzenia dodatkowych miejsc. "
            "Przy jednym bloku proponujemy analizę organizacji w godzinach szczytu. "
            "Brak danych w pozostałych blokach nie oznacza niskiej presji. "
            "Presja to szacunek samochodo-godzin z kart Visa, a nie pomiar zajętości parkingu. "
            "Ręczne grupy intensywności nie zmieniają tej rekomendacji."
        )
    st.download_button(
        "Pobierz rekomendacje CSV", wynik.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"rekomendacje_{ctx.sezon}_{ctx.blok}.csv", mime="text/csv",
    )
