import duckdb
import pandas as pd
import pytest

from warehouse.advisor import recommend


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    c.execute("CREATE SCHEMA analytics")
    yield c
    c.close()


def _seed(con, table, df):
    con.register("_stage", df)
    con.execute(f"CREATE TABLE analytics.{table} AS SELECT * FROM _stage")
    con.unregister("_stage")


def test_small_table_gets_diststyle_all(con):
    _seed(con, "dim_crop_type", pd.DataFrame({"crop_type_key": range(1, 9)}))
    rec = recommend(con, "dim_crop_type")
    assert rec.diststyle == "ALL"
    assert rec.distkey is None


def test_high_cardinality_join_key_gets_distkey(con):
    n = 1000
    df = pd.DataFrame({
        "farmer_key": range(n),  # 100% cardinality -- the clear winner
        "plot_key": range(n),
        "crop_type_key": [i % 8 for i in range(n)],
        "node_key": [i % 25 for i in range(n)],
        "date_key": [20260101 + i % 60 for i in range(n)],
    })
    _seed(con, "fact_harvest_transactions", df)
    rec = recommend(con, "fact_harvest_transactions")
    assert rec.diststyle == "KEY"
    assert rec.distkey == "farmer_key"  # first 100%-cardinality column in join_keys order


def test_low_cardinality_join_keys_avoid_distkey_skew(con):
    n = 1000
    df = pd.DataFrame({
        "farmer_key": [1] * n,  # worst case: a single value for every row
        "plot_key": [1, 2] * (n // 2),
        "crop_type_key": [1, 2] * (n // 2),
        "node_key": [1, 2] * (n // 2),
        "date_key": [20260101] * n,
    })
    _seed(con, "fact_harvest_transactions", df)
    rec = recommend(con, "fact_harvest_transactions")
    assert rec.diststyle == "EVEN"
    assert rec.distkey is None


def test_sortkey_uses_range_filter_as_leading_column(con):
    n = 100
    df = pd.DataFrame({
        "farmer_key": range(n), "plot_key": range(n), "crop_type_key": [1] * n,
        "node_key": [1] * n, "date_key": [20260101 + i for i in range(n)],
    })
    _seed(con, "fact_harvest_transactions", df)
    rec = recommend(con, "fact_harvest_transactions")
    assert rec.sortkey_columns[0] == "date_key"
    assert rec.sortkey_type == "COMPOUND"


def test_unknown_table_raises():
    con = duckdb.connect(":memory:")
    with pytest.raises(ValueError):
        recommend(con, "not_a_declared_table")
    con.close()
