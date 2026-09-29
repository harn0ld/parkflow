"""Podgląd wartości kolumn filtrujących w podzbiorze Łodzi (tylko liczności, bez kart).

Użycie:
    python -m pipeline.inspect_lodz data/interim/lodz_all.parquet
    python -m pipeline.inspect_lodz --kody 91-111,93-020   # top sprzedawcy w kodach
"""

import argparse

from pyspark.sql import functions as F

from pipeline.spark import get_spark


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?", default="data/interim/lodz_all.parquet")
    ap.add_argument("--kody", help="kody pocztowe po przecinku")
    args = ap.parse_args()
    spark = get_spark("parkflow-inspect")
    spark.sparkContext.setLogLevel("ERROR")
    df = spark.read.parquet(args.src)
    if args.kody:
        (df.where(F.col("mrch_postal_code").isin(*args.kody.split(",")))
         .groupBy("mrch_postal_code", "mrch_nm_raw", "mrch_catg_cd").count()
         .orderBy(F.desc("count")).show(40, False))
        return
    for c in ["transaction_type", "transaction_pos_entry_mode", "channel_flg", "cp_flag"]:
        df.groupBy(c).count().orderBy(F.desc("count")).show(20, False)
    df.where(F.col("mrch_catg_cd") == 7523).agg(
        F.count("*").alias("n7523"),
        F.sum(F.upper("mrch_nm_raw").rlike(r"^SPP LODZ\s+\d+[A-Z]?").cast("int")).alias("spp"),
    ).show()
    print("brak kodu:", df.where(F.col("mrch_postal_code").isNull()).count())
    df.where(F.col("transaction_type") == "ATM").groupBy("mrch_catg_cd").count().show(5)


if __name__ == "__main__":
    main()
