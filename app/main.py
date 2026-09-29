"""ParkFlow — aplikacja demo. Uruchomienie z katalogu repo: `streamlit run app/main.py`.

Pasek boczny: sezon, blok. Widoki (zakładki) z listy WIDOKI dostają `Kontekst`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from app.kontekst import ETYKIETY_BLOKOW, ETYKIETY_SEZONOW, Kontekst  # noqa: E402
from app.oprawa import naglowek, panel_boczny  # noqa: E402
from app.widoki import karta_kierowcy as widok_karta_kierowcy  # noqa: E402
from app.widoki import mapa as widok_mapa  # noqa: E402
from app.widoki import wyliczenia as widok_wyliczenia  # noqa: E402
from app.widoki import grupy_intensywnosci as widok_grupy  # noqa: E402
from app.widoki import rekomendacje as widok_rekomendacje  # noqa: E402
from parkflow.dane import KATALOG_AGG, wczytaj_agregaty  # noqa: E402
from parkflow.model import BLOKI, SEZONY, tabela_p  # noqa: E402

# Kolejne tickety dopisują tu swoje widoki (mapa, karta kierowcy, panel miasta).
WIDOKI = [widok_mapa, widok_wyliczenia, widok_karta_kierowcy, widok_rekomendacje, widok_grupy]


@st.cache_data
def _model(katalog: str):
    agregaty = wczytaj_agregaty(katalog)
    return agregaty, tabela_p(agregaty.strefy)


def main() -> None:
    st.set_page_config(page_title="ParkFlow", layout="wide")
    naglowek()

    with st.sidebar:
        panel_boczny()
        if not (KATALOG_AGG / "agg_strefy.parquet").exists():
            st.error("Brak agregatów w data/agg. Przygotuj dane z pipeline'u, aby uruchomić aplikację.")
            st.stop()
        sezon = st.radio("Sezon", SEZONY, format_func=ETYKIETY_SEZONOW.get)
        blok = st.select_slider("Przedział godzinowy (pn–pt)", BLOKI, value=BLOKI[1], format_func=ETYKIETY_BLOKOW.get)

    agregaty, tabela = _model(str(KATALOG_AGG))
    ctx = Kontekst(agregaty=agregaty, tabela=tabela, sezon=sezon, blok=blok)

    for zakladka, widok in zip(st.tabs([w.TYTUL for w in WIDOKI]), WIDOKI):
        with zakladka:
            widok.render(ctx)


main()
