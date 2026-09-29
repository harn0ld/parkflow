"""Logika digitalizacji parkomatów (ticket 06): numery, georeferencja, przypisanie kodu.

Czyste funkcje na numpy/pandas. Przetwarzanie obrazu (OpenCV, tesseract) jest w
`scripts/digitalizuj_parkomaty.py`, tu zostaje to, co da się przetestować bez mapy.

Układ metryczny: EPSG:2180 (PUWG 1992, jak PRG). `x` = easting, `y` = northing.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
from pyproj import Transformer

NUMER_MAX = 440  # mapa ZDiT VI 2024: numery 1–440, globalnie unikalne
# Litera w ID = podstrefa z mapy 2024. Od VI 2025 dawne C (Fabryczna) weszło do B,
# a D (Bałucki Rynek) to obecna C — tak samo jak fallback w pipeline/aggregate.py.
PODSTREFA_2025 = {"A": "A", "B": "B", "C": "B", "D": "C"}

STATUS_MAPA = "mapa_2024"  # kropka z mapy, georeferencja afiniczna
STATUS_WSTAWKA = "mapa_2024_wstawka"  # wstawka Rynek Bałucki, osobna transformacja
STATUS_ZDIT = "wspolrzedne_zdit"  # współrzędne z XLSX ZDiT (Legionów)
STATUS_NIEZNANA = "lokalizacja nieznana"  # ID z danych Visa, którego nie ma na mapie

_DO_2180 = Transformer.from_crs(4326, 2180, always_xy=True)
_DO_4326 = Transformer.from_crs(2180, 4326, always_xy=True)


def do_2180(lat, lon) -> tuple[np.ndarray, np.ndarray]:
    x, y = _DO_2180.transform(np.asarray(lon, float), np.asarray(lat, float))
    return np.asarray(x), np.asarray(y)


def do_wgs84(x, y) -> tuple[np.ndarray, np.ndarray]:
    """EPSG:2180 → (lat, lon)."""
    lon, lat = _DO_4326.transform(np.asarray(x, float), np.asarray(y, float))
    return np.asarray(lat), np.asarray(lon)


# ---------- numery ----------

def parsuj_etykiete(tekst: str, litera: str) -> int | None:
    """Odczyt OCR etykiety → numer parkomatu albo None.

    Litera jest znana z koloru ramki, więc OCR służy tylko do cyfr. Typowe błędy
    tesseracta: resztka ramki czytana jako B/D na początku (`B5A`), litera B czytana
    jako 8 (`2178` = 217B). Numer spoza 1–440 odrzucamy.
    """
    t = re.sub(r"\s", "", tekst or "").upper()
    t = re.sub(r"^[BD](?=\d)", "", t)  # pionowa kreska ramki przed cyframi
    m = re.fullmatch(r"(\d{1,3})" + litera, t)
    if m is None and litera == "B":
        m = re.fullmatch(r"(\d{1,3})8", t)
    if m is None:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= NUMER_MAX else None


def numer_id(numer: int, litera: str) -> str:
    """ID jak w danych Visa (`SPP Lodz 438B` → `438B`)."""
    return f"{numer}{litera}"


def waliduj_numery(numery: pd.Series) -> dict[str, list]:
    """Numery (int) przypisane kropkom: duplikaty, spoza zakresu, brakujące w 1–440."""
    n = numery.dropna().astype(int)
    licz = n.value_counts()
    return {
        "duplikaty": sorted(licz[licz > 1].index.tolist()),
        "poza_zakresem": sorted(n[(n < 1) | (n > NUMER_MAX)].unique().tolist()),
        "brakujace": sorted(set(range(1, NUMER_MAX + 1)) - set(n.tolist())),
    }


def rozstrzygnij_odczyty(odczyty: pd.DataFrame) -> pd.DataFrame:
    """Kropka × kandydaci numeru → jeden numer na kropkę, numer unikalny.

    Wejście: `kropka`, `numer`, `zrodlo` (`manual` wygrywa z `ocr`). Numer OCR, który
    trafił do dwóch kropek, albo kropka z dwoma różnymi numerami OCR — odrzucamy
    (do ręcznej poprawki). Wyjście: `kropka`, `numer`, `zrodlo`.
    """
    o = odczyty.dropna(subset=["numer"]).drop_duplicates(["kropka", "numer", "zrodlo"])
    manual = o[o.zrodlo == "manual"]
    if manual.numer.duplicated().any() or manual.kropka.duplicated().any():
        raise ValueError("ręczne poprawki: numer lub kropka powtórzone")
    ocr = o[(o.zrodlo == "ocr") & ~o.kropka.isin(manual.kropka) & ~o.numer.isin(manual.numer)]
    ocr = ocr[~ocr.kropka.duplicated(keep=False) & ~ocr.numer.duplicated(keep=False)]
    out = pd.concat([manual, ocr], ignore_index=True)[["kropka", "numer", "zrodlo"]]
    return out.sort_values("numer").reset_index(drop=True)


# ---------- georeferencja ----------

def dopasuj_afiniczna(px: np.ndarray, xy: np.ndarray) -> np.ndarray:
    """Najmniejsze kwadraty: [px_x, px_y, 1] @ M = [x, y]. Zwraca M (3×2)."""
    px, xy = np.asarray(px, float), np.asarray(xy, float)
    if len(px) < 3:
        raise ValueError("afiniczna wymaga ≥ 3 punktów")
    a = np.column_stack([px, np.ones(len(px))])
    m, *_ = np.linalg.lstsq(a, xy, rcond=None)
    return m


def zastosuj_afiniczna(m: np.ndarray, px: np.ndarray) -> np.ndarray:
    px = np.atleast_2d(np.asarray(px, float))
    return np.column_stack([px, np.ones(len(px))]) @ m


def dopasuj_podobienstwo(px: np.ndarray, xy: np.ndarray) -> np.ndarray:
    """Podobieństwo (skala, obrót, przesunięcie; oś y obrazu w dół) jako M 3×2.

    Na wstawkę, gdzie są 2–3 punkty kontrolne. Parametry: x = a·u + b·v + c,
    y = b·u − a·v + d (odbicie, bo y obrazu rośnie w dół, a northing w górę).
    """
    px, xy = np.asarray(px, float), np.asarray(xy, float)
    u, v = px[:, 0], px[:, 1]
    one, zero = np.ones(len(u)), np.zeros(len(u))
    a = np.vstack([np.column_stack([u, v, one, zero]), np.column_stack([-v, u, zero, one])])
    b = np.concatenate([xy[:, 0], xy[:, 1]])
    (p, q, c, d), *_ = np.linalg.lstsq(a, b, rcond=None)
    return np.array([[p, q], [q, -p], [c, d]])


def bledy_georeferencji(px: np.ndarray, xy: np.ndarray, dopasuj=dopasuj_afiniczna) -> pd.DataFrame:
    """Reszty na punktach kontrolnych i leave-one-out, w metrach."""
    px, xy = np.asarray(px, float), np.asarray(xy, float)
    m = dopasuj(px, xy)
    reszta = np.linalg.norm(zastosuj_afiniczna(m, px) - xy, axis=1)
    loo = np.empty(len(px))
    for i in range(len(px)):
        maska = np.arange(len(px)) != i
        mi = dopasuj(px[maska], xy[maska])
        loo[i] = np.linalg.norm(zastosuj_afiniczna(mi, px[i:i + 1])[0] - xy[i])
    return pd.DataFrame({"reszta_m": reszta, "loo_m": loo})


def skala_m_na_px(m: np.ndarray) -> tuple[float, float]:
    """Długość wektora jednostkowego piksela w osi x i y obrazu [m/px]."""
    return float(np.linalg.norm(m[0])), float(np.linalg.norm(m[1]))


# ---------- kod pocztowy ----------

def przypisz_kod(xy: np.ndarray, adresy_xy: np.ndarray, adresy_kod: np.ndarray,
                 adresy_ulica: np.ndarray | None = None) -> pd.DataFrame:
    """Kod pocztowy najbliższego punktu adresowego PRG (EPSG:2180). Zwraca kod, odległość [m]
    i — gdy podano `adresy_ulica` — ulicę tego punktu (`ulica_adresu`)."""
    from scipy.spatial import cKDTree

    d, i = cKDTree(np.asarray(adresy_xy, float)).query(np.asarray(xy, float))
    out = pd.DataFrame({"kod_pocztowy": np.asarray(adresy_kod)[i], "odl_adres_m": np.round(d, 1)})
    if adresy_ulica is not None:
        out["ulica_adresu"] = np.asarray(adresy_ulica)[i]
    return out


def kody_spp(parkomaty: pd.DataFrame) -> pd.DataFrame:
    """Kody SPP: kod z ≥ 1 zlokalizowanym parkomatem. Wyjście: `kod_pocztowy`, `parkomaty`."""
    z = parkomaty.dropna(subset=["kod_pocztowy"])
    return (
        z.groupby("kod_pocztowy").size().rename("parkomaty").reset_index()
        .sort_values("kod_pocztowy").reset_index(drop=True)
    )
