import pytest

from warehouse import config


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SOURCE_DB_PATH", tmp_path / "source.duckdb")
    monkeypatch.setattr(config, "WAREHOUSE_DB_PATH", tmp_path / "warehouse.duckdb")
    monkeypatch.setattr(config, "GENERATED_SQL_DIR", tmp_path / "sql_generated")


def test_pipeline_runs_end_to_end_and_is_idempotent(isolated_paths):
    from data_gen import bootstrap
    from warehouse import pipeline as pipeline_module, db

    bootstrap.bootstrap(farmers=100, seed=1)
    assert pipeline_module.run() is True

    con = db.get_target_connection()
    try:
        first_farmer = con.execute("SELECT COUNT(*) FROM analytics.dim_farmer").fetchone()[0]
        first_fact = con.execute("SELECT COUNT(*) FROM analytics.fact_harvest_transactions").fetchone()[0]
        assert first_farmer > 0 and first_fact > 0
    finally:
        con.close()

    assert pipeline_module.run() is True  # no new source activity -- must be a true no-op

    con = db.get_target_connection()
    try:
        second_farmer = con.execute("SELECT COUNT(*) FROM analytics.dim_farmer").fetchone()[0]
        second_fact = con.execute("SELECT COUNT(*) FROM analytics.fact_harvest_transactions").fetchone()[0]
    finally:
        con.close()

    assert second_farmer == first_farmer
    assert second_fact == first_fact


def test_incremental_activity_creates_new_scd2_version_not_duplicate(isolated_paths):
    from data_gen import bootstrap
    from data_gen.simulate_incremental_activity import simulate
    from warehouse import pipeline as pipeline_module, db

    bootstrap.bootstrap(farmers=100, seed=2)
    assert pipeline_module.run() is True

    con = db.get_target_connection()
    before = con.execute("SELECT COUNT(*) FROM analytics.dim_farmer").fetchone()[0]
    con.close()

    simulate(seed=2, n_mutations=3, n_new_transactions=5)
    assert pipeline_module.run() is True

    con = db.get_target_connection()
    try:
        after = con.execute("SELECT COUNT(*) FROM analytics.dim_farmer").fetchone()[0]
        multi_version_farmers = con.execute("""
            SELECT COUNT(*) FROM (
                SELECT farmer_code FROM analytics.dim_farmer GROUP BY farmer_code HAVING COUNT(*) > 1
            )
        """).fetchone()[0]
    finally:
        con.close()

    assert after == before + 3  # 3 mutated farmers, each got exactly one new version
    assert multi_version_farmers == 3


def test_dry_run_makes_no_changes(isolated_paths):
    from data_gen import bootstrap
    from warehouse import pipeline as pipeline_module, db

    bootstrap.bootstrap(farmers=50, seed=3)
    assert pipeline_module.run(dry_run=True) is True

    con = db.get_target_connection()
    try:
        exists = con.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema='raw' AND table_name='farmers'"
        ).fetchone()
        assert exists is None
    finally:
        con.close()
