"""Etap 1: pełny plik Visa → podzbiór Łodzi (poziom karty, zostaje w chronionym środowisku).

Łódź = sklep w Polsce i kod 90-xxx–94-xxx po normalizacji, albo brak poprawnego kodu
i miasto „LODZ”. Kody 95-xxx odrzucamy (SPEC §2, visa-dane.md).

Użycie:
    python -m pipeline.extract_lodz <wejście.parquet> <wyjście_dir>
"""

import sys

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

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


def select_lodz(df: DataFrame) -> DataFrame:
    postal = normalize_postal(F.col("mrch_postal_code"))
    city = F.upper(F.translate(F.trim(F.col("mrch_city_nm_raw")), "łŁóÓźŹ", "lLoOzZ"))
    in_lodz_postal = F.substring(postal, 1, 2).isin("90", "91", "92", "93", "94")
    lodz_city_no_postal = postal.isNull() & city.startswith("LODZ")
    return (
        df.select(*COLUMNS)
        .where(F.col("mrch_ctry_nm") == "POLAND")
        .withColumn("mrch_postal_code", postal)
        .withColumn("pstl_cd_enr", normalize_postal(F.col("pstl_cd_enr")))
        .where(in_lodz_postal | lodz_city_no_postal)
    )


def main(src: str, dst: str) -> None:
    spark = get_spark("parkflow-extract-lodz")
    out = select_lodz(spark.read.parquet(src))
    out.repartition(16).write.mode("overwrite").parquet(dst)
    n = spark.read.parquet(dst).count()
    print(f"Łódź: {n:,} transakcji → {dst}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
