-- migrate:up

CREATE TABLE company_buyback_events (
    company_id integer NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    event_date date NOT NULL,
    change_shares bigint NOT NULL,
    change_pct_raw numeric,
    reported_price numeric,
    currency varchar(3),
    treasury_shares bigint,
    treasury_shares_pct_raw numeric,
    source text NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT NOW(),
    raw_payload jsonb NOT NULL,
    PRIMARY KEY (company_id, event_date, source)
);

CREATE TABLE company_short_snapshots (
    company_id integer NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    observation_date date NOT NULL,
    short_pct_raw numeric,
    reported_holder_count numeric,
    average_short_pct_raw numeric,
    short_value_millions_raw numeric,
    average_short_value_millions_raw numeric,
    last_transaction_date date,
    days_to_cover_sum numeric,
    days_to_cover_average numeric,
    trend_1w numeric,
    trend_1m numeric,
    trend_3m numeric,
    trend_6m numeric,
    source text NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT NOW(),
    raw_payload jsonb NOT NULL,
    PRIMARY KEY (company_id, observation_date, source)
);

-- migrate:down

DROP TABLE company_short_snapshots;
DROP TABLE company_buyback_events;
