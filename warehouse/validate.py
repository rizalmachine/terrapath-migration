"""Row-count and checksum reconciliation between source and the raw layer.

Row-count alone misses a real failure mode: a source mutation that doesn't
bump `updated_at` is invisible to watermark-based extraction, but an
order-independent row-hash checksum catches it immediately. Results logged to
audit.validation_results.
"""
import hashlib
import uuid

from warehouse import config, db


def _row_hash_xor(con, table):
    """Order-independent checksum: hash each row, XOR-fold across rows -- so
    row order (which extract.py makes no promises about) never matters."""
    df = con.execute(f"SELECT * FROM {table}").fetchdf()
    if df.empty:
        return 0
    # astype(object) first -- nullable Int/datetime dtypes reject "" via fillna
    # directly; going through plain object dtype avoids that, then astype(str)
    # stringifies whatever's left (ints, Timestamps, already-"" gaps) uniformly.
    df = df.astype(object).where(df.notna(), "")
    row_strs = df.astype(str).agg("|".join, axis=1)
    acc = 0
    for s in row_strs:
        h = int(hashlib.sha256(s.encode()).hexdigest(), 16) & 0xFFFFFFFFFFFFFFFF
        acc ^= h
    return acc


def validate_table(source_con, target_con, table, run_id):
    source_count = source_con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    target_count = target_con.execute(f"SELECT COUNT(*) FROM raw.{table}").fetchone()[0]
    count_passed = source_count == target_count

    source_hash = _row_hash_xor(source_con, table)
    target_hash = _row_hash_xor(target_con, f"raw.{table}")
    hash_passed = source_hash == target_hash

    for check_type, source_val, target_val, passed in [
        ("row_count", source_count, target_count, count_passed),
        ("row_hash", source_hash, target_hash, hash_passed),
    ]:
        target_con.execute(
            """INSERT INTO audit.validation_results
               (run_id, table_name, check_type, source_value, target_value, passed)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [run_id, table, check_type, str(source_val), str(target_val), passed],
        )
    return count_passed, hash_passed


def run(con=None, run_id=None):
    own_con = con is None
    target_con = con or db.get_target_connection()
    source_con = db.get_source_connection(read_only=True)
    run_id = run_id or str(uuid.uuid4())
    all_passed = True
    try:
        for table in config.SOURCE_TABLES:
            count_ok, hash_ok = validate_table(source_con, target_con, table, run_id)
            status = "OK" if (count_ok and hash_ok) else "MISMATCH"
            print(f"    [{status}] {table}: count_match={count_ok} hash_match={hash_ok}")
            all_passed = all_passed and count_ok and hash_ok
    finally:
        source_con.close()
        if own_con:
            target_con.close()
    return all_passed
