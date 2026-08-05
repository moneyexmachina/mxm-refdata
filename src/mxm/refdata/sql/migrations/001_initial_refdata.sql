CREATE TABLE {schema}.periods (
    period_id text PRIMARY KEY,
    period_type text NOT NULL,
    first_date date NOT NULL,
    last_date date NOT NULL,

    CONSTRAINT periods_period_id_non_empty
        CHECK (period_id <> ''),

    CONSTRAINT periods_period_type_valid
        CHECK (
            period_type IN (
                'YEAR',
                'QUARTER',
                'MONTH',
                'WEEK',
                'DAY'
            )
        ),

    CONSTRAINT periods_date_order
        CHECK (first_date <= last_date)
);


CREATE TABLE {schema}.period_cycles (
    cycle_id text PRIMARY KEY,
    name text NOT NULL,
    period_type text NOT NULL,
    instance_kind text NOT NULL,
    cycle_size integer NOT NULL,

    CONSTRAINT period_cycles_cycle_id_non_empty
        CHECK (cycle_id <> ''),

    CONSTRAINT period_cycles_name_non_empty
        CHECK (name <> ''),

    CONSTRAINT period_cycles_period_type_valid
        CHECK (
            period_type IN (
                'YEAR',
                'QUARTER',
                'MONTH',
                'WEEK',
                'DAY'
            )
        ),

    CONSTRAINT period_cycles_instance_kind_non_empty
        CHECK (instance_kind <> ''),

    CONSTRAINT period_cycles_cycle_size_positive
        CHECK (cycle_size >= 1)
);


CREATE TABLE {schema}.futures_products (
    product_id text PRIMARY KEY,

    schema_version text NOT NULL,
    asset_class text NOT NULL,

    source_relative_path text NOT NULL,
    source_revision text NOT NULL,
    specification_digest text NOT NULL,
    canonical_specification jsonb NOT NULL,

    venue text NOT NULL,
    description text NOT NULL,
    currency text NOT NULL,
    unit text NOT NULL,
    contract_size double precision NOT NULL,
    valid_period_rule text NOT NULL,
    listing_rule text NOT NULL,
    period_types text NOT NULL,
    settlement text NOT NULL,
    last_trading_rule text NOT NULL,
    expiry_rule text NOT NULL,
    trading_calendar text NOT NULL,

    trading_hours text,
    tick_size double precision,
    tick_value double precision,
    initial_margin double precision,
    maintenance_margin double precision,

    CONSTRAINT futures_products_product_id_non_empty
        CHECK (product_id <> ''),

    CONSTRAINT futures_products_schema_version_non_empty
        CHECK (schema_version <> ''),

    CONSTRAINT futures_products_asset_class_non_empty
        CHECK (asset_class <> ''),

    CONSTRAINT futures_products_source_relative_path_non_empty
        CHECK (source_relative_path <> ''),

    CONSTRAINT futures_products_source_revision_non_empty
        CHECK (source_revision <> ''),

    CONSTRAINT futures_products_specification_digest_sha256
        CHECK (specification_digest ~ '^[0-9a-f]{64}$'),

    CONSTRAINT futures_products_canonical_specification_object
        CHECK (jsonb_typeof(canonical_specification) = 'object'),

    CONSTRAINT futures_products_venue_non_empty
        CHECK (venue <> ''),

    CONSTRAINT futures_products_description_non_empty
        CHECK (description <> ''),

    CONSTRAINT futures_products_currency_non_empty
        CHECK (currency <> ''),

    CONSTRAINT futures_products_unit_non_empty
        CHECK (unit <> ''),

    CONSTRAINT futures_products_valid_period_rule_non_empty
        CHECK (valid_period_rule <> ''),

    CONSTRAINT futures_products_listing_rule_non_empty
        CHECK (listing_rule <> ''),

    CONSTRAINT futures_products_period_types_non_empty
        CHECK (period_types <> ''),

    CONSTRAINT futures_products_settlement_non_empty
        CHECK (settlement <> ''),

    CONSTRAINT futures_products_last_trading_rule_non_empty
        CHECK (last_trading_rule <> ''),

    CONSTRAINT futures_products_expiry_rule_non_empty
        CHECK (expiry_rule <> ''),

    CONSTRAINT futures_products_trading_calendar_non_empty
        CHECK (trading_calendar <> ''),

    CONSTRAINT futures_products_source_relative_path_unique
        UNIQUE (source_relative_path)
);


CREATE TABLE {schema}.period_cycle_memberships (
    cycle_id text NOT NULL,
    period_id text NOT NULL,
    cycle_instance integer NOT NULL,
    cycle_element integer NOT NULL,

    CONSTRAINT period_cycle_memberships_primary_key
        PRIMARY KEY (cycle_id, period_id),

    CONSTRAINT period_cycle_memberships_cycle_foreign_key
        FOREIGN KEY (cycle_id)
        REFERENCES {schema}.period_cycles (cycle_id)
        ON DELETE CASCADE,

    CONSTRAINT period_cycle_memberships_period_foreign_key
        FOREIGN KEY (period_id)
        REFERENCES {schema}.periods (period_id)
        ON DELETE CASCADE,

    CONSTRAINT period_cycle_memberships_instance_positive
        CHECK (cycle_instance > 0),

    CONSTRAINT period_cycle_memberships_element_positive
        CHECK (cycle_element >= 1),

    CONSTRAINT period_cycle_memberships_instance_element_unique
        UNIQUE (
            cycle_id,
            cycle_instance,
            cycle_element
        )
);


CREATE TABLE {schema}.futures_contracts (
    contract_id text PRIMARY KEY,
    product_id text NOT NULL,
    period_id text NOT NULL,

    contract_size double precision NOT NULL,
    unit text NOT NULL,
    currency text NOT NULL,
    trading_calendar text NOT NULL,

    first_day_of_interest date NOT NULL,
    last_trading_day date NOT NULL,

    CONSTRAINT futures_contracts_contract_id_non_empty
        CHECK (contract_id <> ''),

    CONSTRAINT futures_contracts_product_foreign_key
        FOREIGN KEY (product_id)
        REFERENCES {schema}.futures_products (product_id)
        ON DELETE CASCADE,

    CONSTRAINT futures_contracts_period_foreign_key
        FOREIGN KEY (period_id)
        REFERENCES {schema}.periods (period_id)
        ON DELETE CASCADE,

    CONSTRAINT futures_contracts_unit_non_empty
        CHECK (unit <> ''),

    CONSTRAINT futures_contracts_currency_non_empty
        CHECK (currency <> ''),

    CONSTRAINT futures_contracts_trading_calendar_non_empty
        CHECK (trading_calendar <> '')
);


CREATE INDEX futures_contracts_product_id_index
    ON {schema}.futures_contracts (product_id);


CREATE INDEX futures_contracts_period_id_index
    ON {schema}.futures_contracts (period_id);


CREATE INDEX futures_contracts_active_range_index
    ON {schema}.futures_contracts (
        product_id,
        first_day_of_interest,
        last_trading_day
    );


CREATE INDEX periods_date_range_index
    ON {schema}.periods (
        first_date,
        last_date
    );
