"""Dane dodatkowych warstw mapy: parkomaty SPP (ticket 06) i zmierzony popyt (ticket 07).

Czyste pandas, bez pydeck: widok (`app/widoki/mapa_warstwy.py`) dokłada tylko kolory i tooltip.
"""

import numpy as np
import pandas as pd

# Status lokalizacji z data/parkomaty.csv → etykieta dla urzędnika.
STATUSY = {
    "mapa_2024": "z mapy ZDiT (VI 2024)",
    "mapa_2024_wstawka": "z mapy ZDiT (VI 2024), wstawka Bałucki Rynek",
    "wspolrzedne_zdit": "współrzędne ZDiT",
    "lokalizacja nieznana": "lokalizacja nieznana",
}
PROMIEN_MAX_M = 220  # promień koła największej komórki popytu w całej tabeli


def parkomaty_na_mapie(parkomaty: pd.DataFrame) -> pd.DataFrame:
    """Parkomaty z lokalizacją → numer, podstrefa, podstrefa_2024, ulica, kod_pocztowy, status, lat, lon.

    Parkomaty „lokalizacja nieznana” (ID z danych Visa spoza mapy 2024) nie mają współrzędnych i są pomijane.
    """
    p = parkomaty[parkomaty["lat"].notna() & parkomaty["lon"].notna()].copy()
    p["status"] = p["status_lokalizacji"].map(STATUSY).fillna(p["status_lokalizacji"])
    p = p.fillna({"podstrefa": "", "podstrefa_2024": "", "ulica": "", "kod_pocztowy": ""})
    kolumny = ["numer", "podstrefa", "podstrefa_2024", "ulica", "kod_pocztowy", "status", "lat", "lon"]
    return p[kolumny].reset_index(drop=True)


def zmierzony_popyt(popyt: pd.DataFrame, kody_ulice: pd.DataFrame, sezon: str, blok: str,
                    promien_max_m: float = PROMIEN_MAX_M) -> pd.DataFrame:
    """agg_parkomaty_strefy + centroidy kodów → kod, lat, lon, ulice, oplacone_autogodziny, karty, promien_m.

    Jeden sezon i blok. Pole koła ∝ opłaconym auto-godzinom; skala wspólna dla całej tabeli
    (wszystkich sezonów i bloków), więc przy zmianie suwaka koła są porównywalne.
    Kody bez centroidu w `kody_ulice` (brak adresów PRG) są pomijane.
    """
    kolumny = ["kod", "lat", "lon", "ulice", "oplacone_autogodziny", "karty", "promien_m"]
    maks = popyt["oplacone_autogodziny"].max() if len(popyt) else np.nan
    sel = popyt[(popyt["sezon"] == sezon) & (popyt["blok"] == blok)]
    df = sel.merge(kody_ulice[["kod", "lat", "lon", "ulice"]], on="kod", how="inner").dropna(subset=["lat", "lon"])
    if df.empty or not maks > 0:
        return pd.DataFrame(columns=kolumny)
    df["promien_m"] = promien_max_m * np.sqrt(df["oplacone_autogodziny"].clip(lower=0) / maks)
    df["ulice"] = df["ulice"].fillna("")
    # Duże koła pod małymi: pydeck rysuje w kolejności wierszy.
    return df.sort_values("oplacone_autogodziny", ascending=False)[kolumny].reset_index(drop=True)
