"""Shared SCD Type 2 machinery: versioning dimension rows with
valid_from/valid_to/is_current, and resolving the point-in-time surrogate key
a fact row should join to. See docs/adr/005.

Natural keys are coerced to str on both sides before comparing -- generalizes
Porto's real patch_by_key bug: a numeric-looking key silently becomes int64 on
a naive round-trip through pandas/DuckDB, breaking every match.
"""
import pandas as pd

FAR_FUTURE = pd.Timestamp("9999-12-31")
INCEPTION = pd.Timestamp("1900-01-01")


def _table_exists(con, table):
    return con.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema='analytics' AND table_name=?", [table]
    ).fetchone() is not None


def apply_scd2(con, dim_table, key_col, natural_key, incoming_df, tracked_cols, as_of):
    """incoming_df: a current-state snapshot from the raw layer (one row per
    natural_key -- the latest known state of every entity, not just what
    changed this run). Returns (n_new_versions, n_expired)."""
    incoming_df = incoming_df.reset_index(drop=True).copy()
    incoming_df[natural_key] = incoming_df[natural_key].astype(str)

    if not _table_exists(con, dim_table):
        # Historical backfill, not a live change -- valid_from must predate every
        # existing fact row (INCEPTION), not "as_of"/now, or every historical fact
        # fails to resolve in the point-in-time join (found while building this).
        new_rows = incoming_df.copy()
        new_rows.insert(0, key_col, range(1, len(new_rows) + 1))
        new_rows["valid_from"] = INCEPTION
        new_rows["valid_to"] = FAR_FUTURE
        new_rows["is_current"] = True
        con.register("_stage", new_rows)
        con.execute(f"CREATE TABLE analytics.{dim_table} AS SELECT * FROM _stage")
        con.unregister("_stage")
        return len(new_rows), 0

    current = con.execute(f"SELECT * FROM analytics.{dim_table} WHERE is_current = TRUE").fetchdf()
    current[natural_key] = current[natural_key].astype(str)
    current_by_key = current.set_index(natural_key)
    next_key = con.execute(f"SELECT MAX({key_col}) FROM analytics.{dim_table}").fetchone()[0] + 1

    # Brand-new natural keys get INCEPTION (we don't know when they "really"
    # started, and their own facts may predate this run); only a genuinely
    # detected attribute change gets valid_from=as_of ("as of this run, we
    # observed a change").
    to_insert_new = []
    to_insert_changed = []
    to_expire = []
    for _, row in incoming_df.iterrows():
        nk = row[natural_key]
        if nk not in current_by_key.index:
            to_insert_new.append(row)
            continue
        cur_row = current_by_key.loc[nk]
        if any(str(row[c]) != str(cur_row[c]) for c in tracked_cols):
            to_expire.append(nk)
            to_insert_changed.append(row)

    if to_expire:
        con.register("_expire_keys", pd.DataFrame({natural_key: to_expire}))
        con.execute(f"""
            UPDATE analytics.{dim_table}
            SET valid_to = ?, is_current = FALSE
            WHERE is_current = TRUE AND {natural_key} IN (SELECT {natural_key} FROM _expire_keys)
        """, [as_of])
        con.unregister("_expire_keys")

    def _insert_batch(rows, valid_from_value):
        nonlocal next_key
        if not rows:
            return
        new_rows = pd.DataFrame(rows).reset_index(drop=True)
        new_rows.insert(0, key_col, range(next_key, next_key + len(new_rows)))
        new_rows["valid_from"] = valid_from_value
        new_rows["valid_to"] = FAR_FUTURE
        new_rows["is_current"] = True
        con.register("_stage", new_rows)
        con.execute(f"INSERT INTO analytics.{dim_table} SELECT * FROM _stage")
        con.unregister("_stage")
        next_key += len(new_rows)

    _insert_batch(to_insert_new, INCEPTION)
    _insert_batch(to_insert_changed, as_of)

    return len(to_insert_new) + len(to_insert_changed), len(to_expire)


def resolve_scd2_key(con, dim_table, key_col, natural_key, fact_df, fact_natural_key_col, fact_date_col):
    """Point-in-time join: for each fact row, find the dim version valid at
    fact_date_col -- never 'whichever version is current right now'."""
    fact_df = fact_df.copy()
    fact_df[fact_natural_key_col] = fact_df[fact_natural_key_col].astype(str)

    dim = con.execute(f"SELECT {key_col}, {natural_key}, valid_from, valid_to FROM analytics.{dim_table}").fetchdf()
    dim[natural_key] = dim[natural_key].astype(str)

    con.register("_fact", fact_df)
    con.register("_dim", dim)
    result = con.execute(f"""
        SELECT _fact.*, _dim.{key_col}
        FROM _fact
        LEFT JOIN _dim
          ON _fact.{fact_natural_key_col} = _dim.{natural_key}
         AND _fact.{fact_date_col} >= _dim.valid_from
         AND _fact.{fact_date_col} < _dim.valid_to
    """).fetchdf()
    con.unregister("_fact")
    con.unregister("_dim")
    return result
