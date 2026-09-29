"""Kraków: parkomaty.xml ZDMK → data/krakow/parkomaty.csv + data/krakow/spp_kody.csv.

Uruchomienie z katalogu repo: `python scripts/zbuduj_parkomaty_krakow.py [--pobierz]`.
Wejście: data/raw/krakow/parkomaty.xml (plik mapy parkomatów ZDMK, `--pobierz` ściąga go od nowa)
i punkty adresowe PRG Krakowa (data/raw/prg/, jak w `scripts/zbuduj_kody.py --miasto krakow`).
Kod pocztowy parkomatu = kod najbliższego punktu adresowego PRG, tak samo jak w Łodzi.
Kody SPP = kody z ≥ 1 parkomatem.
"""

import argparse
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from parkflow import prg  # noqa: E402
from parkflow.miasta import KRAKOW  # noqa: E402
from pipeline import parkomaty as P  # noqa: E402

URL_XML = "https://zdmk.krakow.pl/wp-content/themes/justidea_theme/assets/xml/parkomaty.xml"
XML = ROOT / "data" / "raw" / "krakow" / "parkomaty.xml"
KOLUMNY = ["numer", "podstrefa", "podstrefa_2024", "lat", "lon", "ulica", "kod_pocztowy", "odl_adres_m",
           "status_lokalizacji", "sektor", "model", "karta"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pobierz", action="store_true", help="pobierz parkomaty.xml z ZDMK od nowa")
    ap.add_argument("--prg", type=Path, default=prg.KATALOG_PRG, help="katalog z zipem PRG i granicą ULDK")
    a = ap.parse_args()

    if a.pobierz or not XML.exists():
        XML.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(URL_XML, headers={"User-Agent": "Mozilla/5.0"})
        XML.write_bytes(urllib.request.urlopen(req).read())
        print(f"pobrano {URL_XML}")
    if not prg.ma_dane(a.prg, KRAKOW):
        prg.pobierz(a.prg, m=KRAKOW)

    p = P.parsuj_zdmk(XML.read_bytes())
    adresy = prg.wczytaj_punkty(a.prg, KRAKOW)
    x, y = P.do_2180(p["lat"].to_numpy(), p["lon"].to_numpy())
    kod = P.przypisz_kod(np.column_stack([x, y]), np.column_stack([adresy.geometry.x, adresy.geometry.y]),
                         adresy["kod"].to_numpy())
    p["kod_pocztowy"], p["odl_adres_m"] = kod["kod_pocztowy"].to_numpy(), kod["odl_adres_m"].to_numpy()
    p["ulica"] = p["adres"]
    p["podstrefa_2024"] = None
    p["status_lokalizacji"] = P.STATUS_ZDMK
    p[["lat", "lon"]] = p[["lat", "lon"]].round(6)
    p = p.sort_values("numer", key=lambda s: s.astype(int))[KOLUMNY]

    KRAKOW.katalog.mkdir(parents=True, exist_ok=True)
    p.to_csv(KRAKOW.parkomaty, index=False)
    spp = P.kody_spp(p)
    spp.to_csv(KRAKOW.katalog / "spp_kody.csv", index=False)
    daleko = int((p["odl_adres_m"] > 100).sum())
    print(f"{KRAKOW.parkomaty.name}: {len(p)} parkomatów, podstrefy {p['podstrefa'].value_counts().to_dict()}; "
          f"spp_kody.csv: {len(spp)} kodów; > 100 m od adresu PRG: {daleko}")


if __name__ == "__main__":
    main()
