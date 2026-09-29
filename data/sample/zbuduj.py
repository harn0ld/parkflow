"""Ręcznie zbudowane przykładowe agregaty w kontrakcie pipeline'u (docs/kontrakt-agregatow.md).

Liczby są zmyślone, ale spójne z regułami pipeline'u:
- presja grupy = karty tygodniowo × współczynnik kierowców × czas wizyty / 60 (samochodo-godziny),
- agg_grupy zawiera tylko grupy z ≥ 30 kartami,
- agg_strefy: karty = Σ kart grup (także < 30), presja = Σ presji grup; < 30 kart → za_malo_danych
  i puste liczby; niektóre komórki w ogóle nie występują (jak w pipeline: brak wizyt → brak wiersza).

Uruchomienie (z katalogu repo):  python data/sample/zbuduj.py
"""

from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent
BLOKI = ["07-10", "10-13", "13-16", "16-19"]
SEZONY = ["lato", "rok_akademicki"]
TYGODNIE = {"lato": 17, "rok_akademicki": 38}

# grupa → (czas wizyty [min], współczynnik kierowców)
GRUPY = {
    "szybkie_uslugi": (15, 0.020),
    "spozywcze_male": (20, 0.025),
    "handel": (45, 0.030),
    "gastronomia": (75, 0.035),
    "uslugi_osobiste": (90, 0.040),
    "rozrywka_kultura": (120, 0.050),
}

# kod → (spp, {grupa: karty przyjezdne w sezonie przy mnożniku 1}, profil bloków, mnożnik lato, mnożnik rok)
KODY = {
    "90-001": (True, {"gastronomia": 220, "handel": 160, "szybkie_uslugi": 120}, "centrum", 1.0, 1.1),
    "90-006": (True, {"spozywcze_male": 140, "gastronomia": 110}, "centrum", 0.9, 1.0),
    "90-057": (True, {"handel": 180, "uslugi_osobiste": 70}, "handel", 0.8, 1.0),
    "90-102": (True, {"gastronomia": 260, "rozrywka_kultura": 90, "szybkie_uslugi": 150}, "wieczor", 1.2, 1.0),
    "90-113": (True, {"gastronomia": 300, "rozrywka_kultura": 120, "handel": 90}, "wieczor", 1.3, 1.0),
    "90-135": (True, {"handel": 120, "szybkie_uslugi": 100}, "centrum", 0.9, 1.0),
    "90-268": (True, {"uslugi_osobiste": 80, "spozywcze_male": 90}, "rano", 0.9, 1.0),
    "90-318": (True, {"szybkie_uslugi": 90, "spozywcze_male": 70}, "rano", 0.8, 1.0),
    "90-361": (True, {"handel": 60, "gastronomia": 50}, "handel", 1.0, 1.0),
    "90-418": (True, {"uslugi_osobiste": 60, "szybkie_uslugi": 60}, "rano", 0.9, 1.0),
    "90-924": (False, {"spozywcze_male": 110, "gastronomia": 90}, "uczelnia", 0.4, 1.4),
    "91-404": (False, {"handel": 140, "spozywcze_male": 60}, "handel", 1.0, 1.0),
    "92-214": (False, {"spozywcze_male": 70, "szybkie_uslugi": 40}, "rano", 1.0, 1.0),
    "93-005": (False, {"spozywcze_male": 40, "szybkie_uslugi": 30}, "rano", 1.0, 0.9),
    "94-010": (False, {"spozywcze_male": 35}, "rano", 0.8, 0.8),
    "91-065": (False, {"gastronomia": 45, "handel": 30}, "wieczor", 0.9, 1.0),
}

# mnożnik kart w blokach 07-10 / 10-13 / 13-16 / 16-19
PROFILE = {
    "centrum": [0.5, 1.0, 1.1, 0.9],
    "handel": [0.3, 1.0, 1.2, 1.1],
    "wieczor": [0.2, 0.7, 1.0, 1.4],
    "rano": [1.2, 1.0, 0.7, 0.5],
    "uczelnia": [0.8, 1.2, 1.1, 0.6],
}

# Komórki pominięte całkowicie (brak wizyt przyjezdnych).
BRAK = {("94-010", "07-10", "lato"), ("94-010", "16-19", "lato"), ("93-005", "16-19", "lato")}


