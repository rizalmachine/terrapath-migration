# ADR-003: Synthetic data, seeded directly into the fictional source system

## Context

This project is a public case study of a real migration. The real source
data included real farmers' national IDs, real phone numbers, and a real
company's supply-chain structure. None of that can appear here, and
scrubbing a real export by find-and-replace is exactly the kind of task where
one missed column causes a real leak.

## Decision

Nothing here is derived from the real system. `data_gen/` builds a fictional
company's OLTP data from scratch on every fresh clone
(`python -m data_gen.bootstrap`):

- `source_schema.py` -- the 10-table schema, standing in for the real
  25-50-table-per-product scale (a representative pattern, not a scale
  match -- see also `funnel-warehouse`/Porto's own precedent of showing
  technique over volume).
- `generate_reference.py` -- regions, crop types, field agents, supply-chain
  nodes.
- `generate_farmers_and_plots.py` -- farmers and plots, `Faker('id_ID')` +
  a scoped `random.Random(seed)`, with deliberate messiness: ~7% of plots
  have no GPS survey yet (`polygon_source='manual_estimate'`), ~2.5% of
  farmers are near-duplicates (same `national_id`, different `farmer_id` --
  a real re-registration pattern `dq_checks.py` flags, never silently
  merges).
- `generate_transactions.py` -- harvests, chain-of-custody events grouped
  into batches, and certifications (some already expired).
- `simulate_incremental_activity.py` -- mutates a few existing farmers/plots
  and adds fresh transactions dated after the mutation, so a second pipeline
  run has real incremental extraction and SCD2 versioning to demonstrate,
  not just a re-run of the same static snapshot.

Unlike Porto's generator (which writes landed CSVs for `extract.py` to read),
this one seeds `source.duckdb` directly. That's still the same underlying
principle, not an exception to it: the code being demonstrated here is
`extract.py` *querying a source connection* via SQL, not reading a file --
direct-seeding is the faithful analog for this domain, not a shortcut around
it.

## Consequences

Company name, brands, region names, and every number here are invented. The
fictional scale (~480,000 farmers, 9 countries) is order-of-magnitude similar
to the real company's public numbers, deliberately not digit-for-digit
identical. Demo defaults (2,000 farmers) are far below either scale --
enough to exercise every technique in `warehouse/transform.py`, not enough to
demonstrate production performance, which was never the point.
