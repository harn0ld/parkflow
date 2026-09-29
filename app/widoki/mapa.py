"""Widok: mapa kodów pocztowych Łodzi pokolorowanych poziomem P (ticket 02).

Warstwa bazowa: polygony kodów z data/kody.geojson (PRG, scripts/zbuduj_kody.py).
Kolejne warstwy (parkomaty, zmierzony popyt, stali bywalcy) dopisuje się do `WARSTWY`
— patrz parkflow-notes/02-mapa.md. Tooltip (`TOOLTIP`) jest wspólny dla wszystkich warstw:
każdy obiekt warstwy ma pola `tytul`, `tresc`, `uwaga` (zbuduj je funkcją `pola_tooltipa`).
"""

import json
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd
import pydeck as pdk
import streamlit as st

from app.kontekst import (CURB_SENSITIVE, ETYKIETY_BLOKOW, ETYKIETY_SEZONOW, KOLOR_NEUTRALNY, KOLORY_POZIOMOW,
                          TYPY_WIZYT, WNIOSKI_TYPOW, Kontekst,
                          NAZWY_USLUG)
from app.widoki import mapa_warstwy, przeplyw, wyliczenia
from parkflow.dane import KODY_GEOJSON, KODY_ULICE, kody_wylaczone, wczytaj_kody_ulice
from parkflow.mapa import WYLACZONY, ZA_MALO, stan_kodow
from parkflow.model import POZIOMY

TYTUL = "Mapa"

WIDOK_LODZI = pdk.ViewState(latitude=51.765, longitude=19.46, zoom=11.3, pitch=0)
ALFA_POZIOMU = 170
ALFA_ZA_MALO = 45  # „za mało danych” = P1 zgodnie z modelem, ale blado
ALFA_WYLACZONY = 150


@dataclass(frozen=True)
class Warstwa:
    """Dodatkowa warstwa mapy. `zbuduj(ctx)` zwraca warstwę pydeck (albo listę / None, gdy brak danych).

    `opis(ctx)` (opcjonalny) to legenda pod mapą, gdy warstwa jest włączona (markdown, może mieć HTML).
    """

    nazwa: str
    zbuduj: Callable[[Kontekst], "pdk.Layer | list[pdk.Layer] | None"]
    domyslnie: bool = True
    opis: Callable[[Kontekst], str] | None = None


# Dodatkowe warstwy nad kodami (ticket 06 parkomaty, 07 zmierzony popyt, 11 stali bywalcy).
WARSTWY: list[Warstwa] = [
    Warstwa("Parkomaty", mapa_warstwy.zbuduj_parkomaty, domyslnie=True, opis=mapa_warstwy.opis_parkomatow),
]


def _uslugi_w_kodach(ctx: Kontekst) -> dict[str, str]:
    grupy = ctx.agregaty.grupy
    wybrane = grupy.loc[
        (grupy["sezon"] == ctx.sezon) & (grupy["blok"] == ctx.blok)
        & (grupy["karty_przyjezdne"] >= 30)
    ]
    return {kod: _udzialy_typow(dane.set_index("grupa")["karty_przyjezdne"])
            for kod, dane in wybrane.groupby("kod")}


def _udzialy_typow(karty: pd.Series) -> str:
    """Typy wizyt z udziałem % (i grupami składowymi) w sumie kart przyjezdnych grup kodu."""
    suma = karty.sum()
    pct = lambda grupy: 100 * karty.reindex(list(grupy)).fillna(0).sum() / suma
    wiersze = []
    for typ, grupy in sorted(TYPY_WIZYT.items(), key=lambda t: -pct(t[1])):
        if not pct(grupy):
            continue
        sklad = ", ".join(f"{NAZWY_USLUG[g].lower()} {pct([g]):.0f}%"
                          for g in sorted(grupy, key=lambda g: -pct([g])) if pct([g]))
        wiersze.append(f"• {typ} — {pct(grupy):.0f}%  ({WNIOSKI_TYPOW[typ]})\n    {sklad}")
    if pct(CURB_SENSITIVE):
        wiersze.append(f"w tym curb-sensitive (odbiór, dostawy) — {pct(CURB_SENSITIVE):.0f}%")
    return "\n".join(wiersze)


