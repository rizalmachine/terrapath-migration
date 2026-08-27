import duckdb
import pandas as pd
import pytest

from warehouse.ddl_generator import generate_ddl, generate_copy


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    c.execute("CREATE SCHEMA analytics")
    yield c
    c.close()


def test_generate_ddl_has_valid_shape(con):
    df = pd.DataFrame({
        "crop_type_key": range(1, 9),
        "crop_name": [f"Crop{i}" for i in range(8)],
        "crop_category": ["plantation"] * 8,
        "unit_of_measure": ["kg"] * 8,
    })
    con.register("_stage", df)
    con.execute("CREATE TABLE analytics.dim_crop_type AS SELECT * FROM _stage")
    con.unregister("_stage")

    ddl = generate_ddl(con, "dim_crop_type")
    assert ddl.startswith("CREATE TABLE analytics.dim_crop_type (")
    assert ddl.rstrip().endswith(";")
    assert "DISTSTYLE ALL" in ddl
    assert "crop_type_key BIGINT" in ddl
    assert "VARCHAR(" in ddl  # string columns got a computed length, not bare VARCHAR


def test_generate_copy_uses_env_placeholders(monkeypatch):
    monkeypatch.setenv("TERRAPATH_S3_BUCKET", "my-test-bucket")
    monkeypatch.setenv("TERRAPATH_IAM_ROLE_ARN", "arn:aws:iam::999999999999:role/test-role")
    copy_sql = generate_copy("dim_crop_type")
    assert "s3://my-test-bucket/exports/analytics/dim_crop_type/" in copy_sql
    assert "arn:aws:iam::999999999999:role/test-role" in copy_sql
    assert copy_sql.strip().endswith(";")
