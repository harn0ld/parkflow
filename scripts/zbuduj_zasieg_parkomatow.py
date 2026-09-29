"""Buduje data/parkomaty_zasieg.csv: parkomat → kody pocztowe w promieniu ~500 m (ticket 08).

Uruchomienie z katalogu repo: `python scripts/zbuduj_zasieg_parkomatow.py [--promien 500]`.
Wejście: data/parkomaty.csv (ticket 06), data/kody.geojson (ticket 02). Logika: `pipeline/zasieg.py`.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.zasieg import PROMIEN_M, zasieg_parkomatow  # noqa: E402

PARKOMATY = ROOT / "data" / "parkomaty.csv"
KODY = ROOT / "data" / "kody.geojson"
WYJSCIE = ROOT / "data" / "parkomaty_zasieg.csv"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--promien", type=float, default=PROMIEN_M, help="promień wokół parkomatu [m]")
    a = ap.parse_args()

    parkomaty = pd.read_csv(PARKOMATY, dtype={"numer": str, "kod_pocztowy": str})
    zasieg = zasieg_parkomatow(parkomaty, gpd.read_file(KODY), a.promien)
    zasieg.to_csv(WYJSCIE, index=False)
    n = zasieg.groupby("numer").size()
    print(f"{WYJSCIE.name}: {len(zasieg)} par, {len(n)}/{len(parkomaty)} parkomatów z zasięgiem, "
          f"kodów na parkomat: mediana {n.median():.0f}, min {n.min()}, max {n.max()}")


if __name__ == "__main__":
    main()
