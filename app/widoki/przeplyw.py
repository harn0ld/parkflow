"""Mapa: odtwarzanie dnia pn–pt 7→19 po czterech blokach (suwak + „play”).

Komponent deck.gl w HTML (app/assets/przeplyw.html): kolor i wysokość sektora przechodzą płynnie
między środkami bloków, więc zmiana presji w ciągu dnia wygląda jak przepływ. Interpolacja jest
wyłącznie wizualna; dane, poziomy i taryfy pozostają liczone w blokach.
"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from app.kontekst import ETYKIETY_BLOKOW, KOLOR_NEUTRALNY, KOLORY_POZIOMOW, Kontekst
from parkflow.mapa import WYLACZONY, profil_dnia
from parkflow.model import BLOKI, ZA_MALO_DANYCH

SZABLON = Path(__file__).resolve().parent.parent / "assets" / "przeplyw.html"
SRODKI_BLOKOW = [(int(b[:2]) + int(b[3:])) / 2 for b in BLOKI]


def _zaokraglij(wsp):
    """Współrzędne do 5 miejsc (~1 m): kilka razy mniejszy HTML komponentu."""
    if isinstance(wsp[0], (int, float)):
        return [round(wsp[0], 5), round(wsp[1], 5)]
    return [_zaokraglij(w) for w in wsp]


def _poziomy_dnia(ctx: Kontekst) -> dict[str, list[str]]:
    t = ctx.tabela[ctx.tabela["sezon"] == ctx.sezon]
    etykieta = t["poziom"].where(t["adnotacja"] != ZA_MALO_DANYCH, "P1 · za mało danych")
    tab = t.assign(etykieta=etykieta).pivot(index="kod", columns="blok", values="etykieta")
    return {kod: [str(v) for v in wiersz] for kod, wiersz in
            tab.reindex(columns=list(BLOKI)).fillna("P1 · za mało danych").iterrows()}


def render(ctx: Kontekst, features: list[dict], stan: pd.DataFrame, ulice: dict[str, str],
           alfa: dict[str, int], wysokosc: int = 640) -> None:
    """`features` = polygony kodów z kody.geojson, `stan` = stan_kodow widocznych kodów (indeks kod)."""
    profil = profil_dnia(ctx.tabela, ctx.sezon)
    poziomy = _poziomy_dnia(ctx)
    brak = ["P1 · za mało danych"] * len(BLOKI)
    wynik = []
    for f in features:
        kod = f["properties"]["kod"]
        if kod not in stan.index:
            continue
        p = profil.loc[kod].tolist() if kod in profil.index else [None] * len(BLOKI)
        wynik.append({"type": "Feature", "geometry": {
            "type": f["geometry"]["type"], "coordinates": _zaokraglij(f["geometry"]["coordinates"]),
        }, "properties": {
            "kod": kod, "ulice": ulice.get(kod, ""),
            "wylaczony": bool(stan.at[kod, "stan"] == WYLACZONY), "opis": str(stan.at[kod, "opis"]),
            "p": [None if pd.isna(v) else round(float(v), 2) for v in p],
            "poziomy": poziomy.get(kod, brak),
        }})
    dane = {
        "geojson": {"type": "FeatureCollection", "features": wynik},
        "bloki": [ETYKIETY_BLOKOW[b] for b in BLOKI],
        "srodki": SRODKI_BLOKOW,
        "start": SRODKI_BLOKOW[BLOKI.index(ctx.blok)],
        "kolory": {**{p: list(c) for p, c in KOLORY_POZIOMOW.items()}, "neutralny": list(KOLOR_NEUTRALNY)},
        "alfa": alfa,
    }
    # `</` w danych zamknąłby <script>; JSON dopuszcza escape `<\/`.
    html = SZABLON.read_text().replace("__DANE__", json.dumps(dane, ensure_ascii=False).replace("</", "<\\/"))
    if hasattr(st, "iframe"):
        st.iframe(html, height=wysokosc)
    else:  # starszy Streamlit bez st.iframe
        components.html(html, height=wysokosc)
