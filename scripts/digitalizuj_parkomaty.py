"""Ticket 06: mapa parkomatów ZDiT (VI 2024) → data/parkomaty.csv + data/spp_kody.csv.

Kroki (logika testowalna w `pipeline/parkomaty.py`):
1. Segmentacja kropek po kolorze podstrefy (A fiolet, B zieleń, C pomarańcz, D niebieski).
2. Ramki etykiet (dwa detektory) → OCR tesseract → numer; litera = kolor ramki.
3. Przypisanie etykieta → kropka 1:1 (Hungarian, próg 60 px).
4. Ręczne odczyty `data/raw/zdit/parkomaty_odczyty_reczne.csv` (numer, px_x, px_y) wygrywają z OCR.
5. Georeferencja afiniczna na punktach kontrolnych `data/raw/zdit/parkomaty_punkty_kontrolne.csv`
   (skrzyżowania osi ulic PRG + 9 parkomatów z XLSX ZDiT); wstawka Rynek Bałucki osobno
   (podobieństwo na 3 punktach). Legenda wykluczona.
6. Kod pocztowy = najbliższy punkt adresowy PRG, ulica = najbliższa oś ulicy PRG.
7. ID z danych Visa, których nie ma na mapie → status „lokalizacja nieznana”.

Użycie:
    python scripts/digitalizuj_parkomaty.py [--prg DIR] [--kafle DIR]

`--prg`: katalog z rozpakowanym PRG dla TERYT 1061 (PRG_PunktyAdresowe_1061.shp, PRG_Ulice_1061.shp).
Domyślnie `data/raw/prg/` (poza gitem); gdy go brak, skrypt pobiera zip z GUGiK.
`--kafle`: zapisuje kafle z kropkami bez numeru (do ręcznego odczytu).
"""

from __future__ import annotations

import argparse
import io
import os
import re
import sys
import urllib.request
import zipfile

import cv2
import numpy as np
import pandas as pd
import pytesseract
from scipy.optimize import linear_sum_assignment

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline import parkomaty as P  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
ZDIT = os.path.join(ROOT, "data", "raw", "zdit")
MAPA = os.path.join(ZDIT, "mapa-parkomatow-2024-06.jpg")
XLSX = os.path.join(ZDIT, "wspolrzedne-parkomatow-legionow.xlsx")
RECZNE = os.path.join(ZDIT, "parkomaty_odczyty_reczne.csv")
KONTROLNE = os.path.join(ZDIT, "parkomaty_punkty_kontrolne.csv")
PRG_URL = "https://opendata.geoportal.gov.pl/prg/adresy/PunktyAdresowe/10/1061.zip"

HUE = {"A": (130, 160), "B": (45, 75), "C": (5, 25), "D": (90, 120)}
POLE_KROPKI = 510  # px², kropka ~25 px średnicy
PROG_PRZYPISANIA = 60  # px: odległość kropki od ramki etykiety


def w_legendzie(x, y) -> bool:
    return x > 4700 and y > 7100


def we_wstawce(x, y) -> bool:
    """Wstawka „Rynek Bałucki” w lewym górnym rogu (inna skala i położenie)."""
    return x < 1190 and y < 760


# ---------- obraz ----------

def kropki(hsv) -> pd.DataFrame:
    H, S, V = cv2.split(hsv)
    wiersze = []
    for litera, (lo, hi) in HUE.items():
        m = ((H >= lo) & (H <= hi) & (S > 180) & (V > 150)).astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
        n, lab, st, cen = cv2.connectedComponentsWithStats(m)
        for i in range(1, n):
            if st[i, 4] < 250 or w_legendzie(*cen[i]):
                continue
            k = max(1, round(st[i, 4] / POLE_KROPKI))
            if k == 1:
                srodki = [cen[i]]
            else:  # sklejone kropki: k-means na pikselach składowej
                ys, xs = np.nonzero(lab == i)
                pts = np.column_stack([xs, ys]).astype(np.float32)
                kryt = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.5)
                _, _, srodki = cv2.kmeans(pts, k, None, kryt, 5, cv2.KMEANS_PP_CENTERS)
            for x, y in srodki:
                wiersze.append({"litera": litera, "px_x": round(float(x), 1), "px_y": round(float(y), 1)})
    d = pd.DataFrame(wiersze).sort_values(["litera", "px_y", "px_x"]).reset_index(drop=True)
    d.insert(0, "kropka", range(len(d)))
    return d


