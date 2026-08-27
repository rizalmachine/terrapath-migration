# ADR-001: Two DuckDB files stand in for MySQL and Redshift

## Context

The real migration this project is modeled on moved OLTP tables from MySQL
into a Redshift analytical warehouse. Neither is a reasonable thing to require
for a portfolio demo: MySQL needs a running server, and Redshift is a paid,
provisioned AWS service with no free zero-setup tier a reviewer could spin up
to try this out.

## Decision

`data/source.duckdb` stands in for the OLTP system, `data/warehouse.duckdb`
for the Redshift target (`raw`/`analytics`/`audit` schemas). Both are plain
embedded DuckDB files -- `pip install`, no server, no account, no cost.

The boundary between them is enforced at the API level, not just by
convention: `warehouse.db.get_source_connection()` defaults to
`read_only=True`; only `data_gen` ever opens it writable.

Real Redshift DDL is still produced -- `warehouse.ddl_generator` emits actual
`CREATE TABLE ... DISTKEY(...) SORTKEY(...)` and `COPY ... FROM 's3://...'`
statements as text files under `sql/generated/`. They are never executed
against anything. This mirrors the sibling `Porto` project's own DuckDB-not-
Postgres decision, and its GSheet-export-off-by-default pattern: ship the real
artifact, gate the real network/cluster call behind something that never runs
automatically.

## Consequences

Anyone cloning this repo gets a working, fully-tested migration pipeline with
one `pip install` and no external service dependencies or AWS credentials.
The generated DDL has never been run against a real Redshift cluster, so
things a live cluster would surface -- actual data skew under concurrent
load, real `VACUUM`/`ANALYZE` costs, WLM queue contention -- aren't validated
here. That's an explicit, stated gap (see also ADR-006), not something this
demo claims to prove.
