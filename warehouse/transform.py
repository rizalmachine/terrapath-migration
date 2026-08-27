"""Analytics layer: builds every dimension and both fact tables from the raw
layer. Three different change-tracking strategies, on purpose (see
docs/adr/005):

- dim_farmer, dim_plot: true SCD2 (warehouse.scd2.apply_scd2)
- dim_certification: effective-dated, no snapshot (source already knows
  issued_date/expiry_date -- snapshotting would only degrade it)
- dim_crop_type, dim_supply_chain_node, dim_location: SCD1, current-state only
"""
import pandas as pd

from warehouse import db
from warehouse.scd2 import apply_scd2, resolve_scd2_key

FARMER_TRACKED_COLS = ["region_id", "phone_number", "is_active"]
PLOT_TRACKED_COLS = ["farmer_id", "ownership_status", "area_hectares", "latitude", "longitude", "polygon_source"]


def _build_scd1_dim(con, dim_table, key_col, source_df):
    df = source_df.reset_index(drop=True).copy()
    df.insert(0, key_col, range(1, len(df) + 1))
    con.register("_stage", df)
    con.execute(f"CREATE OR REPLACE TABLE analytics.{dim_table} AS SELECT * FROM _stage")
    con.unregister("_stage")


def _build_dim_certification(con, certs_df):
    df = certs_df.reset_index(drop=True).copy()
    df.insert(0, "certification_key", range(1, len(df) + 1))
    con.register("_stage", df)
    con.execute("CREATE OR REPLACE TABLE analytics.dim_certification AS SELECT * FROM _stage")
    con.unregister("_stage")


def _build_dim_date(con, min_date, max_date):
    dates = pd.date_range(min_date, max_date, freq="D")
    df = pd.DataFrame({
        "date_key": dates.strftime("%Y%m%d").astype(int),
        "date": dates.date,
        "day_of_week": dates.dayofweek + 1,
        "month": dates.month,
        "quarter": dates.quarter,
        "year": dates.year,
    })
    con.register("_stage", df)
    con.execute("CREATE OR REPLACE TABLE analytics.dim_date AS SELECT * FROM _stage")
    con.unregister("_stage")


def run(con=None, as_of=None):
    own_con = con is None
    con = con or db.get_target_connection()
    as_of = as_of or pd.Timestamp.now()
    try:
        farmers = con.execute("SELECT * FROM raw.farmers").fetchdf()
        plots = con.execute("SELECT * FROM raw.farm_plots").fetchdf()
        crop_types = con.execute("SELECT * FROM raw.crop_types").fetchdf()
        nodes = con.execute("SELECT * FROM raw.supply_chain_nodes").fetchdf()
        regions = con.execute("SELECT * FROM raw.regions").fetchdf()
        certs = con.execute("SELECT * FROM raw.certifications").fetchdf()
        tx = con.execute("SELECT * FROM raw.harvest_transactions").fetchdf()
        custody = con.execute("SELECT * FROM raw.custody_events").fetchdf()

        n_new, n_expired = apply_scd2(con, "dim_farmer", "farmer_key", "farmer_code",
                                       farmers, FARMER_TRACKED_COLS, as_of)
        print(f"    [SCD2] dim_farmer: {n_new} new version(s), {n_expired} expired")
        n_new, n_expired = apply_scd2(con, "dim_plot", "plot_key", "plot_code",
                                       plots, PLOT_TRACKED_COLS, as_of)
        print(f"    [SCD2] dim_plot: {n_new} new version(s), {n_expired} expired")

        _build_scd1_dim(con, "dim_crop_type", "crop_type_key", crop_types)
        _build_scd1_dim(con, "dim_supply_chain_node", "node_key", nodes)
        _build_scd1_dim(con, "dim_location", "location_key", regions)
        _build_dim_certification(con, certs)

        all_dates = pd.concat([tx["transaction_date"], custody["event_timestamp"]])
        _build_dim_date(con, pd.to_datetime(all_dates.min()).date(), pd.to_datetime(all_dates.max()).date())

        # --- fact_harvest_transactions ---
        tx = tx.merge(farmers[["farmer_id", "farmer_code"]], on="farmer_id", how="left")
        tx = tx.merge(plots[["plot_id", "plot_code"]], on="plot_id", how="left")
        tx = resolve_scd2_key(con, "dim_farmer", "farmer_key", "farmer_code", tx, "farmer_code", "transaction_date")
        tx = resolve_scd2_key(con, "dim_plot", "plot_key", "plot_code", tx, "plot_code", "transaction_date")

        crop_type_map = con.execute("SELECT crop_type_key, crop_type_id FROM analytics.dim_crop_type").fetchdf()
        node_map = con.execute("SELECT node_key, node_id FROM analytics.dim_supply_chain_node").fetchdf()
        tx = tx.merge(crop_type_map, on="crop_type_id", how="left")
        tx = tx.merge(node_map, on="node_id", how="left")
        tx["date_key"] = pd.to_datetime(tx["transaction_date"]).dt.strftime("%Y%m%d").astype(int)

        fact_harvest = tx[[
            "transaction_id", "farmer_key", "plot_key", "crop_type_key", "node_key", "date_key",
            "transaction_date", "quantity_kg", "unit_price", "total_value",
            "moisture_content", "grade", "payment_status",
        ]].rename(columns={"transaction_id": "transaction_sk"})
        con.register("_stage", fact_harvest)
        con.execute("CREATE OR REPLACE TABLE analytics.fact_harvest_transactions AS SELECT * FROM _stage")
        con.unregister("_stage")

        # --- fact_custody_events ---
        from_map = node_map.rename(columns={"node_key": "from_node_key", "node_id": "from_node_id"})
        to_map = node_map.rename(columns={"node_key": "to_node_key", "node_id": "to_node_id"})
        custody = custody.merge(from_map, on="from_node_id", how="left")
        custody = custody.merge(to_map, on="to_node_id", how="left")
        custody["date_key"] = pd.to_datetime(custody["event_timestamp"]).dt.strftime("%Y%m%d").astype(int)

        fact_custody = custody[[
            "event_id", "batch_id", "from_node_key", "to_node_key", "date_key",
            "event_type", "event_timestamp", "quantity_kg",
        ]].rename(columns={"event_id": "event_sk"})
        con.register("_stage", fact_custody)
        con.execute("CREATE OR REPLACE TABLE analytics.fact_custody_events AS SELECT * FROM _stage")
        con.unregister("_stage")

        return {
            "dim_farmer_rows": con.execute("SELECT COUNT(*) FROM analytics.dim_farmer").fetchone()[0],
            "dim_plot_rows": con.execute("SELECT COUNT(*) FROM analytics.dim_plot").fetchone()[0],
            "fact_harvest_rows": len(fact_harvest),
            "fact_custody_rows": len(fact_custody),
        }
    finally:
        if own_con:
            con.close()
