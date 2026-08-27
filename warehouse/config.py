"""Single source of configuration. Mirrors the sibling Porto project's pattern:
always imported as `from warehouse import config` and accessed as `config.ATTR`
at call time (never `from warehouse.config import ATTR`) -- that's what lets
tests monkeypatch paths and have it take effect everywhere.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SOURCE_DB_PATH = BASE_DIR / os.environ.get("TERRAPATH_SOURCE_DB_PATH", "data/source.duckdb")
WAREHOUSE_DB_PATH = BASE_DIR / os.environ.get("TERRAPATH_WAREHOUSE_DB_PATH", "data/warehouse.duckdb")
GENERATED_SQL_DIR = BASE_DIR / "sql" / "generated"

SEED = int(os.environ.get("TERRAPATH_SEED", "42"))
FARMERS = int(os.environ.get("TERRAPATH_FARMERS", "2000"))

# Registry of every table in the fictional source OLTP system, replacing what
# in the real system was implicit/scattered knowledge. incremental=True tables
# are pulled by watermark (updated_at); incremental=False tables are always
# fully replaced (small, cheap, must stay current).
SOURCE_TABLES = {
    "regions": {"incremental": False, "key_cols": ["region_id"]},
    "crop_types": {"incremental": False, "key_cols": ["crop_type_id"]},
    "field_agents": {"incremental": False, "key_cols": ["agent_id"]},
    "supply_chain_nodes": {"incremental": False, "key_cols": ["node_id"]},
    "farmers": {"incremental": True, "key_cols": ["farmer_id"], "natural_key": "farmer_code"},
    "farm_plots": {"incremental": True, "key_cols": ["plot_id"], "natural_key": "plot_code"},
    "harvest_transactions": {"incremental": True, "key_cols": ["transaction_id"]},
    "custody_events": {"incremental": True, "key_cols": ["event_id"]},
    "batch_transactions": {"incremental": True, "key_cols": ["batch_id", "transaction_id"]},
    "certifications": {"incremental": True, "key_cols": ["certification_id"], "natural_key": "certificate_number"},
}

REGIONS = [
    ("Kayangan", "province", None),
    ("Kayangan Utara", "district", "Kayangan"),
    ("Kayangan Selatan", "district", "Kayangan"),
    ("Merapatih", "province", None),
    ("Merapatih Barat", "district", "Merapatih"),
    ("Merapatih Timur", "district", "Merapatih"),
    ("Sungai Lembayung", "province", None),
    ("Lembayung Hulu", "district", "Sungai Lembayung"),
    ("Lembayung Hilir", "district", "Sungai Lembayung"),
]

CROP_TYPES = [
    ("Cocoa", "plantation", "kg"),
    ("Robusta Coffee", "plantation", "kg"),
    ("Arabica Coffee", "plantation", "kg"),
    ("Cashew", "nuts", "kg"),
    ("Vanilla", "spice", "kg"),
    ("Black Pepper", "spice", "kg"),
    ("Palm Fruit", "plantation", "kg"),
    ("Rubber", "plantation", "kg"),
]

NODE_TYPES = ["collector", "processor", "exporter", "warehouse"]

CERTIFICATION_BODIES = ["Rainforest Alliance", "Fairtrade", "Organic EU", "UTZ"]

# Deliberate source-data messiness rates -- gives schema redesign & validation something real to catch.
MISSING_GEO_RATE = 0.07
DUPLICATE_FARMER_RATE = 0.025
