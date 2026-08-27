"""Data-quality checks. Standalone, not wired into pipeline.py's steps --
flags issues for a human to review, never auto-merges records. Same
"standalone on purpose" precedent as Porto's tagging.py.
"""


def find_duplicate_farmer_candidates(con):
    """Farmers sharing a national_id under different farmer_id/farmer_code --
    a real re-registration pattern, not something to silently resolve."""
    return con.execute("""
        SELECT national_id, COUNT(*) AS occurrence_count,
               STRING_AGG(farmer_code, ', ') AS farmer_codes
        FROM raw.farmers
        GROUP BY national_id
        HAVING COUNT(*) > 1
        ORDER BY occurrence_count DESC
    """).fetchdf()