def zbuduj() -> tuple[pd.DataFrame, pd.DataFrame]:
    grupy, strefy = [], []
    for kod, (spp, bazowe, profil, m_lato, m_rok) in KODY.items():
        for sezon, m_sezon in zip(SEZONY, [m_lato, m_rok]):
            for blok, m_blok in zip(BLOKI, PROFILE[profil]):
                if (kod, blok, sezon) in BRAK:
                    continue
                karty_sum, presja_sum = 0, 0.0
                for grupa, baza in bazowe.items():
                    czas, d = GRUPY[grupa]
                    karty = round(baza * m_blok * m_sezon)
                    presja = round(karty / TYGODNIE[sezon] * 5 * d * czas / 60, 6)
                    karty_sum += karty
                    presja_sum += presja
                    if karty >= 30:
                        grupy.append(dict(kod=kod, blok=blok, sezon=sezon, grupa=grupa, karty_przyjezdne=karty,
                                          wspolczynnik_kierowcow=d, mediana_czasu_wizyty_min=float(czas),
                                          presja=presja, spp=spp))
                enough = karty_sum >= 30
                strefy.append(dict(kod=kod, blok=blok, sezon=sezon,
                                   karty_przyjezdne=float(karty_sum) if enough else None,
                                   presja=round(presja_sum, 6) if enough else None,
                                   za_malo_danych=not enough, spp=spp))
    return pd.DataFrame(grupy), pd.DataFrame(strefy).astype({"karty_przyjezdne": float, "presja": float})


# grupa → (wizyty wielotransakcyjne, karty, udział wielotransakcyjnych, mediana zmierzonego czasu [min]);
# rozrywka_kultura poniżej progu 30 kart, więc nie jest eksportowana.
KALIBRACJA = {
    "szybkie_uslugi": (410, 350, 0.06, 12.0),
    "spozywcze_male": (520, 430, 0.08, 18.0),
    "handel": (380, 300, 0.11, 34.0),
    "gastronomia": (640, 520, 0.14, 52.0),
    "uslugi_osobiste": (60, 45, 0.05, 71.0),
}


def zbuduj_kalibracje() -> pd.DataFrame:
    return pd.DataFrame([
        dict(grupa=g, czas_domyslny_min=GRUPY[g][0], wizyty_wielotransakcyjne=w, karty=k,
             udzial_wielotransakcyjnych=u, mediana_czasu_zmierzonego_min=m)
        for g, (w, k, u, m) in KALIBRACJA.items()
    ]).astype({"czas_domyslny_min": "int32"})


def zbuduj_popyt() -> pd.DataFrame:
    """agg_parkomaty_strefy dla kodów SPP: ~30% kart przyjezdnych płaci w parkomatach, ~1,5 h na opłatę."""
    wiersze = []
    for kod, (spp, bazowe, profil, m_lato, m_rok) in KODY.items():
        if not spp:
            continue
        for sezon, m_sezon in zip(SEZONY, [m_lato, m_rok]):
            for blok, m_blok in zip(BLOKI, PROFILE[profil]):
                karty = round(sum(bazowe.values()) * 0.3 * m_blok * m_sezon)
                if karty >= 30:
                    wiersze.append(dict(kod=kod, blok=blok, sezon=sezon,
                                        oplacone_autogodziny=round(karty / TYGODNIE[sezon] * 5 * 1.5, 2), karty=karty))
    return pd.DataFrame(wiersze)


if __name__ == "__main__":
    agg_grupy, agg_strefy = zbuduj()
    agg_strefy.to_parquet(OUT / "agg_strefy.parquet", index=False)
    agg_grupy.to_parquet(OUT / "agg_grupy.parquet", index=False)
    print(f"agg_strefy: {len(agg_strefy)} wierszy ({agg_strefy.za_malo_danych.sum()} za mało danych)")
    print(f"agg_grupy:  {len(agg_grupy)} wierszy")
    kalibracja = zbuduj_kalibracje()
    kalibracja.to_parquet(OUT / "agg_kalibracja_czasow.parquet", index=False)
    print(f"agg_kalibracja_czasow: {len(kalibracja)} wierszy")
    popyt = zbuduj_popyt()
    popyt.to_parquet(OUT / "agg_parkomaty_strefy.parquet", index=False)
    print(f"agg_parkomaty_strefy: {len(popyt)} wierszy")
