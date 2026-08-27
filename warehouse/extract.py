"""Raw layer: watermark-based incremental pull from the source system for the
6 transactional tables, always-replace for the 4 small lookups -- same split
Porto used for staging vs reference. Idempotent via delete-then-insert scoped
by the staged batch's key columns (not just "append past the watermark"), so
re-running the same window never duplicates.
"""
from datetime import datetime

from warehouse import config, db

_EPOCH = datetime(2000, 1, 1)


def _get_watermark(target_con, table):
    row = target_con.execute(
        "SELECT last_watermark FROM audit.watermarks WHERE table_name = ?", [table]
    ).fetchone()
    return row[0] if row else _EPOCH


def _set_watermark(target_con, table, value):
    target_con.execute(
        """INSERT INTO audit.watermarks (table_name, last_watermark) VALUES (?, ?)
           ON CONFLICT (table_name) DO UPDATE SET last_watermark = EXCLUDED.last_watermark""",
        [table, value],
    )


def _delete_matching(target_con, table, df, key_cols):
    target_con.register("_keys", df[key_cols].drop_duplicates())
    conditions = " AND ".join(f"raw.{table}.{c} = _keys.{c}" for c in key_cols)
    target_con.execute(f"DELETE FROM raw.{table} USING _keys WHERE {conditions}")
    target_con.unregister("_keys")


def _load_incremental(source_con, target_con, table, key_cols):
    watermark = _get_watermark(target_con, table)
    df = source_con.execute(f"SELECT * FROM {table} WHERE updated_at > ?", [watermark]).fetchdf()
    if df.empty:
        print(f"    [SKIP] {table}: no rows past watermark {watermark}")
        return

    exists = target_con.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema='raw' AND table_name=?", [table]
    ).fetchone() is not None
    if not exists:
        target_con.register("_stage", df)
        target_con.execute(f"CREATE TABLE raw.{table} AS SELECT * FROM _stage WHERE 1=0")
        target_con.unregister("_stage")

    _delete_matching(target_con, table, df, key_cols)

    target_con.register("_stage", df)
    target_con.execute(f"INSERT INTO raw.{table} SELECT * FROM _stage")
    target_con.unregister("_stage")

    new_watermark = df["updated_at"].max()
    _set_watermark(target_con, table, new_watermark)
    print(f"    [LOAD] raw.{table} += {len(df)} rows (watermark -> {new_watermark})")


def _load_full_replace(source_con, target_con, table):
    df = source_con.execute(f"SELECT * FROM {table}").fetchdf()
    target_con.register("_stage", df)
    target_con.execute(f"CREATE OR REPLACE TABLE raw.{table} AS SELECT * FROM _stage")
    target_con.unregister("_stage")
    print(f"    [LOAD] raw.{table} <- {len(df)} rows (always-replace)")


def run(con=None):
    own_con = con is None
    target_con = con or db.get_target_connection()
    source_con = db.get_source_connection(read_only=True)
    try:
        for table, meta in config.SOURCE_TABLES.items():
            if meta["incremental"]:
                _load_incremental(source_con, target_con, table, meta["key_cols"])
            else:
                _load_full_replace(source_con, target_con, table)
    finally:
        source_con.close()
        if own_con:
            target_con.close()
