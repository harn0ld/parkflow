"""Etap 1: pełny plik Visa → podzbiór miasta (poziom karty, zostaje w chronionym środowisku).

Miasto = sklep w Polsce i kod pocztowy z prefiksów miasta po normalizacji, albo brak poprawnego kodu
i nazwa miasta. Łódź: 90-xxx–94-xxx, 95-xxx to okolice (SPEC §2, visa-dane.md).
Kraków: 30-xxx–31-xxx, 32-xxx to okolice (Wieliczka, Skawina).

Użycie:
    python -m pipeline.extract_lodz <wejście.parquet> <wyjście_dir> [--miasto krakow]
"""

import argparse

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from parkflow.miasta import LODZ, MIASTA, Miasto
from pipeline.spark import get_spark

COLUMNS = [
    "tran_id_raw",
    "tran_id_gmt_tm",
    "pymt_crd_acct_num_raw",
    "transaction_type",
    "transaction_pos_entry_mode",
    "mrch_ctry_nm",
    "mrch_nm_raw",
    "mrch_catg_cd",
    "mrch_city_nm_raw",
    "mrch_postal_code",
    "cs_tran_amt",
    "channel_flg",
    "cp_flag",
    "prch_dt",
    "lau_enr",
    "pstl_cd_enr",
]


def normalize_postal(col: Column) -> Column:
    """'93180', '93-180', ' 93 180' → '93-180'; wszystko inne → NULL."""
    digits = F.regexp_replace(col, r"[\s-]", "")
    return F.when(
        digits.rlike(r"^\d{5}$"),
        F.concat(F.substring(digits, 1, 2), F.lit("-"), F.substring(digits, 3, 3)),
    )


def select_city(df: DataFrame, miasto: Miasto) -> DataFrame:
    postal = normalize_postal(F.col("mrch_postal_code"))
    city = F.upper(F.translate(F.trim(F.col("mrch_city_nm_raw")), "łŁóÓźŹ", "lLoOzZ"))
    in_city_postal = F.substring(postal, 1, 2).isin(*miasto.prefiksy_kodow)
    city_no_postal = postal.isNull() & city.startswith(miasto.nazwa_visa)
    return (
        df.select(*COLUMNS)
        .where(F.col("mrch_ctry_nm") == "POLAND")
        .withColumn("mrch_postal_code", postal)
        .withColumn("pstl_cd_enr", normalize_postal(F.col("pstl_cd_enr")))
        .where(in_city_postal | city_no_postal)
    )


def select_lodz(df: DataFrame) -> DataFrame:
    return select_city(df, LODZ)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--miasto", default=LODZ.id, choices=sorted(MIASTA))
    a = ap.parse_args()
    miasto = MIASTA[a.miasto]
    spark = get_spark(f"parkflow-extract-{miasto.id}")
    out = select_city(spark.read.parquet(a.src), miasto)
    out.repartition(16).write.mode("overwrite").parquet(a.dst)
    n = spark.read.parquet(a.dst).count()
    print(f"{miasto.nazwa}: {n:,} transakcji → {a.dst}")


if __name__ == "__main__":
    main()
