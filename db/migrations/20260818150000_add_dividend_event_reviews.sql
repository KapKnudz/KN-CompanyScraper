-- migrate:up

CREATE TABLE dividend_event_reviews (
    company_id     INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    ex_date        DATE NOT NULL,
    amount         NUMERIC(18, 6) NOT NULL CHECK (amount > 0),
    currency       CHARACTER VARYING(3) NOT NULL,
    dividend_type  INTEGER NOT NULL,
    source         TEXT NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'excluded')),
    reason         TEXT NOT NULL,
    evidence_url   TEXT,
    reviewed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, ex_date, amount, currency, dividend_type, source)
);

-- migrate:down

DROP TABLE IF EXISTS dividend_event_reviews;