# Wartości pozostają zwykłym tekstem; układ i style są w szablonie HTML.
TOOLTIP = {
    "html": (
        "<div style='font-size:20px;font-weight:750;color:#0f172a'>{tytul}</div>"
        "<div style='font-size:12px;color:#64748b;white-space:pre-line'>{podtytul}</div>"
        "<div style='margin-top:10px;color:#475569;white-space:pre-line'>{tresc}</div>"
        "<div style='margin-top:12px;font-size:11px;font-weight:750;color:#2563eb;"
        "letter-spacing:.6px'>{naglowek_taryfy}</div>"
        "<div style='font-size:14px;font-weight:650;line-height:1.9;white-space:pre-line'>{taryfa}</div>"
        "<div style='margin-top:10px;font-size:11px;font-weight:750;color:#64748b;"
        "letter-spacing:.6px'>{naglowek_uslug}</div>"
        "<div style='line-height:1.8;white-space:pre-line'>{uslugi}</div>"
        "<div style='margin-top:10px;font-size:11px;color:#64748b;white-space:pre-line'>{uwaga}</div>"
    ),
    "style": {
        "fontFamily": "Inter, system-ui, sans-serif", "fontSize": "13px",
        "backgroundColor": "#ffffff", "color": "#0f172a", "padding": "18px 20px",
        "borderRadius": "14px", "border": "1px solid #e2e8f0",
        "boxShadow": "0 8px 30px rgba(15,23,42,.18)",
        "maxWidth": "min(380px, calc(100vw - 48px))", "lineHeight": "1.5",
    },
}


def pola_tooltipa(tytul: str, wiersze: dict[str, object] | None = None, uwaga: str = "") -> dict[str, str]:
    """Pola `tytul`, `tresc` („klucz: wartość” w liniach, puste pomijane), `uwaga` dla szablonu TOOLTIP."""
    tresc = "\n".join(f"{k}: {v}" for k, v in (wiersze or {}).items() if v not in (None, ""))
    return {"tytul": str(tytul), "tresc": tresc, "uwaga": str(uwaga or ""),
            "podtytul": "", "naglowek_taryfy": "", "taryfa": "", "naglowek_uslug": "", "uslugi": ""}


@st.cache_data
def _kody_geojson() -> dict:
    return json.loads(KODY_GEOJSON.read_text())


@st.cache_data
def _kody_ulice():
    return wczytaj_kody_ulice(KODY_ULICE).set_index("kod")


@st.cache_data
def _wylaczone(katalog: str) -> dict[str, str]:
    return kody_wylaczone(katalog)


def _kolor(stan: str, poziom: str) -> list[int]:
    if stan == WYLACZONY:
        return [*KOLOR_NEUTRALNY, ALFA_WYLACZONY]
    return [*KOLORY_POZIOMOW[poziom], ALFA_ZA_MALO if stan == ZA_MALO else ALFA_POZIOMU]


def _skroc(ulice: str, n: int = 6) -> str:
    lista = ulice.split("; ")
    return "; ".join(lista[:n]) + (f" (+{len(lista) - n})" if len(lista) > n else "")


def _udzialy_w_kodach(ctx: Kontekst) -> pd.DataFrame:
    """Kod × typ wizyty: udział % w sumie kart przyjezdnych grup z ≥ 30 kartami (jak w podpowiedzi)."""
    dane = ctx.agregaty.grupy
    karty = dane.loc[
        dane["sezon"].eq(ctx.sezon) & dane["blok"].eq(ctx.blok) & dane["karty_przyjezdne"].ge(30)
    ].pivot_table(index="kod", columns="grupa", values="karty_przyjezdne", aggfunc="sum", fill_value=0)
    typy = {**TYPY_WIZYT, "Curb-sensitive": CURB_SENSITIVE}
    suma = karty.sum(axis=1)
    return pd.DataFrame({
        typ: 100 * karty.reindex(columns=list(grupy), fill_value=0).sum(axis=1) / suma
        for typ, grupy in typy.items()
    })


