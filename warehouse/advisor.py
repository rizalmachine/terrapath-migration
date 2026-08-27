"""Rules-based DISTKEY/SORTKEY advisor -- computes real cardinality/row-count
stats off the DuckDB target stand-in, combined with a small hand-declared
usage profile (which columns are join keys / range-filtered -- domain
knowledge a schema alone can't infer). Standalone CLI, not wired into
pipeline.py -- same "standalone on purpose" precedent as Porto's tagging.py.
See docs/adr/006 for why this is rules-based, not ML.
"""
import argparse
from dataclasses import dataclass, field

from warehouse import db

# In a real engagement this comes from query logs (SVL_QUERY_METRICS / STL_SCAN),
# not a guess -- declared here because this demo has no live cluster to query.
USAGE_PROFILE = {
    "fact_harvest_transactions": {
        "join_keys": ["farmer_key", "plot_key", "crop_type_key", "node_key", "date_key"],
        "range_filter": "date_key",
        "equality_filters": ["node_key", "crop_type_key"],
    },
    "fact_custody_events": {
        "join_keys": ["from_node_key", "to_node_key", "date_key"],
        "range_filter": "date_key",
        "equality_filters": ["event_type"],
    },
    "dim_farmer": {
        "join_keys": ["farmer_key"], "range_filter": None,
        "equality_filters": ["region_id", "is_current"],
    },
    "dim_plot": {
        "join_keys": ["plot_key"], "range_filter": None,
        "equality_filters": ["farmer_id", "is_current"],
    },
    "dim_crop_type": {"join_keys": ["crop_type_key"], "range_filter": None, "equality_filters": []},
    "dim_supply_chain_node": {"join_keys": ["node_key"], "range_filter": None, "equality_filters": ["node_type"]},
    "dim_location": {"join_keys": ["location_key"], "range_filter": None, "equality_filters": []},
    "dim_date": {"join_keys": ["date_key"], "range_filter": None, "equality_filters": []},
}

SMALL_TABLE_ROW_THRESHOLD = 5000
HIGH_CARDINALITY_RATIO = 0.05  # >5% distinct/row_count on a join key -> safe DISTKEY
SKEW_RATIO = 0.01              # <1% distinct/row_count -> DISTKEY would skew badly


@dataclass
class Recommendation:
    table: str
    row_count: int
    distkey: str = None
    diststyle: str = "EVEN"
    sortkey_columns: list = field(default_factory=list)
    sortkey_type: str = "COMPOUND"
    rationale: list = field(default_factory=list)


def _cardinality(con, table, col):
    total, distinct = con.execute(f"SELECT COUNT(*), COUNT(DISTINCT {col}) FROM analytics.{table}").fetchone()
    return total, distinct


def _recommend_dist(con, table, row_count, profile, rec):
    if row_count <= SMALL_TABLE_ROW_THRESHOLD and table.startswith("dim_"):
        rec.diststyle = "ALL"
        rec.rationale.append(
            f"DISTSTYLE ALL: only {row_count:,} rows -- cheaper to replicate to every node than redistribute."
        )
        return

    best_col, best_ratio = None, 0.0
    for col in profile["join_keys"]:
        total, distinct = _cardinality(con, table, col)
        ratio = distinct / total if total else 0
        if ratio > best_ratio:
            best_col, best_ratio = col, ratio

    if best_col and best_ratio >= HIGH_CARDINALITY_RATIO:
        rec.distkey = best_col
        rec.diststyle = "KEY"
        rec.rationale.append(
            f"DISTKEY({best_col}): {best_ratio * 100:.1f}% cardinality "
            f"({int(best_ratio * row_count):,}/{row_count:,}), dominant join column on this fact's queries."
        )
    elif best_col and best_ratio < SKEW_RATIO:
        rec.diststyle = "EVEN"
        rec.rationale.append(
            f"DISTSTYLE EVEN: best join-key candidate ({best_col}) is only "
            f"{best_ratio * 100:.1f}% cardinality -- a DISTKEY here would skew badly onto very few slices."
        )
    else:
        rec.diststyle = "EVEN"
        rec.rationale.append("DISTSTYLE EVEN: no join key clears the cardinality bar for a safe DISTKEY.")


def _recommend_sort(profile, rec):
    if profile["range_filter"]:
        cols = [profile["range_filter"]]
        if profile["equality_filters"]:
            cols.append(profile["equality_filters"][0])
        rec.sortkey_columns, rec.sortkey_type = cols, "COMPOUND"
        second = cols[1] if len(cols) > 1 else None
        rationale = f"COMPOUND SORTKEY({', '.join(cols)}): {profile['range_filter']} is the dominant range filter (leading column)"
        rationale += f", {second} is the next most common equality filter." if second else "."
        rec.rationale.append(rationale)
    elif len(profile["equality_filters"]) >= 3:
        rec.sortkey_columns, rec.sortkey_type = profile["equality_filters"], "INTERLEAVED"
        rec.rationale.append(
            f"INTERLEAVED SORTKEY: filter pattern varies across {len(profile['equality_filters'])} "
            "unrelated columns with no single dominant one -- costs more to VACUUM REINDEX than a compound key."
        )
    elif profile["equality_filters"]:
        rec.sortkey_columns = profile["equality_filters"][:2]
        rec.sortkey_type = "COMPOUND"
        rec.rationale.append(f"COMPOUND SORTKEY({', '.join(rec.sortkey_columns)}): the declared equality filters.")
    else:
        rec.rationale.append("No SORTKEY recommended -- no declared filter pattern for this table.")


def recommend(con, table) -> Recommendation:
    profile = USAGE_PROFILE.get(table)
    if profile is None:
        raise ValueError(f"No usage profile declared for {table} -- add one to advisor.USAGE_PROFILE")

    row_count = con.execute(f"SELECT COUNT(*) FROM analytics.{table}").fetchone()[0]
    rec = Recommendation(table=table, row_count=row_count)
    _recommend_dist(con, table, row_count, profile, rec)
    _recommend_sort(profile, rec)
    return rec


def print_recommendation(rec: Recommendation):
    print(f"=== {rec.table} ({rec.row_count:,} rows) ===")
    dist_line = f"  DISTSTYLE {rec.diststyle}"
    if rec.distkey:
        dist_line += f"  DISTKEY({rec.distkey})"
    print(dist_line)
    if rec.sortkey_columns:
        print(f"  {rec.sortkey_type} SORTKEY({', '.join(rec.sortkey_columns)})")
    for line in rec.rationale:
        print(f"    [ADVISE] {line}")


def main():
    parser = argparse.ArgumentParser(description="Recommend DISTKEY/SORTKEY for a table")
    parser.add_argument("table", nargs="?", default=None)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    con = db.get_target_connection()
    try:
        tables = list(USAGE_PROFILE) if (args.all or not args.table) else [args.table]
        for table in tables:
            print_recommendation(recommend(con, table))
    finally:
        con.close()


if __name__ == "__main__":
    main()
