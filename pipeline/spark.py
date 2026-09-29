"""Wspólna sesja Spark dla pipeline'u (tryb lokalny albo `datasprint`)."""

import os
import sys

from pyspark.sql import SparkSession


os.environ.setdefault("PYSPARK_PYTHON", sys.executable)


def get_spark(app: str = "parkflow", driver_memory: str | None = None) -> SparkSession:
    builder = (
        SparkSession.builder.appName(app)
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", os.environ.get("PARKFLOW_SHUFFLE", "64"))
        .config("spark.sql.parquet.datetimeRebaseModeInWrite", "CORRECTED")
    )
    mem = driver_memory or os.environ.get("PARKFLOW_DRIVER_MEMORY")
    if mem:
        builder = builder.config("spark.driver.memory", mem)
    if not os.environ.get("SPARK_MASTER"):
        builder = builder.master(f"local[{os.environ.get('PARKFLOW_CORES', '*')}]")
    return builder.getOrCreate()
