# ADR-002: One config module, one SOURCE_TABLES registry

## Context

A 25-50-table-per-product migration accumulates per-table knowledge fast:
which tables are append-heavy vs. small lookups, what their primary/natural
keys are, which watermark column drives incremental extraction. Left
implicit, that knowledge ends up re-derived (or re-guessed, inconsistently)
in every script that touches a given table.

## Decision

`warehouse/config.py` is the one place that knows every table in the source
system: `SOURCE_TABLES`, a dict keyed by table name, declaring
`incremental` (watermark-pulled vs. always-replace), `key_cols` (what
`extract.py`'s delete-then-insert matches on), and `natural_key` where one
exists. `warehouse/extract.py` iterates this registry rather than hardcoding
a per-table branch; adding an eleventh table is a five-line addition to one
dict, not a new function in three files.

Paths (`SOURCE_DB_PATH`, `WAREHOUSE_DB_PATH`, `GENERATED_SQL_DIR`) and
generation parameters follow the same rule, imported everywhere as
`from warehouse import config` and read as `config.ATTR` at call time --
never `from warehouse.config import ATTR`. That's what lets
`tests/test_pipeline_e2e.py` monkeypatch `config.SOURCE_DB_PATH` and have it
take effect inside every module without a reload.

## Consequences

The registry doesn't yet know about column-level type overrides or
per-column PII flags -- a real 25-50-table migration would likely want that
here too. Scoped out deliberately: this demo's 10 tables don't need it, and
adding speculative structure nobody exercises would just be a second thing to
keep in sync with reality.
