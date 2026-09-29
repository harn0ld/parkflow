"""Buduje parkomaty_zasieg.csv miasta: parkomat → kody pocztowe w promieniu ~500 m (ticket 08).

Uruchomienie z katalogu repo: `python scripts/zbuduj_zasieg_parkomatow.py [--miasto krakow] [--promien 500]`.
Wejście z katalogu miasta: parkomaty.csv (ticket 06), kody.geojson (ticket 02). Logika: `pipeline/zasieg.py`.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402

from parkflow.miasta import LODZ, MIASTA  # noqa: E402
from pipeline.zasieg import PROMIEN_M, zasieg_parkomatow  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--miasto", default=LODZ.id, choices=sorted(MIASTA))
    ap.add_argument("--promien", type=float, default=PROMIEN_M, help="promień wokół parkomatu [m]")
    a = ap.parse_args()
    miasto = MIASTA[a.miasto]
    wyjscie = miasto.parkomaty_zasieg

    parkomaty = pd.read_csv(miasto.parkomaty, dtype={"numer": str, "kod_pocztowy": str})
    zasieg = zasieg_parkomatow(parkomaty, gpd.read_file(miasto.kody_geojson), a.promien)
    zasieg.to_csv(wyjscie, index=False)
    n = zasieg.groupby("numer").size()
    print(f"{miasto.nazwa} {wyjscie.name}: {len(zasieg)} par, {len(n)}/{len(parkomaty)} parkomatów z zasięgiem, "
          f"kodów na parkomat: mediana {n.median():.0f}, min {n.min()}, max {n.max()}")


if __name__ == "__main__":
    main()
