"""Simulates a second wave of source activity: a few farmer/plot attribute
changes (to exercise SCD2 versioning) plus fresh harvest transactions dated
after those changes -- so a point-in-time join has both a pre-change and a
post-change transaction to resolve correctly. Run this, then re-run
warehouse.pipeline, to see incremental extract + SCD2 versioning in action.
"""
import argparse
import random
from datetime import datetime, timedelta

import pandas as pd

from warehouse import config, db


def simulate(seed=config.SEED, n_mutations=5, n_new_transactions=20, as_of=None):
    as_of = as_of or datetime.now()
    rng = random.Random(seed + 100)
    con = db.get_source_connection(read_only=False)
    try:
        farmers = con.execute("SELECT farmer_id, region_id FROM farmers WHERE is_active = TRUE").fetchdf()
        region_ids = con.execute("SELECT region_id FROM regions").fetchdf()["region_id"].tolist()
        mutated_farmers = farmers.sample(n=min(n_mutations, len(farmers)), random_state=seed)

        for _, row in mutated_farmers.iterrows():
            other_regions = [r for r in region_ids if r != row["region_id"]] or [row["region_id"]]
            con.execute(
                "UPDATE farmers SET region_id = ?, updated_at = ? WHERE farmer_id = ?",
                [rng.choice(other_regions), as_of, int(row["farmer_id"])],
            )
        print(f"[MUTATE] {len(mutated_farmers)} farmer(s) reassigned to a new region")

        plot_ids = con.execute(
            "SELECT plot_id FROM farm_plots WHERE polygon_source = 'manual_estimate' LIMIT ?", [n_mutations]
        ).fetchdf()
        for plot_id in plot_ids["plot_id"]:
            lat = round(rng.uniform(-8.5, -6.0), 6)
            lon = round(rng.uniform(106.0, 112.0), 6)
            con.execute(
                """UPDATE farm_plots SET latitude = ?, longitude = ?, polygon_source = 'gps_survey', updated_at = ?
                   WHERE plot_id = ?""",
                [lat, lon, as_of, int(plot_id)],
            )
        print(f"[MUTATE] {len(plot_ids)} plot(s) re-surveyed (geolocation corrected)")

        next_tx_id = con.execute("SELECT MAX(transaction_id) FROM harvest_transactions").fetchone()[0] + 1
        rows = []
        mutated_ids = mutated_farmers["farmer_id"].tolist()
        for i in range(n_new_transactions):
            farmer_id = int(mutated_ids[i % len(mutated_ids)])
            plot_row = con.execute(
                "SELECT plot_id, crop_type_id FROM farm_plots WHERE farmer_id = ? LIMIT 1", [farmer_id]
            ).fetchone()
            if plot_row is None:
                continue
            plot_id, crop_type_id = plot_row
            node_id = con.execute(
                "SELECT node_id FROM supply_chain_nodes WHERE node_type = 'collector' ORDER BY random() LIMIT 1"
            ).fetchone()[0]
            tx_date = as_of + timedelta(hours=rng.randint(1, 48))
            quantity = round(rng.uniform(20, 500), 2)
            unit_price = round(rng.uniform(15000, 45000), 2)
            rows.append({
                "transaction_id": next_tx_id + i, "farmer_id": farmer_id, "plot_id": plot_id,
                "crop_type_id": crop_type_id, "node_id": node_id, "transaction_date": tx_date,
                "quantity_kg": quantity, "unit_price": unit_price, "total_value": round(quantity * unit_price, 2),
                "moisture_content": round(rng.uniform(6.0, 14.0), 2), "grade": rng.choice(["A", "B", "C"]),
                "payment_status": "pending", "updated_at": tx_date,
            })
        if rows:
            df = pd.DataFrame(rows)
            con.register("_stage", df)
            con.execute("INSERT INTO harvest_transactions SELECT * FROM _stage")
            con.unregister("_stage")
        print(f"[NEW] {len(rows)} new harvest transaction(s) dated after the mutation")
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description="Simulate a second wave of source activity")
    parser.add_argument("--mutations", type=int, default=5)
    parser.add_argument("--transactions", type=int, default=20)
    parser.add_argument("--seed", type=int, default=config.SEED)
    args = parser.parse_args()
    simulate(seed=args.seed, n_mutations=args.mutations, n_new_transactions=args.transactions)


if __name__ == "__main__":
    main()
