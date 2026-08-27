from datetime import datetime

import duckdb
import pytest

from warehouse.extract import _load_incremental, _get_watermark


@pytest.fixture
def source_con():
    c = duckdb.connect(":memory:")
    c.execute("CREATE TABLE widgets (widget_id INTEGER, name VARCHAR, updated_at TIMESTAMP)")
    now = datetime(2026, 1, 1)
    c.execute("INSERT INTO widgets VALUES (1, 'a', ?), (2, 'b', ?)", [now, now])
    yield c
    c.close()


@pytest.fixture
def target_con():
    c = duckdb.connect(":memory:")
    c.execute("CREATE SCHEMA raw")
    c.execute("CREATE SCHEMA audit")
    c.execute("CREATE TABLE audit.watermarks (table_name VARCHAR PRIMARY KEY, last_watermark TIMESTAMP)")
    yield c
    c.close()


def test_incremental_load_advances_watermark(source_con, target_con):
    _load_incremental(source_con, target_con, "widgets", ["widget_id"])
    assert target_con.execute("SELECT COUNT(*) FROM raw.widgets").fetchone()[0] == 2
    assert _get_watermark(target_con, "widgets") == datetime(2026, 1, 1)


def test_second_run_with_no_new_rows_pulls_nothing(source_con, target_con, capsys):
    _load_incremental(source_con, target_con, "widgets", ["widget_id"])
    _load_incremental(source_con, target_con, "widgets", ["widget_id"])
    assert target_con.execute("SELECT COUNT(*) FROM raw.widgets").fetchone()[0] == 2  # not duplicated
    assert "[SKIP]" in capsys.readouterr().out


def test_updated_row_replaces_not_duplicates(source_con, target_con):
    _load_incremental(source_con, target_con, "widgets", ["widget_id"])
    source_con.execute("UPDATE widgets SET name = 'a-v2', updated_at = ? WHERE widget_id = 1", [datetime(2026, 1, 2)])
    _load_incremental(source_con, target_con, "widgets", ["widget_id"])

    rows = target_con.execute("SELECT widget_id, name FROM raw.widgets ORDER BY widget_id").fetchdf()
    assert len(rows) == 2
    assert rows.set_index("widget_id").loc[1, "name"] == "a-v2"
