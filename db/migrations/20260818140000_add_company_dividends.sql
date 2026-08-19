-- migrate:up

CREATE TABLE company_dividends (
    id                      BIGSERIAL PRIMARY KEY,
    company_id              INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    ex_date                 DATE NOT NULL,
    amount                  NUMERIC(18, 6) NOT NULL CHECK (amount > 0),
    currency                CHARACTER VARYING(3) NOT NULL,
    dividend_type           INTEGER NOT NULL,
    distribution_frequency  TEXT,
    source                  TEXT NOT NULL,
    fetched_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_id, ex_date, dividend_type, amount, currency, source)
);

CREATE INDEX idx_company_dividends_company_date
    ON company_dividends (company_id, ex_date);

CREATE TABLE dividend_data_coverage (
    company_id       INTEGER PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
    covered_from     DATE NOT NULL,
    covered_through  DATE NOT NULL,
    source           TEXT NOT NULL,
    fetched_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (covered_from <= covered_through)
);

-- migrate:down

DROP TABLE IF EXISTS dividend_data_coverage;
DROP TABLE IF EXISTS company_dividends;
