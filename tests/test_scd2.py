import duckdb
import pandas as pd
import pytest

from warehouse.scd2 import apply_scd2, resolve_scd2_key, INCEPTION, FAR_FUTURE


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    c.execute("CREATE SCHEMA analytics")
    yield c
    c.close()


def test_first_build_uses_inception_not_as_of(con):
    incoming = pd.DataFrame({"code": ["A", "B"], "region": [1, 2]})
    n_new, n_expired = apply_scd2(con, "dim_x", "x_key", "code", incoming, ["region"], pd.Timestamp("2026-08-27"))
    assert (n_new, n_expired) == (2, 0)
    out = con.execute("SELECT * FROM analytics.dim_x").fetchdf()
    assert (out["valid_from"] == INCEPTION).all()  # not as_of -- see the bug this fixes
    assert (out["valid_to"] == FAR_FUTURE).all()
    assert out["is_current"].all()


def test_unchanged_row_is_a_noop(con):
    incoming = pd.DataFrame({"code": ["A"], "region": [1]})
    apply_scd2(con, "dim_x", "x_key", "code", incoming, ["region"], pd.Timestamp("2026-01-01"))
    n_new, n_expired = apply_scd2(con, "dim_x", "x_key", "code", incoming, ["region"], pd.Timestamp("2026-02-01"))
    assert (n_new, n_expired) == (0, 0)
    assert con.execute("SELECT COUNT(*) FROM analytics.dim_x").fetchone()[0] == 1


def test_changed_attribute_expires_old_and_inserts_new_version(con):
    apply_scd2(con, "dim_x", "x_key", "code",
               pd.DataFrame({"code": ["A"], "region": [1]}), ["region"], pd.Timestamp("2026-01-01"))
    as_of2 = pd.Timestamp("2026-03-01")
    n_new, n_expired = apply_scd2(con, "dim_x", "x_key", "code",
                                   pd.DataFrame({"code": ["A"], "region": [2]}), ["region"], as_of2)
    assert (n_new, n_expired) == (1, 1)

    rows = con.execute("SELECT x_key, region, valid_from, valid_to, is_current FROM analytics.dim_x ORDER BY x_key").fetchdf()
    assert len(rows) == 2
    old, new = rows.iloc[0], rows.iloc[1]
    assert not old["is_current"] and old["valid_to"] == as_of2
    assert new["is_current"] and new["valid_from"] == as_of2 and new["valid_to"] == FAR_FUTURE


def test_natural_key_coercion_matches_across_numeric_and_string_types(con):
    """Regression: a numeric-looking natural key must match whether it comes
    back as int64 or str -- the SCD2 side of Porto's original patch_by_key bug."""
    apply_scd2(con, "dim_x", "x_key", "code",
               pd.DataFrame({"code": [700001], "region": [1]}), ["region"], pd.Timestamp("2026-01-01"))
    n_new, n_expired = apply_scd2(con, "dim_x", "x_key", "code",
                                   pd.DataFrame({"code": ["700001"], "region": [1]}), ["region"], pd.Timestamp("2026-02-01"))
    assert (n_new, n_expired) == (0, 0)  # same key, same value -- must be a no-op, not a "new" key


def test_resolve_scd2_key_point_in_time(con):
    dim = pd.DataFrame({
        "x_key": [1, 2],
        "code": ["700001", "700001"],
        "valid_from": [INCEPTION, pd.Timestamp("2026-06-01")],
        "valid_to": [pd.Timestamp("2026-06-01"), FAR_FUTURE],
    })
    con.register("_stage", dim)
    con.execute("CREATE TABLE analytics.dim_x AS SELECT * FROM _stage")
    con.unregister("_stage")

    fact = pd.DataFrame({
        "tx_id": [1, 2],
        "code": [700001, 700001],  # int, deliberately not str -- proves coercion works
        "tx_date": [pd.Timestamp("2026-01-15"), pd.Timestamp("2026-07-01")],
    })
    out = resolve_scd2_key(con, "dim_x", "x_key", "code", fact, "code", "tx_date").set_index("tx_id")
    assert out.loc[1, "x_key"] == 1  # before the version change
    assert out.loc[2, "x_key"] == 2  # after the version change
