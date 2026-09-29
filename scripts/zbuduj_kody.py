"""Buduje kody.geojson i kody_ulice.csv miasta z punktów adresowych PRG (ticket 02).

Uruchomienie z katalogu repo: `python scripts/zbuduj_kody.py [--miasto krakow] [--prg KATALOG] [--pobierz]`.
Wyjście trafia do katalogu miasta (`parkflow.miasta`): Łódź `data/`, Kraków `data/krakow/`.
KATALOG (domyślnie data/raw/prg/, poza gitem) ma zawierać zip PRG i odpowiedź ULDK z granicą;
brakujące pliki są pobierane. `--pobierz` wymusza świeże pobranie (GUGiK aktualizuje PRG codziennie).

Wyjście:
- data/kody.geojson — kod, geometry (Polygon/MultiPolygon, EPSG:4326, dokładność 1e-6°).
- data/kody_ulice.csv — kod, ulice (krótkie nazwy, „; ”, od najliczniejszej), ulice_pelne,
  liczba_ulic, liczba_adresow, lat, lon (centroid = średnia punktów adresowych).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import geopandas as gpd  # noqa: E402
from pyproj import Transformer  # noqa: E402

from parkflow import prg  # noqa: E402
from parkflow.miasta import LODZ, MIASTA  # noqa: E402
from parkflow.kody import BUFOR_M, UPROSZCZENIE_M, polygony_kodow, ulice_kodow  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--miasto", default=LODZ.id, choices=sorted(MIASTA))
    ap.add_argument("--prg", type=Path, default=prg.KATALOG_PRG, help="katalog z zipem PRG i granicą ULDK")
    ap.add_argument("--pobierz", action="store_true", help="pobierz PRG i granicę od nowa")
    ap.add_argument("--bufor", type=float, default=BUFOR_M, help="bufor wokół punktów [m]")
    ap.add_argument("--uproszczenie", type=float, default=UPROSZCZENIE_M, help="tolerancja uproszczenia [m]")
    a = ap.parse_args()
    miasto = MIASTA[a.miasto]
    kody_geojson, kody_ulice = miasto.kody_geojson, miasto.kody_ulice
    kody_geojson.parent.mkdir(parents=True, exist_ok=True)

    if a.pobierz or not prg.ma_dane(a.prg, miasto):
        prg.pobierz(a.prg, nadpisz=a.pobierz, m=miasto)
    punkty = prg.wczytaj_punkty(a.prg, miasto)
    granica = prg.wczytaj_granice(a.prg, miasto)
    print(f"{len(punkty)} punktów adresowych, {punkty['kod'].nunique()} kodów")

    xy = punkty.assign(x=punkty.geometry.x, y=punkty.geometry.y)
    pelne = ulice_kodow(xy, "ulica")
    krotkie = ulice_kodow(xy, "ulica_krotka")[["kod", "ulice"]]
    lon, lat = Transformer.from_crs(prg.UKLAD, 4326, always_xy=True).transform(pelne["x"].values, pelne["y"].values)
    tabela = (pelne.rename(columns={"ulice": "ulice_pelne"}).merge(krotkie, on="kod")
              .assign(lat=lat.round(6), lon=lon.round(6)))
    tabela = tabela[["kod", "ulice", "ulice_pelne", "liczba_ulic", "liczba_adresow", "lat", "lon"]]
    tabela.to_csv(kody_ulice, index=False)

    kody = polygony_kodow(punkty[["kod", "geometry"]], granica, a.bufor, a.uproszczenie).to_crs(4326)
    kody = gpd.GeoDataFrame(kody, geometry=kody.geometry.set_precision(1e-6))
    kody_geojson.unlink(missing_ok=True)
    kody.to_file(kody_geojson, driver="GeoJSON", layer_options={"RFC7946": "YES", "COORDINATE_PRECISION": 6})

    brak = sorted(set(tabela["kod"]) - set(kody["kod"]))
    print(f"{kody_ulice.name}: {len(tabela)} kodów; {kody_geojson.name}: {len(kody)} kodów, "
          f"{kody_geojson.stat().st_size / 1e6:.1f} MB" + (f"; bez polygonu: {', '.join(brak)}" if brak else ""))


if __name__ == "__main__":
    main()