def kody_z_typami(ctx: Kontekst, typy: list[str], minimum_pct: float, wszystkie: bool = False) -> set[str]:
    """Kody, w których dowolny lub każdy wybrany typ wizyty ma co najmniej `minimum_pct` % kart."""
    spelnia = _udzialy_w_kodach(ctx)[typy].ge(minimum_pct)
    return set(spelnia.index[spelnia.all(axis=1) if wszystkie else spelnia.any(axis=1)])


def warstwa_kodow(ctx: Kontekst, wybrane_kody: set[str] | None = None) -> tuple[pdk.Layer, pd.DataFrame]:
    """GeoJsonLayer kodów pokolorowanych poziomem P dla ctx.sezon i ctx.blok + tabela stanu kodów."""
    gj = _kody_geojson()
    ulice = _kody_ulice()
    kody = [f["properties"]["kod"] for f in gj["features"]]
    stan = stan_kodow(kody, ctx.komorki, _wylaczone(str(ctx.agregaty.katalog))).set_index("kod")
    # Na razie pokazujemy wyłącznie kody oznaczone jako SPP, bez bufora.
    stan = stan.loc[stan["spp"].eq(True)]
    if wybrane_kody is not None:
        stan = stan.loc[stan.index.isin(wybrane_kody) & stan["stan"].ne(WYLACZONY)]
    stany = stan.to_dict("index")
    nazwy = ulice["ulice"].to_dict()
    uslugi = _uslugi_w_kodach(ctx)
    features = []
    for f in gj["features"]:
        kod = f["properties"]["kod"]
        if kod not in stany:
            continue
        s = stany[kod]
        tooltip = pola_tooltipa(f"Sektor {kod}", {"Ulice": _skroc(str(nazwy.get(kod, "")), 4)})
        tooltip["podtytul"] = (
            f"SPP · {ETYKIETY_SEZONOW[ctx.sezon]} · {ETYKIETY_BLOKOW[ctx.blok]}"
        )
        if s["stan"] == WYLACZONY:
            tooltip["uwaga"] = s["opis"]
        else:
            tooltip["naglowek_uslug"] = "TYPY WIZYT · UDZIAŁ KART PRZYJEZDNYCH VISA"
            tooltip["uslugi"] = uslugi.get(kod, "Brak grup z co najmniej 30 kartami.")
            if s["stan"] == ZA_MALO:
                tooltip["uwaga"] = "Za mało danych — brak rekomendowanej taryfy."
            else:
                _, taryfa = wyliczenia.taryfa_sektora(ctx, kod, s["poziom"])
                zl = lambda v: f"{v:.2f}".replace(".", ",") + " zł"
                etapy = [f"Pierwsze {taryfa.okres_pref_min} min  ·  {zl(taryfa.cena_pref)}"
                         + (" łącznie" if taryfa.ryczalt else "/godz.")]
                if taryfa.okres_pref_min < taryfa.prog_min:
                    etapy.append(f"{taryfa.okres_pref_min}–{taryfa.prog_min} min  ·  {zl(taryfa.stawka_potem)}/godz.")
                etapy.append(f"Po {max(taryfa.okres_pref_min, taryfa.prog_min)} min  ·  {zl(taryfa.stawka_po_2h)}/godz.")
                tooltip["naglowek_taryfy"] = f"POLECANA TARYFA · {s['poziom']}"
                tooltip["taryfa"] = "\n".join(etapy)
                tooltip["uwaga"] = (
                    "Propozycja modelu · bez ulgi mieszkańca.\n"
                    + ("Pierwsza opłata stała, także za krótszy postój.\n" if taryfa.ryczalt else "")
                    + "Stawki godzinowe naliczane minutowo."
                )
        features.append({
            "type": "Feature", "geometry": f["geometry"],
            "properties": {"kod": kod, "kolor": _kolor(s["stan"], s["poziom"]), **tooltip},
        })
    layer = pdk.Layer(
        "GeoJsonLayer", {"type": "FeatureCollection", "features": features}, id="kody",
        pickable=True, stroked=True, filled=True, get_fill_color="properties.kolor",
        get_line_color=[255, 255, 255, 160], line_width_min_pixels=0.5, auto_highlight=True,
    )
    return layer, stan