def _ocr(g) -> str:
    cfg = "--psm 7 -c tessedit_char_whitelist=0123456789ABCD"
    return pytesseract.image_to_string(g, config=cfg).strip().replace(" ", "")


def _wnetrze(col, V, x, y, w, h, mx=6, my=5):
    m = col[y + my:y + h - my, x + mx:x + w - mx]
    v = V[y + my:y + h - my, x + mx:x + w - mx]
    if m.size == 0:
        return None
    g = np.where(m > 0, v, 255).astype(np.uint8)  # tylko piksele w kolorze podstrefy: bez linii ulic
    g = cv2.resize(g, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    _, g = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return cv2.copyMakeBorder(g, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)


def ramki(hsv) -> pd.DataFrame:
    """Kandydaci etykiet z dwóch detektorów: pary poziomych linii ramki i składowe konturu."""
    H, S, V = cv2.split(hsv)
    wiersze = []
    for litera, (lo, hi) in HUE.items():
        col = ((H >= lo) & (H <= hi) & (S > 50) & (V > 60)).astype(np.uint8)
        lin = ((H >= lo) & (H <= hi) & (S > 25) & (V > 60)).astype(np.uint8)
        boxes = []
        # 1) pary poziomych odcinków (górna i dolna krawędź ramki)
        hl = cv2.morphologyEx(lin, cv2.MORPH_CLOSE, np.ones((1, 7), np.uint8))
        hl = cv2.morphologyEx(hl, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1)))
        n, _, st, _ = cv2.connectedComponentsWithStats(hl)
        segs = sorted([tuple(st[i, :4]) for i in range(1, n) if 55 <= st[i, 2] <= 260], key=lambda s: s[1])
        for x, y, w, h in segs:
            best = None
            for x2, y2, w2, h2 in segs:
                dy = y2 - y
                if not 35 <= dy <= 75:
                    continue
                ov = min(x + w, x2 + w2) - max(x, x2)
                if ov >= 0.8 * max(w, w2) and (best is None or dy < best[1] - y):
                    best = (x2, y2, w2, h2)
            if best:
                x2, y2, w2, h2 = best
                boxes.append((max(x, x2), y, min(x + w, x2 + w2) - max(x, x2), y2 + h2 - y, "pary"))
        # 2) składowe maski ramki o rozmiarze etykiety
        cl = cv2.morphologyEx(lin, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        n, _, st, _ = cv2.connectedComponentsWithStats(cl)
        for i in range(1, n):
            x, y, w, h = st[i, :4]
            if 38 <= h <= 80 and 55 <= w <= 270:
                boxes.append((x, y, w, h, "skladowe"))
        for x, y, w, h, det in boxes:
            if w_legendzie(x, y):
                continue
            g = _wnetrze(col, V, int(x), int(y), int(w), int(h))
            if g is None:
                continue
            t = _ocr(g)
            wiersze.append({"litera": litera, "x": int(x), "y": int(y), "w": int(w), "h": int(h),
                            "detektor": det, "tekst": t, "numer": P.parsuj_etykiete(t, litera)})
    return pd.DataFrame(wiersze)


def _odl_do_prostokata(px, py, r) -> float:
    dx = max(r.x - px, 0, px - (r.x + r.w))
    dy = max(r.y - py, 0, py - (r.y + r.h))
    return float(np.hypot(dx, dy))


def odczyty_ocr(kr: pd.DataFrame, et: pd.DataFrame) -> pd.DataFrame:
    """Etykiety z numerem → kropki tej samej litery, przypisanie 1:1 per detektor."""
    out = []
    et = et.dropna(subset=["numer"])
    for (litera, det), e in et.groupby(["litera", "detektor"]):
        e = e.drop_duplicates(["x", "y"]).reset_index(drop=True)
        k = kr[kr.litera == litera].reset_index(drop=True)
        if e.empty or k.empty:
            continue
        c = np.array([[_odl_do_prostokata(kk.px_x, kk.px_y, ee) for kk in k.itertuples()] for ee in e.itertuples()])
        ri, ci = linear_sum_assignment(np.minimum(c, 1e4))
        for r, ci_ in zip(ri, ci):
            if c[r, ci_] <= PROG_PRZYPISANIA:
                out.append({"kropka": int(k.kropka[ci_]), "numer": int(e.numer[r]), "zrodlo": "ocr"})
    o = pd.DataFrame(out, columns=["kropka", "numer", "zrodlo"])
    # oba detektory zgodne lub tylko jeden: jeden wiersz; sprzeczne numery rozstrzyga rozstrzygnij_odczyty
    return o.drop_duplicates()


def odczyty_reczne(kr: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ręczne odczyty → (kropki uzupełnione o niewykryte, odczyty).

    Wiersz trafia do najbliższej kropki tej samej litery w promieniu 25 px. Gdy takiej nie ma
    (kropka przykryta linią i zgubiona przez segmentację), wiersz dodaje kropkę w podanym pikselu.
    """
    if not os.path.exists(RECZNE):
        return kr, pd.DataFrame(columns=["kropka", "numer", "zrodlo"])
    r = pd.read_csv(RECZNE, dtype={"numer": str})
    out, nowe = [], []
    for w in r.itertuples():
        m = re.fullmatch(r"(\d{1,3})([ABCD])", w.numer.strip().upper())
        if m is None:
            raise ValueError(f"ręczny odczyt: zły numer {w.numer}")
        k = kr[kr.litera == m.group(2)]
        d = np.hypot(k.px_x - w.px_x, k.px_y - w.px_y)
        if len(d) and d.min() <= 25:
            kropka = int(k.kropka.iloc[int(np.argmin(d.values))])
        else:
            kropka = int(kr.kropka.max()) + 1 + len(nowe)
            nowe.append({"kropka": kropka, "litera": m.group(2), "px_x": float(w.px_x), "px_y": float(w.px_y)})
        out.append({"kropka": kropka, "numer": int(m.group(1)), "zrodlo": "manual"})
    if nowe:
        kr = pd.concat([kr, pd.DataFrame(nowe)], ignore_index=True)
    return kr, pd.DataFrame(out)


def zapisz_kafle(im, kr: pd.DataFrame, katalog: str, rozmiar=(1000, 800)):
    """Kafle z kropkami bez numeru (czerwone kółko + ID kropki) do ręcznego odczytu."""
    os.makedirs(katalog, exist_ok=True)
    brak = kr[kr.numer.isna()]
    W, Hh = rozmiar
    for (tx, ty), grp in brak.groupby([(brak.px_x // W).astype(int), (brak.px_y // Hh).astype(int)]):
        x0, y0 = max(0, tx * W - 150), max(0, ty * Hh - 100)
        tile = im[y0:(ty + 1) * Hh + 100, x0:(tx + 1) * W + 150].copy()
        for w in grp.itertuples():
            p = (int(w.px_x - x0), int(w.px_y - y0))
            cv2.circle(tile, p, 20, (0, 0, 255), 3)
            cv2.putText(tile, str(w.kropka), (p[0] - 30, p[1] + 45), 0, 1.0, (0, 0, 255), 3)
        cv2.imwrite(os.path.join(katalog, f"kafel_{tx}_{ty}.png"), tile)


# ---------- PRG ----------

def wczytaj_prg(katalog: str | None):
    import geopandas as gpd

    katalog = katalog or os.path.join(ROOT, "data", "raw", "prg")
    shp = os.path.join(katalog, "PRG_PunktyAdresowe_1061.shp")
    if not os.path.exists(shp):
        print(f"pobieram PRG → {katalog}")
        os.makedirs(katalog, exist_ok=True)
        with urllib.request.urlopen(PRG_URL) as r:
            zipfile.ZipFile(io.BytesIO(r.read())).extractall(katalog)
        if not os.path.exists(shp):  # zip może mieć podkatalog
            for dp, _, fs in os.walk(katalog):
                if "PRG_PunktyAdresowe_1061.shp" in fs:
                    katalog = dp
                    shp = os.path.join(dp, "PRG_PunktyAdresowe_1061.shp")
    adresy = gpd.read_file(shp, columns=["KOD_POCZT", "NAZWA_ULC"]).set_crs(2180, allow_override=True)
    ulice = gpd.read_file(os.path.join(katalog, "PRG_Ulice_1061.shp")).set_crs(2180, allow_override=True)
    return adresy, ulice


def skrzyzowanie(ulice, a: str, b: str) -> tuple[float, float]:
    """Środek przecięcia osi dwóch ulic PRG (po NAZWA_TER1); MultiPoint → centroid."""
    ga = ulice[ulice.NAZWA_TER1 == a].union_all()
    gb = ulice[ulice.NAZWA_TER1 == b].union_all()
    i = ga.intersection(gb)
    if i.is_empty:
        raise ValueError(f"PRG: osie {a} i {b} się nie przecinają")
    c = i.centroid
    return c.x, c.y


def legionow() -> pd.DataFrame:
    x = pd.read_excel(XLSX, header=1)
    x = x.rename(columns={"NUMER PARKOMATU": "id", "WSPÓŁRZĘDNE": "wsp"})
    x = x.dropna(subset=["id"])
    lat_lon = x.wsp.str.split("/", expand=True).astype(float)
    return pd.DataFrame({"id": x.id.str.strip(), "lat": lat_lon[0], "lon": lat_lon[1]})


def punkty_kontrolne(ulice, kr: pd.DataFrame, leg: pd.DataFrame) -> pd.DataFrame:
    pk = pd.read_csv(KONTROLNE, dtype=str)
    wiersze = []
    for w in pk.itertuples():
        if isinstance(w.numer, str):
            l = leg[leg.id == w.numer]
            k = kr[kr.id == w.numer]
            if l.empty or k.empty:
                raise ValueError(f"punkt kontrolny {w.numer}: brak w XLSX albo na mapie")
            x, y = P.do_2180(l.lat.iloc[0], l.lon.iloc[0])
            px, py = k.px_x.iloc[0], k.px_y.iloc[0]
            zrodlo = "XLSX ZDiT"
        else:
            if isinstance(w.x_2180, str):
                x, y = float(w.x_2180), float(w.y_2180)
            else:
                x, y = skrzyzowanie(ulice, w.ulica1, w.ulica2)
            px, py = float(w.px_x), float(w.px_y)
            zrodlo = "osie ulic PRG"
        wiersze.append({"nazwa": w.nazwa, "uklad": w.uklad, "px_x": px, "px_y": py,
                        "x": float(x), "y": float(y), "zrodlo": zrodlo})
    return pd.DataFrame(wiersze)


# ---------- Visa ----------

def id_visa() -> tuple[set[str], str]:
    """ID parkomatów z danych kartowych: pełna lista z data/parkomaty_visa_id.csv, a bez niej z agregatów."""
    plik = os.path.join(ROOT, "data", "parkomaty_visa_id.csv")
    if os.path.exists(plik):
        return set(pd.read_csv(plik, dtype=str).parkomat.str.upper().str.strip()), "`data/parkomaty_visa_id.csv`"
    ids: set[str] = set()
    for f in ["agg_parkomaty", "agg_stali"]:
        p = os.path.join(ROOT, "data", "agg", f"{f}.parquet")
        if os.path.exists(p):
            ids |= set(pd.read_parquet(p, columns=["parkomat"]).parkomat.dropna().str.upper())
    return ids, "tylko ID z `data/agg` (lista niepełna)"


# ---------- raport ----------

def raport(pk: pd.DataFrame, bl: pd.DataFrame, bl_w: pd.DataFrame, m, wal, stat, sciezka):
    sx, sy = P.skala_m_na_px(m)
    t = pk.assign(reszta_m=np.r_[bl.reszta_m, bl_w.reszta_m], loo_m=np.r_[bl.loo_m, bl_w.loo_m])
    mapa = t[t.uklad == "mapa"]
    rmse = float(np.sqrt((mapa.reszta_m ** 2).mean()))
    rmse_loo = float(np.sqrt((mapa.loo_m ** 2).mean()))

    def wiersz(nazwa, d):
        q = lambda s: f"{np.sqrt((s ** 2).mean()):.1f} m | {s.median():.1f} m | {s.max():.1f} m"  # noqa: E731
        return f"| {nazwa} ({len(d)} pkt) | {q(d.reszta_m)} | {q(d.loo_m)} |"
    L = [
        "# Georeferencja mapy parkomatów ZDiT (VI 2024)",
        "",
        "Wygenerowane przez `scripts/digitalizuj_parkomaty.py` — nie edytuj ręcznie.",
        "",
        "## Metoda",
        "- Transformacja afiniczna piksel → EPSG:2180 (najmniejsze kwadraty), potem WGS84.",
        f"- {len(mapa)} punktów kontrolnych na mapie głównej: {int((mapa.zrodlo == 'osie ulic PRG').sum())} skrzyżowań "
        f"osi ulic PRG (GUGiK) i {int((mapa.zrodlo == 'XLSX ZDiT').sum())} parkomatów z Legionów (XLSX ZDiT). "
        "Piksele skrzyżowań odczytane wizualnie (środek jezdni, ±10 px ≈ ±5 m); piksele parkomatów = środki kropek.",
        f"- Skala: {sx:.3f} m/px (oś x obrazu), {sy:.3f} m/px (oś y) — mapa jest w skali, nie schematyczna.",
        "- Wstawka „Rynek Bałucki” ma własną skalę: osobne podobieństwo na 3 skrzyżowaniach PRG. Legenda wykluczona.",
        "- 9 parkomatów z Legionów dostaje współrzędne z XLSX, a nie z transformacji.",
        "",
        "## Błąd (cel ≤ 50 m)",
        "",
        "| punkty | reszta RMSE | reszta mediana | reszta maks. | LOO RMSE | LOO mediana | LOO maks. |",
        "|---|---|---|---|---|---|---|",
        wiersz("wszystkie, mapa główna", mapa),
        wiersz("skrzyżowania PRG", mapa[mapa.zrodlo == "osie ulic PRG"]),
        wiersz("parkomaty Legionów", mapa[mapa.zrodlo == "XLSX ZDiT"]),
        wiersz("wstawka Rynek Bałucki", t[t.uklad == "wstawka"]),
        "",
        "Leave-one-out: transformacja dopasowana bez danego punktu, błąd = odległość przewidzianej pozycji od prawdziwej.",
        "",
        "**Jak czytać:** skrzyżowania mierzą dokładność samej transformacji (mapa jest wierna geometrycznie, "
        "błąd kilka metrów). Parkomaty z Legionów mierzą to, co nas interesuje — położenie parkomatu — i mają "
        "błąd ~25–45 m, bo kropka jest rysowana obok jezdni z odsunięciem kartograficznym, a współrzędne ZDiT "
        "nie zawsze zgadzają się z układem kropek na mapie. "
        "Transformacja dopasowana tylko na skrzyżowaniach daje na Legionów praktycznie ten sam błąd, więc to "
        "błąd położenia kropek, a nie georeferencji. **Realny błąd parkomatu: ≤ 50 m (typowo 10–30 m).**",
        "",
        "Konsekwencja dla kodów pocztowych: kody w Łodzi bywają jedną stroną ulicy, więc część parkomatów "
        "może trafić do kodu sąsiedniego (po drugiej stronie jezdni). Dla flagi SPP (kod z parkomatem) i bufora "
        "nie ma to znaczenia; dla porównań per parkomat × kod — trzeba o tym pamiętać.",
        "",
        "## Punkty kontrolne",
        "",
        "| punkt | układ | źródło | px x | px y | reszta [m] | LOO [m] |",
        "|---|---|---|---|---|---|---|",
    ]
    for w in t.itertuples():
        L.append(f"| {w.nazwa} | {w.uklad} | {w.zrodlo} | {w.px_x:.0f} | {w.px_y:.0f} | {w.reszta_m:.1f} | {w.loo_m:.1f} |")
    L += [
        "",
        "## Digitalizacja numerów",
        "",
        f"- Kropek na mapie: {stat['kropki']} (w tym wstawka: {stat['wstawka']}).",
        f"- Numer z OCR: {stat['ocr']}, z ręcznego odczytu (`data/raw/zdit/parkomaty_odczyty_reczne.csv`): {stat['manual']}.",
        f"- Kropki bez numeru: {stat['bez_numeru']}.",
        f"- Numery 1–{P.NUMER_MAX} nieobecne na mapie: {', '.join(map(str, wal['brakujace'])) or 'brak'}.",
        f"- Duplikaty: {wal['duplikaty'] or 'brak'}.",
        f"- ID z danych Visa bez lokalizacji: {stat['nieznane']} (status „lokalizacja nieznana”; źródło listy: "
        f"{stat['zrodlo_visa']}). Pipeline łączy po dokładnym ID, więc ID bez litery (nowe parkomaty > 440, "
        "ale też np. `312` obok `312B` z mapy) nie dziedziczy lokalizacji — nie wiemy, czy to to samo urządzenie.",
        "- Wszystkie kropki sprawdzone odczytem wizualnym kafli. Ręczny CSV zawiera tylko te, dla których OCR "
        "nie dał numeru (`brak_ocr`), dał numer sprzeczny lub błędny (`korekta_ocr`) albo segmentacja zgubiła "
        "kropkę przykrytą linią (`kropka_niewykryta`, piksel podany ręcznie).",
        "- Litera w numerze to podstrefa z mapy 2024 (kolor kropki). `podstrefa` w `data/parkomaty.csv` to "
        "podstrefa obecna: A → A, B → B, dawne C (Fabryczna) → B, D (Bałucki Rynek) → C.",
        "",
        "## Kody SPP (`data/spp_kody.csv`)",
        "",
        f"Reguła: kod pocztowy jest kodem SPP, gdy ma co najmniej jeden zlokalizowany parkomat z mapy 2024 "
        f"(kod najbliższego punktu adresowego PRG). Wynik: {stat['kody_spp']} kodów. Pozostałe kody z danych to "
        "bufor. Ograniczenia: mapa nie obejmuje rozszerzenia SPP z 2025 r. (kody z nowych parkomatów wypadają "
        "do bufora), a kody „po drugiej stronie ulicy” bez własnego parkomatu też.",
        "",
    ]
    with open(sciezka, "w") as f:
        f.write("\n".join(L))
    return rmse, rmse_loo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prg", default=None)
    ap.add_argument("--kafle", default=None)
    ap.add_argument("--wyjscie", default=os.path.join(ROOT, "data"))
    a = ap.parse_args()

    im = cv2.imread(MAPA)
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    kr = kropki(hsv)
    et = ramki(hsv)
    ocr = odczyty_ocr(kr, et)
    kr, reczne = odczyty_reczne(kr)
    odczyty = pd.concat([ocr, reczne], ignore_index=True)
    num = P.rozstrzygnij_odczyty(odczyty)
    kr = kr.merge(num, on="kropka", how="left")
    kr["id"] = [P.numer_id(int(n), l) if pd.notna(n) else None for n, l in zip(kr.numer, kr.litera)]
    wal = P.waliduj_numery(kr.numer)
    print(f"kropki {len(kr)}, z numerem {kr.numer.notna().sum()} (ocr {int((kr.zrodlo == 'ocr').sum())}, "
          f"manual {int((kr.zrodlo == 'manual').sum())}), duplikaty {wal['duplikaty']}")
    print("brakujące numery:", wal["brakujace"])
    if a.kafle:
        zapisz_kafle(im, kr, a.kafle)
        print("kropki bez numeru:", kr[kr.numer.isna()][["kropka", "litera", "px_x", "px_y"]].to_string())

    adresy, ulice = wczytaj_prg(a.prg)
    leg = legionow()
    pk = punkty_kontrolne(ulice, kr, leg)
    glowna, wst = pk[pk.uklad == "mapa"], pk[pk.uklad == "wstawka"]
    m = P.dopasuj_afiniczna(glowna[["px_x", "px_y"]].values, glowna[["x", "y"]].values)
    mw = P.dopasuj_podobienstwo(wst[["px_x", "px_y"]].values, wst[["x", "y"]].values)
    bl = P.bledy_georeferencji(glowna[["px_x", "px_y"]].values, glowna[["x", "y"]].values)
    bl_w = P.bledy_georeferencji(wst[["px_x", "px_y"]].values, wst[["x", "y"]].values, P.dopasuj_podobienstwo)

    z = kr.dropna(subset=["numer"]).copy()
    ins = np.array([we_wstawce(x, y) for x, y in zip(z.px_x, z.px_y)])
    xy = np.where(ins[:, None], P.zastosuj_afiniczna(mw, z[["px_x", "px_y"]].values),
                  P.zastosuj_afiniczna(m, z[["px_x", "px_y"]].values))
    z["x"], z["y"] = xy[:, 0], xy[:, 1]
    z["status_lokalizacji"] = np.where(ins, P.STATUS_WSTAWKA, P.STATUS_MAPA)
    for w in leg.itertuples():  # współrzędne ZDiT zamiast transformacji
        x, y = P.do_2180(w.lat, w.lon)
        z.loc[z.id == w.id, ["x", "y", "status_lokalizacji"]] = [float(x), float(y), P.STATUS_ZDIT]

    kod = P.przypisz_kod(z[["x", "y"]].values, np.column_stack([adresy.geometry.x, adresy.geometry.y]),
                         adresy.KOD_POCZT.values, adresy.NAZWA_ULC.values)
    z["kod_pocztowy"], z["odl_adres_m"] = kod.kod_pocztowy.values, kod.odl_adres_m.values
    import geopandas as gpd

    # ulica: najbliższa oś PRG; gdy dalej niż 30 m (place bez osi, np. pl. Dąbrowskiego) — ulica punktu adresowego
    pts = gpd.GeoDataFrame(z[["id"]], geometry=gpd.points_from_xy(z.x, z.y), crs=2180)
    near = gpd.sjoin_nearest(pts, ulice[["NAZWA_ULC", "geometry"]], how="left", distance_col="d") \
        .drop_duplicates("id").set_index("id")
    os_ulicy, d_osi = z.id.map(near.NAZWA_ULC), z.id.map(near.d)
    z["ulica"] = np.where(d_osi <= 30, os_ulicy, kod.ulica_adresu.values)
    lat, lon = P.do_wgs84(z.x, z.y)
    z["lat"], z["lon"] = np.round(lat, 6), np.round(lon, 6)
    z["podstrefa_2024"] = z.litera
    z["podstrefa"] = z.litera.map(P.PODSTREFA_2025)
    z["numer"] = z.id
    z["px_x"], z["px_y"] = z.px_x.round(0).astype(int), z.px_y.round(0).astype(int)
    z["zrodlo_numeru"] = z.zrodlo

    visa, zrodlo_visa = id_visa()
    nieznane = sorted(visa - set(z.numer), key=lambda s: (int(re.match(r"\d+", s).group()), s))
    nz = pd.DataFrame({"numer": nieznane, "status_lokalizacji": P.STATUS_NIEZNANA})
    nz["podstrefa_2024"] = nz.numer.str.extract(r"([A-D])$")[0]
    # podstrefa pusta: bez lokalizacji pipeline sam bierze literę z ID (podstrefa_zrodlo = litera_id)
    kol = ["numer", "podstrefa", "podstrefa_2024", "lat", "lon", "ulica", "kod_pocztowy", "odl_adres_m",
           "status_lokalizacji", "zrodlo_numeru", "px_x", "px_y"]
    z = z.sort_values("numer", key=lambda s: s.str.extract(r"(\d+)")[0].astype(int))
    wynik = pd.concat([z[kol], nz.reindex(columns=kol)], ignore_index=True)
    wynik[["px_x", "px_y"]] = wynik[["px_x", "px_y"]].astype("Int64")
    wynik.to_csv(os.path.join(a.wyjscie, "parkomaty.csv"), index=False)
    spp = P.kody_spp(wynik)
    spp.to_csv(os.path.join(a.wyjscie, "spp_kody.csv"), index=False)

    stat = {"kropki": len(kr), "wstawka": int(sum(we_wstawce(x, y) for x, y in zip(kr.px_x, kr.px_y))),
            "ocr": int((kr.zrodlo == "ocr").sum()), "manual": int((kr.zrodlo == "manual").sum()),
            "bez_numeru": int(kr.numer.isna().sum()), "nieznane": len(nieznane), "zrodlo_visa": zrodlo_visa,
            "kody_spp": len(spp)}
    rmse, rmse_loo = raport(pk, bl, bl_w, m, wal, stat, os.path.join(ROOT, "docs", "parkomaty-georeferencja.md"))
    print(f"georeferencja: RMSE {rmse:.1f} m, LOO RMSE {rmse_loo:.1f} m; parkomaty {len(z)}, "
          f"nieznane {len(nieznane)}, kody SPP {len(spp)}")


if __name__ == "__main__":
    main()
