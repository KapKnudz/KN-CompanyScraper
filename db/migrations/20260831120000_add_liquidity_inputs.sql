-- migrate:up

ALTER TABLE stock_prices
    ADD COLUMN volume bigint CHECK (volume >= 0);

CREATE TABLE borsdata_markets (
    id integer PRIMARY KEY,
    name text,
    exchange_name text,
    fetched_at timestamptz NOT NULL DEFAULT NOW()
);

ALTER TABLE companies
    ADD COLUMN market_id integer REFERENCES borsdata_markets(id),
    ADD COLUMN listing_date date;

-- migrate:down

ALTER TABLE companies
    DROP COLUMN listing_date,
    DROP COLUMN market_id;

DROP TABLE borsdata_markets;

ALTER TABLE stock_prices
    DROP COLUMN volume;
