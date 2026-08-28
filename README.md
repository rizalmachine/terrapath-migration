# Kanopi Agritech: TerraPath Migration (demo)

> Fictional company, 100% synthetic data. A portfolio case study of a real
> MySQL-to-Redshift migration I led the schema redesign and warehouse layer
> for at my day job, as one product-area owner on a larger migration team,
> using the same techniques on an entirely fictional company, data, and scale.

A standalone migration accelerator: source OLTP -> a Redshift-shaped star
schema, three change-tracking strategies applied deliberately, a rules-based
DISTKEY/SORTKEY advisor, and a DDL/COPY generator that emits real Redshift
SQL without ever touching a real cluster.

## Why it's interesting

- **A migration accelerator, not just a migrated schema.** `warehouse/advisor.py`
  recommends DISTKEY/SORTKEY choices from real computed cardinality, and
  `warehouse/ddl_generator.py` turns that into actual, valid Redshift DDL +
  COPY text: the kind of reusable tooling a migration team builds once and
  runs on every table, not a one-off script.
- **A real bug that broke every point-in-time join, caught by its own test.**
  The first historical SCD2 load set `valid_from` to "now" instead of an
  epoch, so 0 of 472 historical transactions could resolve a farmer
  dimension key. Fixed, and guarded by
  `tests/test_scd2.py::test_first_build_uses_inception_not_as_of` so it can't
  come back quietly.
- **Three change-tracking strategies, chosen on purpose.** `dim_farmer`/
  `dim_plot` get true SCD2, `dim_certification` stays effective-dated (the
  source already knows its validity window), and three smaller dimensions
  stay SCD1. Same rule of thumb proven in a companion project's real ADR,
  not three defaults applied at random.
- **Row-count checks aren't enough, and this proves it.**
  `warehouse/validate.py`'s row-hash checksum catches a source mutation that
  never bumps `updated_at`, invisible to watermark-based extraction alone
  but caught immediately by the checksum.
- **Deliberately kept messy, not smoothed over.** About 7% of plots have no GPS
  survey yet, and about 2.5% of farmers are re-registration duplicates that
  `dq_checks.py` flags but never silently merges. Real migration data is
  never clean, and pretending otherwise would make the demo less honest.

## Stack

Python, pandas, DuckDB (embedded, standing in for both MySQL and Redshift),
Faker, pytest. Zero AWS dependency: generated Redshift DDL is text only,
never executed.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m data_gen.bootstrap                       # seeds the fictional source system
python -m warehouse.pipeline --dry-run
python -m warehouse.pipeline                       # extract -> transform -> validate

python -m data_gen.simulate_incremental_activity   # a second wave: mutations + new activity
python -m warehouse.pipeline                       # incremental extract + new SCD2 versions

python -m warehouse.advisor --all                  # DISTKEY/SORTKEY recommendations
python -m warehouse.ddl_generator --all            # generates sql/generated/*.sql

pytest tests/ -q
```

## Architecture

```
data_gen/ --seeds--> data/source.duckdb --(extract.py, watermark)--> raw.*
                                                                         |
                                                           (transform.py) -> analytics
                                                                         |
        +-----------------+-----------------+---------------------+----+----------------+
        v                 v                 v                     v                     v
   dim_farmer         dim_plot       dim_certification    dim_crop_type/          fact_harvest_
   (SCD2)             (SCD2)         (effective-dated)    node/location/date      transactions,
                                                            (SCD1)                 fact_custody_events
                                                                                         |
                                                        +--------------------------------+
                                                        v                                v
                                              warehouse.advisor                warehouse.ddl_generator
                                          (DISTKEY/SORTKEY, real stats)      (sql/generated/*.sql, never run)
```

`warehouse/pipeline.py` orchestrates extract -> transform -> validate with a
CLI: `--skip-extract`, `--only-validate`, `--step`, `--dry-run`. Every step
logs to `audit.pipeline_runs`; `validate` logs every check to
`audit.validation_results`.

## Project layout

- `warehouse/config.py`: single source of configuration, the `SOURCE_TABLES` registry, paths, seeds
- `warehouse/extract.py`: watermark-based incremental extract, always-replace for small lookups
- `warehouse/scd2.py`: shared SCD2 machinery plus the point-in-time join
- `warehouse/transform.py`: builds every dimension and both fact tables
- `warehouse/dq_checks.py`: duplicate-farmer detector, standalone, not wired into the pipeline
- `warehouse/advisor.py`: rules-based DISTKEY/SORTKEY recommender
- `warehouse/ddl_generator.py`: emits real Redshift DDL and COPY text
- `warehouse/validate.py`: row-count and checksum reconciliation
- `warehouse/pipeline.py`: CLI orchestrator
- `data_gen/`: synthetic source-system generation, including a second-wave activity simulator
- `docs/adr/`: why things are built this way

## Tests

```bash
pytest tests/ -q
```

23 tests: SCD2 insert/expire/no-op/inception-vs-as_of/natural-key coercion,
point-in-time join resolution, the duplicate-farmer detector, all DISTKEY/
SORTKEY rule branches, DDL/COPY string generation, watermark-based extract
(advance, no-op, replace-not-duplicate), row-count/checksum match and
mismatch, and a full end-to-end run proving idempotency, incremental SCD2
versioning, and a true no-op dry-run.

## Docs

- [ADR-001: Two DuckDB files stand in for MySQL and Redshift](docs/adr/001-duckdb-stand-in-for-redshift.md)
- [ADR-002: One config module, one SOURCE_TABLES registry](docs/adr/002-consolidated-config.md)
- [ADR-003: Synthetic data, seeded directly into the fictional source](docs/adr/003-synthetic-source-data.md)
- [ADR-004: Natural keys are coerced to str before any comparison](docs/adr/004-natural-key-coercion.md)
- [ADR-005: Three change-tracking strategies, on purpose](docs/adr/005-three-scd-strategies.md)
- [ADR-006: The DISTKEY/SORTKEY advisor is rules-based, not ML](docs/adr/006-rules-based-advisor.md)

## Privacy

**Kanopi Agritech, TerraPath, and every farmer, plot, and transaction here
are entirely fictional.** This is a from-scratch case study of the
schema-redesign and warehouse-layer techniques behind a real MySQL-to-Redshift
migration I worked on professionally, as one product-area owner on a larger
migration team. No code, data, credentials, or identifiers were copied from
that system. Every row of data in this repo is generated by `data_gen/` at
setup time.
