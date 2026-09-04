-- migrate:up

CREATE TABLE mfn_feed_checks (
    company_id       INTEGER PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
    checked_at       TIMESTAMPTZ NOT NULL,
    discovered_count INTEGER NOT NULL CHECK (discovered_count >= 0),
    unseen_count     INTEGER NOT NULL CHECK (unseen_count >= 0)
);

-- migrate:down

DROP TABLE IF EXISTS mfn_feed_checks;
