"""Reference/lookup data: regions, crop types, field agents, supply-chain
nodes. Always-replace tables (small, cheap, must stay current) -- see
warehouse.config.SOURCE_TABLES.
"""
import random
from datetime import date, timedelta

import pandas as pd
from faker import Faker

from warehouse import config

# Fictional bounding box for GPS coordinates -- plausible numeric ranges, not a real place.
_LAT_RANGE = (-8.5, -6.0)
_LON_RANGE = (106.0, 112.0)


def _random_latlon(rng):
    lat = round(rng.uniform(*_LAT_RANGE), 6)
    lon = round(rng.uniform(*_LON_RANGE), 6)
    return lat, lon


def generate_regions() -> pd.DataFrame:
    name_to_id = {name: i for i, (name, _, _) in enumerate(config.REGIONS, start=1)}
    rows = [
        {
            "region_id": i,
            "region_name": name,
            "region_level": level,
            "parent_region_id": name_to_id.get(parent_name) if parent_name else None,
        }
        for i, (name, level, parent_name) in enumerate(config.REGIONS, start=1)
    ]
    return pd.DataFrame(rows)


def generate_crop_types() -> pd.DataFrame:
    rows = [
        {"crop_type_id": i, "crop_name": name, "crop_category": category, "unit_of_measure": unit}
        for i, (name, category, unit) in enumerate(config.CROP_TYPES, start=1)
    ]
    return pd.DataFrame(rows)


def generate_field_agents(region_ids, n=25, seed=config.SEED) -> pd.DataFrame:
    Faker.seed(seed)
    fake = Faker("id_ID")
    rng = random.Random(seed)
    roles = ["Field Officer", "Senior Field Officer", "Regional Coordinator"]
    rows = []
    for i in range(1, n + 1):
        hire_date = date(2020, 1, 1) + timedelta(days=rng.randint(0, 365 * 5))
        rows.append({
            "agent_id": i,
            "agent_code": f"AGT-{i:04d}",
            "full_name": fake.name(),
            "region_id": rng.choice(region_ids),
            "role": rng.choice(roles),
            "hire_date": hire_date,
            "is_active": rng.random() > 0.05,
        })
    return pd.DataFrame(rows)


def generate_supply_chain_nodes(region_ids, seed=config.SEED) -> pd.DataFrame:
    Faker.seed(seed + 1)
    fake = Faker("id_ID")
    rng = random.Random(seed + 1)
    rows = []
    node_id = 1
    for region_id in region_ids:
        for node_type in config.NODE_TYPES:
            if rng.random() < 0.6:  # not every region has every node type
                lat, lon = _random_latlon(rng)
                rows.append({
                    "node_id": node_id,
                    "node_type": node_type,
                    "node_name": f"{node_type.title()} {fake.company()}",
                    "region_id": region_id,
                    "gps_lat": lat,
                    "gps_lon": lon,
                })
                node_id += 1
    return pd.DataFrame(rows)
