"""Test dymny schematu wejścia na próbce `datasprint` (pomijany, gdy pliku nie ma).

Czyta tylko metadane i kilkaset wierszy pierwszej grupy wierszy; plik ma ~17,5 GB.
Ścieżka: zmienna PARKFLOW_SAMPLE albo `datasprint_sample_data.parquet` w katalogu repo.
"""

import os
import re

import pytest

from pipeline.aggregate import build_aggregates, load_reference
from pipeline.extract_lodz import COLUMNS, select_lodz
from tests.test_pipeline import SCHEMA

SAMPLE = os.environ.get(
    "PARKFLOW_SAMPLE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datasprint_sample_data.parquet"),
)

pytestmark = pytest.mark.skipif(not os.path.exists(SAMPLE), reason=f"brak próbki datasprint: {SAMPLE}")


def test_sample_has_input_columns_with_types_of_hand_built_tables(spark):
    # Spark czyta tylko stopkę pliku; ręczne tabele w testach mają ten sam schemat co próbka.
    actual = {f.name: f.dataType for f in spark.read.parquet(SAMPLE).schema.fields}
    expected = {f.name: f.dataType for f in SCHEMA.fields}
    assert set(COLUMNS) == set(expected)
    assert {c: actual.get(c) for c in COLUMNS} == expected


def test_pipeline_plan_resolves_on_sample_schema(spark):
    # Tylko plan (bez akcji): kolumny i typy muszą się rozwiązać w obu etapach.
    out = build_aggregates(select_lodz(spark.read.parquet(SAMPLE)), load_reference(spark, "data"))
    assert {"kod", "blok", "sezon", "grupa", "presja"} <= set(out["agg_grupy"].columns)
    for df in out.values():
        assert "card" not in df.columns and "pymt_crd_acct_num_raw" not in df.columns


def test_sample_values_match_parsed_formats():
    import pyarrow.parquet as pq

    batch = next(pq.ParquetFile(SAMPLE).iter_batches(batch_size=500, columns=COLUMNS)).to_pydict()
    assert all(re.fullmatch(r"\d{6}", t) for t in batch["tran_id_gmt_tm"])  # HHMMSS w GMT
    assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) for d in batch["prch_dt"])
    assert set(batch["cp_flag"]) <= {0, 1}
