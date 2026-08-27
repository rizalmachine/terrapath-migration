import duckdb
import pandas as pd
import pytest

from warehouse.validate import validate_table


@pytest.fixture
def dbs():
    source = duckdb.connect(":memory:")
    target = duckdb.connect(":memory:")
    target.execute("CREATE SCHEMA raw")
    target.execute("CREATE SCHEMA audit")
    target.execute("""
        CREATE TABLE audit.validation_results (
            run_id VARCHAR, table_name VARCHAR, check_type VARCHAR,
            source_value VARCHAR, target_value VARCHAR, passed BOOLEAN
        )
    """)
    yield source, target
    source.close()
    target.close()


def _seed(con, schema_table, df):
    con.register("_stage", df)
    con.execute(f"CREATE TABLE {schema_table} AS SELECT * FROM _stage")
    con.unregister("_stage")


def test_matching_tables_pass_both_checks(dbs):
    source, target = dbs
    df = pd.DataFrame({"id": [1, 2, 3], "value": ["a", "b", "c"]})
    _seed(source, "widgets", df)
    _seed(target, "raw.widgets", df)

    count_ok, hash_ok = validate_table(source, target, "widgets", "run-1")
    assert count_ok and hash_ok


def test_row_count_mismatch_is_caught(dbs):
    source, target = dbs
    _seed(source, "widgets", pd.DataFrame({"id": [1, 2, 3], "value": ["a", "b", "c"]}))
    _seed(target, "raw.widgets", pd.DataFrame({"id": [1, 2], "value": ["a", "b"]}))

    count_ok, hash_ok = validate_table(source, target, "widgets", "run-1")
    assert not count_ok
    assert not hash_ok


def test_silent_value_change_is_caught_by_hash_not_count(dbs):
    """Same row count, different content -- the failure mode a watermark-only
    (or count-only) check would miss entirely."""
    source, target = dbs
    _seed(source, "widgets", pd.DataFrame({"id": [1, 2], "value": ["a", "TAMPERED"]}))
    _seed(target, "raw.widgets", pd.DataFrame({"id": [1, 2], "value": ["a", "b"]}))

    count_ok, hash_ok = validate_table(source, target, "widgets", "run-1")
    assert count_ok
    assert not hash_ok