def _legenda() -> str:
    def kwadrat(rgb, alfa):
        return (f"<span style='display:inline-block;width:12px;height:12px;margin:0 4px 0 12px;"
                f"background:rgba({rgb[0]},{rgb[1]},{rgb[2]},{alfa / 255:.2f});border:1px solid #999'></span>")
    pozycje = [kwadrat(KOLORY_POZIOMOW[p], ALFA_POZIOMU) + p for p in POZIOMY]
    pozycje.append(kwadrat(KOLORY_POZIOMOW["P1"], ALFA_ZA_MALO) + "za mało danych (P1)")
    pozycje.append(kwadrat(KOLOR_NEUTRALNY, ALFA_WYLACZONY) + "kod zbiorczy / wyłączony")
    return "".join(pozycje)


def render(ctx: Kontekst) -> None:
    st.subheader(f"Mapa poziomów P · {ETYKIETY_SEZONOW[ctx.sezon]} · przedział godzinowy {ETYKIETY_BLOKOW[ctx.blok]}")
    if not KODY_GEOJSON.exists() or not KODY_ULICE.exists():
        st.info("Brak data/kody.geojson lub data/kody_ulice.csv — uruchom `python scripts/zbuduj_kody.py`.")
        return

    with st.expander("Filtry typów wizyt", expanded=True):
        typy = st.multiselect(
            "Jakich wizyt szukasz?", [*TYPY_WIZYT, "Curb-sensitive"],
            format_func=lambda t: f"{t} · {WNIOSKI_TYPOW.get(t, 'odbiór, dostawy')}",
            key="mapa_filtr_typy", placeholder="Wszystkie typy — wybierz, aby zawęzić mapę",
        )
        lewa, prawa = st.columns(2)
        minimum = lewa.slider(
            "Minimalny udział typu w kartach przyjezdnych (%)", min_value=0, max_value=100, value=30, step=5,
            disabled=not typy, key="mapa_filtr_udzial",
        )
        tryb = prawa.radio(
            "Przy kilku typach pokaż sektory spełniające próg dla:",
            ["Dowolnego wybranego typu", "Każdego wybranego typu"],
            disabled=len(typy) < 2, key="mapa_filtr_tryb_typow",
        )
        st.caption(
            "Udział liczymy tak jak w podpowiedzi: od sumy kart przyjezdnych Visa w grupach z co najmniej 30 kartami, "
            "w wybranym sezonie i godzinach. Curb-sensitive nakłada się na pozostałe typy. "
            "Usuń wybrane typy, aby ponownie pokazać wszystkie sektory SPP."
        )
    wybrane_kody = kody_z_typami(ctx, typy, minimum, tryb == "Każdego wybranego typu") if typy else None
    kody, stan = warstwa_kodow(ctx, wybrane_kody)
    if typy:
        st.caption(f"Sektory pasujące do filtrów: {len(stan)}.")
        if stan.empty:
            st.info("Brak sektorów spełniających filtry. Zmniejsz próg udziału lub zmień typy wizyt.")
    odtwarzanie = st.toggle(
        "Przepływ w ciągu dnia (odtwarzanie 7→19)", key="mapa_przeplyw",
        help="Suwak i przycisk ▶ przesuwają godzinę; sektory płynnie przechodzą między blokami 7–10, 10–13, 13–16, 16–19.",
    )
    if odtwarzanie:
        nazwy = _kody_ulice()["ulice"].to_dict()
        przeplyw.render(
            ctx, _kody_geojson()["features"], stan, {k: _skroc(str(v), 4) for k, v in nazwy.items()},
            alfa={"poziom": ALFA_POZIOMU, "za_malo": ALFA_ZA_MALO, "wylaczony": ALFA_WYLACZONY},
        )
        st.caption(
            "Odtwarzanie pokazuje presję sektorów SPP w wybranym sezonie od 7:00 do 19:00 (pn–pt). "
            "W środku każdego bloku (8:30, 11:30, 14:30, 17:30) kolor i wysokość odpowiadają danym bloku; "
            "przejścia między nimi są interpolacją wizualną, a nie pomiarem godzinowym. "
            "Poziomy P i taryfy obowiązują w całych blokach. Blado: za mało danych (P1). "
            "Parkomaty i podpowiedzi z taryfami są dostępne po wyłączeniu odtwarzania."
        )
        return
    warstwy = [kody]
    opisy = []
    if WARSTWY:
        kolumny = st.columns(len(WARSTWY))
        for kol, w in zip(kolumny, WARSTWY):
            if kol.checkbox(w.nazwa, value=w.domyslnie, key=f"mapa_warstwa_{w.nazwa}"):
                wynik = w.zbuduj(ctx)
                if typy and wynik is not None and w.nazwa == "Parkomaty":
                    wynik.data = [p for p in wynik.data if p["kod_pocztowy"] in stan.index]
                warstwy += wynik if isinstance(wynik, list) else [wynik] if wynik is not None else []
                if w.opis is not None:
                    opisy.append(w.opis(ctx))

    st.pydeck_chart(pdk.Deck(
        layers=warstwy, initial_view_state=WIDOK_LODZI, map_style="light",
        tooltip=TOOLTIP,
    ), height=620)
    st.markdown(_legenda(), unsafe_allow_html=True)
    st.caption("Taryfy w podpowiedziach są propozycją modelu dla wybranego sezonu i bloku, nie obowiązującym cennikiem SPP.")
    for opis in opisy:
        st.markdown(f"<small>{opis}</small>", unsafe_allow_html=True)
    st.caption(
        "Najedź na obszar, aby zobaczyć typy wizyt (Quick stop, Errand, Destination) z udziałem w kartach "
        "przyjezdnych Visa w wybranym sezonie i bloku. Udział liczymy od sumy kart grup z co najmniej 30 kartami; "
        "jedna karta może występować w kilku grupach. Typy przypisujemy do grup MCC w przybliżeniu: "
        "Long dwell (hotele, biura, szpitale) nie ma osobnej grupy w agregatach, a curb-sensitive "
        "(gastronomia i małe sklepy spożywcze) nakłada się na pozostałe typy. "
        "Agregaty nie zawierają nazw lokali ani szczegółowych rodzajów usług w danym kodzie."
    )

    kody_prg = {f["properties"]["kod"] for f in _kody_geojson()["features"]}
    brak_na_mapie = sorted(set(ctx.komorki["kod"]) - kody_prg)
    st.caption(
        "Mapa pokazuje tylko kody oznaczone jako SPP; bufor i kody bez oznaczenia SPP są ukryte. "
        f"{int((stan['stan'] == 'poziom').sum())} z {len(stan)} widocznych kodów PRG ma poziom z danych w tym bloku; "
        "kody bez transakcji lub poniżej 30 kart przyjezdnych mają P1 z adnotacją „za mało danych”. "
        "Szare: kody zbiorcze (adres rozliczeniowy wielu sprzedawców) i galerie z własnym parkingiem, wyłączone ze stref. "
        + (f"Kody z danych Visa bez punktów adresowych w PRG (brak na mapie): {', '.join(brak_na_mapie)}. "
           if brak_na_mapie else "")
        + "Granice kodów: komórki Voronoi punktów adresowych, przycięte do 150 m od adresów. Źródło: PRG, GUGiK."
    )
