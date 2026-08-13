-- migrate:up
CREATE TABLE portfolio_runs (
    id            BIGSERIAL PRIMARY KEY,
    as_of         DATE NOT NULL,
    target_size   INTEGER NOT NULL CHECK (target_size > 0),
    status        TEXT NOT NULL CHECK (status IN ('ready', 'not_ready')),
    content       JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_portfolio_runs_created_at
    ON portfolio_runs (created_at DESC);

-- migrate:down
DROP TABLE IF EXISTS portfolio_runs;
