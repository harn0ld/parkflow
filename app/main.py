"""ParkFlow — aplikacja demo. Uruchomienie z katalogu repo: `streamlit run app/main.py`.

Pasek boczny: miasto, sezon, blok. Widoki (zakładki) z listy WIDOKI dostają `Kontekst`.
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
from parkflow.dane import KATALOG_AGG, KATALOG_SAMPLE, wczytaj_agregaty  # noqa: E402
from parkflow.miasta import LODZ, MIASTA  # noqa: E402
from parkflow.model import BLOKI, SEZONY, tabela_p  # noqa: E402

# Kolejne tickety dopisują tu swoje widoki (mapa, karta kierowcy, panel miasta).
WIDOKI = [widok_mapa, widok_wyliczenia, widok_karta_kierowcy, widok_rekomendacje, widok_grupy]


@st.cache_data
def _model(katalog: str):
    agregaty = wczytaj_agregaty(katalog)
    return agregaty, tabela_p(agregaty.strefy)


def _ma_agregaty(katalog) -> bool:
    return (katalog / "agg_strefy.parquet").exists()


def main() -> None:
    st.set_page_config(page_title="ParkFlow", layout="wide")
    # Miasta z policzonymi agregatami; Łódź zawsze (w razie braku data/agg — data/sample).
    miasta = [m for m in MIASTA.values() if m is LODZ or _ma_agregaty(m.katalog_agg)]

    with st.sidebar:
        marka = st.container()  # nad wyborem miasta, choć zależy od niego
        miasto = MIASTA[st.radio("Miasto", [m.id for m in miasta], format_func=lambda i: MIASTA[i].nazwa,
                                 horizontal=True, key="miasto")] if len(miasta) > 1 else LODZ
        with marka:
            panel_boczny(miasto)
        katalog = miasto.katalog_agg
        if miasto is LODZ and not _ma_agregaty(katalog):
            katalog = KATALOG_SAMPLE if _ma_agregaty(KATALOG_SAMPLE) else KATALOG_AGG
        if not _ma_agregaty(katalog):
            st.error(f"Brak agregatów w {katalog.relative_to(KATALOG_AGG.parent.parent)}. "
                     "Przygotuj dane z pipeline'u, aby uruchomić aplikację.")
            st.stop()
        sezon = st.radio("Sezon", SEZONY, format_func=ETYKIETY_SEZONOW.get)
        blok = st.select_slider("Przedział godzinowy (pn–pt)", BLOKI, value=BLOKI[1], format_func=ETYKIETY_BLOKOW.get)
    naglowek(miasto)

    agregaty, tabela = _model(str(katalog))
    ctx = Kontekst(agregaty=agregaty, tabela=tabela, sezon=sezon, blok=blok, miasto=miasto)

    for zakladka, widok in zip(st.tabs([w.TYTUL for w in WIDOKI]), WIDOKI):
        with zakladka:
            widok.render(ctx)


main()
