# ADR-005: Three change-tracking strategies, on purpose

## Context

Not every slowly-changing input needs the same treatment, and treating them
identically either loses history that matters or builds versioning machinery
for data that never needed it. This is the same rule of thumb already proven
in a companion portfolio project's real ADR
(`funnel-warehouse/docs/adr/002-scd-strategy.md`): *if the source system
knows the validity window, keep it; if only you can observe the change,
snapshot it.*

## Decision

Three strategies, applied deliberately rather than defaulted to one:

- **`dim_farmer`, `dim_plot` -- true SCD2** (`warehouse/scd2.py`). A farmer
  gets reassigned to a new region; a plot gets re-surveyed and its
  coordinates corrected. Neither event is announced ahead of time by the
  source -- only observable at extract time -- so both are versioned with
  `valid_from`/`valid_to`/`is_current`.
- **`dim_certification` -- effective-dated, no snapshot.** The source already
  carries `issued_date`/`expiry_date`; snapshotting on top would only degrade
  a real validity window into "whenever the pipeline happened to run."
- **`dim_crop_type`, `dim_supply_chain_node`, `dim_location` -- SCD1**,
  current-state only. Explicitly scoped out, not an oversight.

Facts resolve dimension keys via a **point-in-time join**
(`resolve_scd2_key()`: `fact.date BETWEEN dim.valid_from AND dim.valid_to`),
never "whichever version `is_current` right now." `tests/test_scd2.py::
test_resolve_scd2_key_point_in_time` proves it: a transaction dated before a
farmer's region change resolves to the old dimension version; one dated after
resolves to the new one.

**A real bug found while building this, worth stating plainly:** the first
historical load of `dim_farmer`/`dim_plot` originally set `valid_from = as_of`
(the moment the pipeline ran) for every farmer's first version. Every
historical transaction predates "now," so every point-in-time join failed --
0 of 472 fact rows resolved a `farmer_key`. The fix: a historical backfill's
initial version gets `valid_from = INCEPTION` (a fixed epoch predating all
data), not `as_of`; only a *genuinely detected change* on a later run earns
`valid_from = as_of`. `tests/test_scd2.py::test_first_build_uses_inception_not_as_of`
guards this.

## Consequences

`dim_certification` isn't part of either fact table's grain -- it's queried
directly by `plot_id` + an as-of date, not joined into
`fact_harvest_transactions`. That's a deliberate simplification: a
transaction isn't "for" a certification the way it's for a farmer or a plot.
