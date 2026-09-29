import os
import sys

import pytest

os.environ.setdefault("PYSPARK_PYTHON", sys.executable)


@pytest.fixture(scope="session")
def spark():
    from pyspark.sql import SparkSession

    s = SparkSession.builder.master("local[2]").config("spark.sql.session.timeZone", "UTC") \
        .config("spark.sql.shuffle.partitions", "4").config("spark.ui.enabled", "false").getOrCreate()
    yield s
    s.stop()


@pytest.fixture(autouse=True)
def _wyczysc_cache_sparka(request):
    """build_aggregates cache'uje DataFrame'y; bez czyszczenia pełny zestaw testów kończy się OOM lokalnego Sparka."""
    yield
    if "spark" in request.fixturenames:
        request.getfixturevalue("spark").catalog.clearCache()
