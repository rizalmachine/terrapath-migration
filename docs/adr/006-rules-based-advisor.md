# ADR-006: The DISTKEY/SORTKEY advisor is rules-based, not ML

## Context

Choosing a Redshift table's distribution and sort strategy is exactly the
kind of decision a migration accelerator should help make faster and more
consistently -- and exactly the kind of decision that's easy to fake with a
model that sounds confident and can't explain itself.

## Decision

`warehouse/advisor.py` computes real statistics off the actual data (row
counts, join-key cardinality via `COUNT(DISTINCT col)`) and combines them
with a small, explicit, hand-declared usage profile per table (which columns
are join keys, which are range- or equality-filtered). Every recommendation
carries a rationale line that names the real numbers it was based on --
`"DISTKEY(farmer_key): 61.0% cardinality (288/472), dominant join column"`
-- not just a verdict.

The rules: a small dimension gets `DISTSTYLE ALL` (cheaper to replicate than
redistribute); a fact/large-dim table's highest-cardinality declared join key
becomes `DISTKEY` if it clears a cardinality floor, otherwise `DISTSTYLE EVEN`
with an explicit skew warning if the best candidate is dangerously
low-cardinality; the dominant range filter leads a `COMPOUND SORTKEY`, with
`INTERLEAVED` recommended (and its `VACUUM REINDEX` cost flagged) only when
three or more unrelated columns are all commonly filtered.

`warehouse/ddl_generator.py` turns a recommendation into real, syntactically
valid Redshift DDL + `COPY` text -- never executed, so this needs zero AWS
SDK dependency and is fully unit-testable via string assertions
(`tests/test_ddl_generator.py`).

## Consequences

The usage profile (`USAGE_PROFILE` in `advisor.py`) is hand-declared, not
learned from real query logs -- in a real engagement this comes from
`SVL_QUERY_METRICS`/`STL_SCAN`, not a guess, and that's an explicit,
acknowledged gap here, not a claim this demo proves optimal choices. The
advisor also doesn't yet flag when its own `DISTKEY` and `SORTKEY`
recommendations for the same table overlap (a real anti-pattern, since it can
cluster a table's distribution and its sort order along the same axis) --
scoped out for this version, worth adding before treating this as more than
a demo.
