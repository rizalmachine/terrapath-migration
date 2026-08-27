"""Entry point: `python -m data_gen.bootstrap [--force] [--farmers N] [--seed N]`

Seeds the fictional source OLTP system (data/source.duckdb) directly -- the
code under demonstration here is warehouse.extract *querying a source
connection*, not reading a landed file, so direct-seeding is the right analog
of Porto's generator-writes-landed-files principle, not a violation of it.
See docs/adr/003.
"""
import argparse

from warehouse import config, db
from data_gen.source_schema import create_source_schema
from data_gen.generate_reference import (
    generate_regions, generate_crop_types, generate_field_agents, generate_supply_chain_nodes,
)
from data_gen.generate_farmers_and_plots import generate_farmers_and_plots
from data_gen.generate_transactions import generate_transactions, generate_certifications


def _table_has_rows(con, table):
    return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] > 0


def bootstrap(farmers=config.FARMERS, seed=config.SEED, force=False):
    con = db.get_source_connection(read_only=False)
    try:
        create_source_schema(con, force=force)

        if not force and _table_has_rows(con, "farmers"):
            print("[SKIP] source already seeded (use --force to regenerate)")
            return

        regions = generate_regions()
        crop_types = generate_crop_types()
        agents = generate_field_agents(regions["region_id"].tolist(), seed=seed)
        nodes = generate_supply_chain_nodes(regions["region_id"].tolist(), seed=seed)
        farmers_df, plots_df = generate_farmers_and_plots(
            regions["region_id"].tolist(), agents["agent_id"].tolist(), crop_types["crop_type_id"].tolist(),
            n_farmers=farmers, seed=seed,
        )
        tx_df, batch_tx_df, custody_df = generate_transactions(farmers_df, plots_df, nodes, seed=seed)
        certs_df = generate_certifications(plots_df, seed=seed)

        for table, df in [
            ("regions", regions), ("crop_types", crop_types), ("field_agents", agents),
            ("supply_chain_nodes", nodes), ("farmers", farmers_df), ("farm_plots", plots_df),
            ("harvest_transactions", tx_df), ("batch_transactions", batch_tx_df),
            ("custody_events", custody_df), ("certifications", certs_df),
        ]:
            con.register("_stage", df)
            con.execute(f"INSERT INTO {table} SELECT * FROM _stage")
            con.unregister("_stage")
            print(f"[OK] {len(df)} rows -> {table}")
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description="Seed the fictional TerraPath source system")
    parser.add_argument("--farmers", type=int, default=config.FARMERS)
    parser.add_argument("--seed", type=int, default=config.SEED)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    bootstrap(farmers=args.farmers, seed=args.seed, force=args.force)


if __name__ == "__main__":
    main()
