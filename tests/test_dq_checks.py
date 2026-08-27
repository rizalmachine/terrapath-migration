import duckdb
import pandas as pd
import pytest

from warehouse.dq_checks import find_duplicate_farmer_candidates


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    c.execute("CREATE SCHEMA raw")
    yield c
    c.close()


def test_finds_seeded_duplicate(con):
    df = pd.DataFrame({
        "farmer_id": [1, 2, 3],
        "farmer_code": ["700001", "700002", "700003"],
        "national_id": ["1111", "2222", "1111"],  # farmer 1 and 3 share a national_id
    })
    con.register("_stage", df)
    con.execute("CREATE TABLE raw.farmers AS SELECT * FROM _stage")
    con.unregister("_stage")

    out = find_duplicate_farmer_candidates(con)
    assert len(out) == 1
    assert out.iloc[0]["national_id"] == "1111"
    assert out.iloc[0]["occurrence_count"] == 2


def test_no_false_positive_on_unique_ids(con):
    df = pd.DataFrame({
        "farmer_id": [1, 2],
        "farmer_code": ["700001", "700002"],
        "national_id": ["1111", "2222"],
    })
    con.register("_stage", df)
    con.execute("CREATE TABLE raw.farmers AS SELECT * FROM _stage")
    con.unregister("_stage")

    assert len(find_duplicate_farmer_candidates(con)) == 0
