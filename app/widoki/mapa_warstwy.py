"""Warstwy mapy: zmierzony popyt z parkomatów (ticket 07) i parkomaty SPP (ticket 06).

Dane przygotowuje `parkflow.warstwy`; tu tylko kolory, tooltip i pydeck. Rejestracja w `mapa.WARSTWY`.
"""

import pandas as pd
import pydeck as pdk
import streamlit as st

from app.kontekst import Kontekst
from app.ustawienia import KODY_UKRYTE
from parkflow.dane import KODY_ULICE, PARKOMATY, wczytaj_kody_ulice, wczytaj_parkomaty
from parkflow.warstwy import parkomaty_na_mapie, zmierzony_popyt

# Kolory podstref jak na mapie ZDiT (fiolet = A, zielony = B); C (Bałucki Rynek) pomarańczowy.
KOLORY_PODSTREF = {"A": (123, 50, 148), "B": (0, 128, 96), "C": (230, 120, 20)}
KOLOR_POPYTU = (33, 102, 172)


def pola_tooltipa(tytul, wiersze=None, uwaga=""):
    from app.widoki.mapa import pola_tooltipa as f  # import cykliczny: mapa rejestruje te warstwy
    return f(tytul, wiersze, uwaga)


def _liczba(v: float, cyfry: int = 1) -> str:
    return f"{v:,.{cyfry}f}".replace(",", " ").replace(".", ",")


@st.cache_data
def _parkomaty() -> pd.DataFrame:
    p = parkomaty_na_mapie(wczytaj_parkomaty(PARKOMATY))
    return p.loc[~p["kod_pocztowy"].isin(KODY_UKRYTE)].reset_index(drop=True)


@st.cache_data
def _kody_ulice() -> pd.DataFrame:
    return wczytaj_kody_ulice(KODY_ULICE)


def zbuduj_popyt(ctx: Kontekst) -> pdk.Layer | None:
    """Koła na centroidach kodów: opłacone auto-godziny z parkomatów SPP w sezonie i bloku."""
    if ctx.agregaty.popyt is None or not KODY_ULICE.exists():
        return None
    df = zmierzony_popyt(ctx.agregaty.popyt, _kody_ulice(), ctx.sezon, ctx.blok)
    if df.empty:
        return None
    tooltip = [
        pola_tooltipa(
            f"Zmierzony popyt · {r.kod}",
            {"Opłacone auto-godziny / tydzień": _liczba(r.oplacone_autogodziny),
             "Karty płacące w parkomatach": int(r.karty),
             "Ulice": "; ".join(str(r.ulice).split("; ")[:4])},
            "mediana tygodni roboczych sezonu; tylko płatności kartą Visa, więc to dolne oszacowanie",
        )
        for r in df.itertuples()
    ]
    df = pd.concat([df, pd.DataFrame(tooltip)], axis=1)
    return pdk.Layer(
        "ScatterplotLayer", df, id="zmierzony_popyt", get_position="[lon, lat]", get_radius="promien_m",
        radius_min_pixels=4, get_fill_color=[*KOLOR_POPYTU, 110], stroked=True,
        get_line_color=[*KOLOR_POPYTU, 230], line_width_min_pixels=1.5, pickable=True, auto_highlight=True,
    )


def zbuduj_parkomaty(ctx: Kontekst) -> pdk.Layer | None:
    """Punkty parkomatów z lokalizacją, kolor = obecna podstrefa."""
    if not PARKOMATY.exists():
        return None
    df = _parkomaty()
    tooltip = [
        pola_tooltipa(
            f"Parkomat {r.numer}",
            {"Ulica": r.ulica, "Podstrefa": r.podstrefa, "Kod pocztowy": r.kod_pocztowy,
             "Lokalizacja": r.status},
            f"na mapie 2024 podstrefa {r.podstrefa_2024}" if r.podstrefa_2024 and r.podstrefa_2024 != r.podstrefa
            else "",
        )
        for r in df.itertuples()
    ]
    df = pd.concat([df, pd.DataFrame(tooltip)], axis=1)
    df["kolor"] = [[*KOLORY_PODSTREF.get(p, (60, 60, 60)), 230] for p in df["podstrefa"]]
    return pdk.Layer(
        "ScatterplotLayer", df, id="parkomaty", get_position="[lon, lat]", get_radius=12,
        radius_min_pixels=2.5, radius_max_pixels=7, get_fill_color="kolor", stroked=True,
        get_line_color=[255, 255, 255, 220], line_width_min_pixels=0.5, pickable=True,
    )


def opis_popytu(ctx: Kontekst) -> str:
    if ctx.agregaty.popyt is None:
        return "Zmierzony popyt: brak agg_parkomaty_strefy w wybranym źródle danych."
    return ("Niebieskie koła: zmierzony popyt, czyli opłacone auto-godziny w parkomatach SPP (mediana tygodni "
            "roboczych sezonu, kwota / 0,92 przeliczona na minuty wg cennika z dnia opłaty). Pole koła ∝ auto-godzinom; "
            "Większe koło oznacza więcej opłaconego czasu, a nie zasięg parkingu. "
            "Tylko płatności kartą Visa i kody z ≥ 30 kartami płacącymi w bloku.")


def opis_parkomatow(ctx: Kontekst) -> str:
    kropka = "<span style='color:rgb({},{},{})'>●</span>"
    legenda = " ".join(kropka.format(*KOLORY_PODSTREF[p]) + f" {p}" for p in KOLORY_PODSTREF)
    return (f"Parkomaty (podstrefa): {legenda}. Lokalizacje z mapy ZDiT (VI 2024); parkomaty z rozszerzenia 2025 "
            "są w danych Visa, ale bez lokalizacji — nie ma ich na mapie.")
