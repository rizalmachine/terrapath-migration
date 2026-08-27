"""DDL for the 10 tables of the fictional OLTP source system (TerraPath's
production MySQL, stood in here by DuckDB -- see docs/adr/001). Types are
DuckDB-equivalent; comments note where real MySQL would differ.
"""

DDL = {
    "regions": """
        CREATE TABLE regions (
            region_id INTEGER PRIMARY KEY,      -- MySQL: BIGINT UNSIGNED AUTO_INCREMENT
            region_name VARCHAR NOT NULL,
            region_level VARCHAR NOT NULL,       -- province / district / village
            parent_region_id INTEGER             -- self-FK, NULL for top-level provinces
        )
    """,
    "crop_types": """
        CREATE TABLE crop_types (
            crop_type_id INTEGER PRIMARY KEY,
            crop_name VARCHAR NOT NULL,
            crop_category VARCHAR NOT NULL,
            unit_of_measure VARCHAR NOT NULL
        )
    """,
    "field_agents": """
        CREATE TABLE field_agents (
            agent_id INTEGER PRIMARY KEY,
            agent_code VARCHAR NOT NULL,
            full_name VARCHAR NOT NULL,
            region_id INTEGER NOT NULL,
            role VARCHAR NOT NULL,
            hire_date DATE NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE
        )
    """,
    "supply_chain_nodes": """
        CREATE TABLE supply_chain_nodes (
            node_id INTEGER PRIMARY KEY,
            node_type VARCHAR NOT NULL,          -- collector / processor / exporter / warehouse
            node_name VARCHAR NOT NULL,
            region_id INTEGER NOT NULL,
            gps_lat DOUBLE,
            gps_lon DOUBLE
        )
    """,
    "farmers": """
        CREATE TABLE farmers (
            farmer_id INTEGER PRIMARY KEY,
            farmer_code VARCHAR NOT NULL,        -- external natural key, numeric-looking string on purpose
            national_id VARCHAR NOT NULL,        -- numeric-looking, can have leading zeros
            full_name VARCHAR NOT NULL,
            phone_number VARCHAR,
            region_id INTEGER NOT NULL,
            registered_by_agent_id INTEGER NOT NULL,
            registered_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE
        )
    """,
    "farm_plots": """
        CREATE TABLE farm_plots (
            plot_id INTEGER PRIMARY KEY,
            plot_code VARCHAR NOT NULL,          -- external natural key, numeric-looking string on purpose
            farmer_id INTEGER NOT NULL,
            crop_type_id INTEGER NOT NULL,
            region_id INTEGER NOT NULL,
            latitude DOUBLE,                     -- nullable: not every plot has been GPS-surveyed
            longitude DOUBLE,
            area_hectares DECIMAL(8,2) NOT NULL,
            ownership_status VARCHAR NOT NULL,   -- owned / leased / shared
            polygon_source VARCHAR NOT NULL,     -- gps_survey / manual_estimate / satellite
            updated_at TIMESTAMP NOT NULL
        )
    """,
    "harvest_transactions": """
        CREATE TABLE harvest_transactions (
            transaction_id INTEGER PRIMARY KEY,
            farmer_id INTEGER NOT NULL,
            plot_id INTEGER NOT NULL,
            crop_type_id INTEGER NOT NULL,
            node_id INTEGER NOT NULL,            -- buyer / collection point
            transaction_date TIMESTAMP NOT NULL,
            quantity_kg DECIMAL(10,2) NOT NULL,
            unit_price DECIMAL(10,2) NOT NULL,
            total_value DECIMAL(12,2) NOT NULL,
            moisture_content DECIMAL(5,2),
            grade VARCHAR,
            payment_status VARCHAR NOT NULL,     -- pending / paid
            updated_at TIMESTAMP NOT NULL
        )
    """,
    "custody_events": """
        CREATE TABLE custody_events (
            event_id INTEGER PRIMARY KEY,
            batch_id VARCHAR NOT NULL,
            from_node_id INTEGER,
            from_node_type VARCHAR,
            to_node_id INTEGER NOT NULL,
            event_type VARCHAR NOT NULL,         -- collected / transported / processed / exported
            event_timestamp TIMESTAMP NOT NULL,
            quantity_kg DECIMAL(10,2) NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
    """,
    "batch_transactions": """
        CREATE TABLE batch_transactions (
            batch_id VARCHAR NOT NULL,
            transaction_id INTEGER NOT NULL,
            quantity_allocated_kg DECIMAL(10,2) NOT NULL,
            updated_at TIMESTAMP NOT NULL,
            PRIMARY KEY (batch_id, transaction_id)
        )
    """,
    "certifications": """
        CREATE TABLE certifications (
            certification_id INTEGER PRIMARY KEY,
            plot_id INTEGER NOT NULL,
            certification_body VARCHAR NOT NULL,
            certification_type VARCHAR NOT NULL,
            certificate_number VARCHAR NOT NULL, -- numeric-looking string on purpose
            issued_date DATE NOT NULL,
            expiry_date DATE NOT NULL,
            status VARCHAR NOT NULL,             -- active / expired / revoked
            updated_at TIMESTAMP NOT NULL
        )
    """,
}


def create_source_schema(con, force=False):
    for table, ddl in DDL.items():
        if force:
            con.execute(f"DROP TABLE IF EXISTS {table}")
        con.execute(ddl.replace(f"CREATE TABLE {table}", f"CREATE TABLE IF NOT EXISTS {table}"))
