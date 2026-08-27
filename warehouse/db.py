"""Connection factories for the two DuckDB files standing in for the real
MySQL source and Redshift target -- see docs/adr/001. No Postgres/Redshift
connectivity here; that boundary is enforced at the API level, not just by
convention: `get_source_connection` defaults to read-only.
"""
import duckdb

from warehouse import config

_WAREHOUSE_SCHEMAS = ("raw", "analytics", "audit")

_AUDIT_TABLES = {
    "pipeline_runs": """
        CREATE TABLE IF NOT EXISTS audit.pipeline_runs (
            run_id VARCHAR, step VARCHAR,
            start_time TIMESTAMP, end_time TIMESTAMP,
            status VARCHAR, error_message VARCHAR
        )
    """,
    "watermarks": """
        CREATE TABLE IF NOT EXISTS audit.watermarks (
            table_name VARCHAR PRIMARY KEY,
            last_watermark TIMESTAMP
        )
    """,
    "validation_results": """
        CREATE TABLE IF NOT EXISTS audit.validation_results (
            run_id VARCHAR, table_name VARCHAR, check_type VARCHAR,
            source_value VARCHAR, target_value VARCHAR, passed BOOLEAN,
            checked_at TIMESTAMP DEFAULT current_timestamp
        )
    """,
}


def get_source_connection(read_only=True):
    """The fictional OLTP system. read_only=True for anything that isn't
    data_gen seeding/updating it -- extract.py never opens this writable."""
    config.SOURCE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(config.SOURCE_DB_PATH), read_only=read_only)


def get_target_connection():
    """The Redshift-stand-in warehouse: raw/analytics/audit schemas."""
    config.WAREHOUSE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(config.WAREHOUSE_DB_PATH))
    for schema in _WAREHOUSE_SCHEMAS:
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    for ddl in _AUDIT_TABLES.values():
        con.execute(ddl)
    return con
