"""Harvest transactions, chain-of-custody events, batch linkage, and
certifications -- the transactional heart of the traceability story: which
farmers' lots make up a shipped batch, and can it be traced end to end.
"""
import random
from datetime import datetime, timedelta

import pandas as pd

from warehouse import config


def _nodes_by_type(nodes_df):
    by_type = {}
    for node_type in config.NODE_TYPES:
        ids = nodes_df.loc[nodes_df["node_type"] == node_type, "node_id"].tolist()
        by_type[node_type] = ids
    return by_type


def generate_transactions(farmers_df, plots_df, nodes_df, seed=config.SEED, as_of=None, days=180):
    rng = random.Random(seed + 3)
    as_of = as_of or datetime.now()
    window_start = as_of - timedelta(days=days)
    by_type = _nodes_by_type(nodes_df)
    collectors = by_type["collector"] or nodes_df["node_id"].tolist()

    active_farmers = farmers_df[farmers_df["is_active"]]
    plots_by_farmer = plots_df.groupby("farmer_id")["plot_id"].apply(list).to_dict()

    transactions = []
    transaction_id = 1
    for _, farmer in active_farmers.iterrows():
        plot_ids = plots_by_farmer.get(farmer["farmer_id"], [])
        if not plot_ids:
            continue
        n_tx = rng.randint(1, 4)
        for _ in range(n_tx):
            plot_id = rng.choice(plot_ids)
            crop_type_id = plots_df.loc[plots_df["plot_id"] == plot_id, "crop_type_id"].iloc[0]
            tx_date = window_start + timedelta(seconds=rng.randint(0, int((as_of - window_start).total_seconds())))
            quantity = round(rng.uniform(20, 500), 2)
            unit_price = round(rng.uniform(15000, 45000), 2)
            transactions.append({
                "transaction_id": transaction_id,
                "farmer_id": farmer["farmer_id"],
                "plot_id": plot_id,
                "crop_type_id": crop_type_id,
                "node_id": rng.choice(collectors),
                "transaction_date": tx_date,
                "quantity_kg": quantity,
                "unit_price": unit_price,
                "total_value": round(quantity * unit_price, 2),
                "moisture_content": round(rng.uniform(6.0, 14.0), 2),
                "grade": rng.choice(["A", "B", "C"]),
                "payment_status": rng.choices(["paid", "pending"], weights=[0.85, 0.15])[0],
                "updated_at": tx_date,
            })
            transaction_id += 1

    tx_df = pd.DataFrame(transactions)

    # Batch transactions by (collector node, week) -- a collector aggregates several
    # farmers' lots into one shipped batch, which is the actual traceability question.
    tx_df["_week"] = pd.to_datetime(tx_df["transaction_date"]).dt.to_period("W").astype(str)
    batch_transactions = []
    custody_events = []
    event_id = 1
    processors = by_type["processor"] or nodes_df["node_id"].tolist()
    exporters = by_type["exporter"] or nodes_df["node_id"].tolist()

    for (node_id, week), group in tx_df.groupby(["node_id", "_week"]):
        batch_id = f"BATCH-{node_id}-{week}"
        total_qty = round(group["quantity_kg"].sum(), 2)
        last_tx = group["transaction_date"].max()
        for _, row in group.iterrows():
            batch_transactions.append({
                "batch_id": batch_id,
                "transaction_id": row["transaction_id"],
                "quantity_allocated_kg": row["quantity_kg"],
                "updated_at": row["transaction_date"],
            })

        collected_at = last_tx + timedelta(hours=rng.randint(2, 12))
        transported_at = collected_at + timedelta(hours=rng.randint(6, 48))
        processor_id = rng.choice(processors)
        processed_at = transported_at + timedelta(hours=rng.randint(12, 72))
        exporter_id = rng.choice(exporters)
        exported_at = processed_at + timedelta(days=rng.randint(2, 10))

        chain = [
            ("collected", None, None, node_id, collected_at),
            ("transported", node_id, "collector", processor_id, transported_at),
            ("processed", processor_id, "processor", processor_id, processed_at),
            ("exported", processor_id, "processor", exporter_id, exported_at),
        ]
        for event_type, from_id, from_type, to_id, ts in chain:
            custody_events.append({
                "event_id": event_id,
                "batch_id": batch_id,
                "from_node_id": from_id,
                "from_node_type": from_type,
                "to_node_id": to_id,
                "event_type": event_type,
                "event_timestamp": ts,
                "quantity_kg": total_qty,
                "updated_at": ts,
            })
            event_id += 1

    tx_df = tx_df.drop(columns=["_week"])
    return tx_df, pd.DataFrame(batch_transactions), pd.DataFrame(custody_events)


def generate_certifications(plots_df, seed=config.SEED, as_of=None, coverage=0.4):
    rng = random.Random(seed + 4)
    as_of = as_of or datetime.now()
    rows = []
    certification_id = 1
    eligible_plots = plots_df.sample(frac=coverage, random_state=seed).to_dict("records")
    for plot in eligible_plots:
        issued_date = (as_of - timedelta(days=rng.randint(30, 3 * 365))).date()
        validity_days = rng.choice([365, 730])
        expiry_date = issued_date + timedelta(days=validity_days)
        status = "active" if expiry_date >= as_of.date() else "expired"
        rows.append({
            "certification_id": certification_id,
            "plot_id": plot["plot_id"],
            "certification_body": rng.choice(config.CERTIFICATION_BODIES),
            "certification_type": rng.choice(["Sustainable Sourcing", "Deforestation-Free", "Organic"]),
            "certificate_number": str(500000 + certification_id),
            "issued_date": issued_date,
            "expiry_date": expiry_date,
            "status": status,
            "updated_at": issued_date,
        })
        certification_id += 1
    return pd.DataFrame(rows)
