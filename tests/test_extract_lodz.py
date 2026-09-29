"""Etap 1: wybór transakcji Łodzi z pełnego pliku Visa."""

import pytest

from pipeline.extract_lodz import select_lodz
from tests.test_pipeline import SCHEMA, tx

NO_CODE = "brak_kodu"


@pytest.mark.parametrize("kod,country,city,expected", [
    ("90001", "POLAND", "LODZ", "90-001"),
    ("94-100", "POLAND", "LODZ", "94-100"),
    (" 93 180", "POLAND", "LODZ", "93-180"),
    ("95-100", "POLAND", "ZGIERZ", None),   # okolice Łodzi
    ("95100", "POLAND", "LODZ", None),      # 95-xxx odpada nawet z miastem LODZ
    ("90015", "ITALY", "CEFALU", None),     # włoski kod łapany przez 9[0-4]xxx
    ("90-001", "GERMANY", "BERLIN", None),
    (None, "POLAND", "Łódź", NO_CODE),      # brak kodu, miasto Łódź
    ("ABC", "POLAND", "LODZ 1", NO_CODE),   # niepoprawny kod, miasto Łódź
    (None, "POLAND", "ZGIERZ", None),
])
def test_lodz_is_polish_postal_90_to_94_or_city_without_code(spark, kod, country, city, expected):
    df = spark.createDataFrame([tx("c1", "083000", kod=kod, country=country, city=city)], SCHEMA)
    out = [r.mrch_postal_code for r in select_lodz(df).collect()]
    assert out == ([] if expected is None else [None if expected == NO_CODE else expected])


def test_home_postal_code_is_normalized_like_merchant_code(spark):
    df = spark.createDataFrame([tx("c1", "083000", kod="90001", home="95100")], SCHEMA)
    [r] = select_lodz(df).collect()
    assert r.pstl_cd_enr == "95-100"


def test_krakow_postal_prefixes_and_city_without_postal(spark):
    from parkflow.miasta import KRAKOW
    from pipeline.extract_lodz import select_city

    rows = [tx("c1", "080000", kod=k, city=c) for k, c in
            [("31061", "KRAKOW"), ("30-418", "KRAKOW"), ("32-020", "WIELICZKA"), (None, "Kraków"), ("90-001", "LODZ")]]
    df = spark.createDataFrame(rows, SCHEMA)
    out = sorted((r.mrch_postal_code or "", r.mrch_city_nm_raw) for r in select_city(df, KRAKOW).collect())
    assert out == [("", "Kraków"), ("30-418", "KRAKOW"), ("31-061", "KRAKOW")]
