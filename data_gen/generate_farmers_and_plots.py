"""Farmers and their plots -- the two entities that get true SCD2 treatment
downstream, so their source data needs realistic messiness: missing GPS
surveys and near-duplicate registrations (see warehouse.config for rates).

farmer_code / plot_code are deliberately pure-digit strings (not prefixed like
"FARM-001") -- these are the natural keys that must be coerced to str before
any cross-source comparison downstream (see docs/adr/004 and Porto's original
patch_by_key bug this generalizes).
"""
import random
from datetime import datetime, timedelta

import pandas as pd
from faker import Faker

from warehouse import config
from data_gen.generate_reference import _random_latlon


def _random_phone(rng):
    return "628" + "".join(rng.choice("123456789") for _ in range(9))


def generate_farmers_and_plots(region_ids, agent_ids, crop_type_ids,
                                n_farmers=config.FARMERS, seed=config.SEED, as_of=None):
    Faker.seed(seed + 2)
    fake = Faker("id_ID")
    rng = random.Random(seed + 2)
    as_of = as_of or datetime.now()
    window_start = as_of - timedelta(days=365 * 5)

    farmers = []
    plots = []
    plot_id = 1

    def _new_farmer(farmer_id, national_id=None, full_name=None, registered_at=None):
        registered_at = registered_at or (
            window_start + timedelta(seconds=rng.randint(0, int((as_of - window_start).total_seconds())))
        )
        return {
            "farmer_id": farmer_id,
            "farmer_code": str(700000 + farmer_id),
            "national_id": national_id or f"{rng.randint(0, 10 ** 16 - 1):016d}",
            "full_name": full_name or fake.name(),
            "phone_number": _random_phone(rng),
            "region_id": rng.choice(region_ids),
            "registered_by_agent_id": rng.choice(agent_ids),
            "registered_at": registered_at,
            "updated_at": registered_at,
            "is_active": rng.random() > 0.03,
        }

    for farmer_id in range(1, n_farmers + 1):
        farmers.append(_new_farmer(farmer_id))

    # Deliberate messiness: re-registered farmers -- same national_id, new farmer_id/agent/date.
    n_duplicates = int(n_farmers * config.DUPLICATE_FARMER_RATE)
    next_id = n_farmers + 1
    for _ in range(n_duplicates):
        original = rng.choice(farmers)
        farmers.append(_new_farmer(
            next_id, national_id=original["national_id"], full_name=original["full_name"],
        ))
        next_id += 1

    for farmer in farmers:
        n_plots = rng.randint(1, 3)
        for _ in range(n_plots):
            missing_geo = rng.random() < config.MISSING_GEO_RATE
            if missing_geo:
                lat, lon, source = None, None, "manual_estimate"
            else:
                lat, lon = _random_latlon(rng)
                source = rng.choice(["gps_survey", "satellite"])
            updated_at = farmer["registered_at"] + timedelta(days=rng.randint(0, 300))
            plots.append({
                "plot_id": plot_id,
                "plot_code": str(900000 + plot_id),
                "farmer_id": farmer["farmer_id"],
                "crop_type_id": rng.choice(crop_type_ids),
                "region_id": farmer["region_id"],
                "latitude": lat,
                "longitude": lon,
                "area_hectares": round(rng.uniform(0.3, 4.0), 2),
                "ownership_status": rng.choice(["owned", "leased", "shared"]),
                "polygon_source": source,
                "updated_at": min(updated_at, as_of),
            })
            plot_id += 1

    return pd.DataFrame(farmers), pd.DataFrame(plots)
