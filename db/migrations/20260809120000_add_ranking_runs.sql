-- migrate:up

CREATE TABLE ranking_runs (
    id SERIAL PRIMARY KEY,
    run_at TIMESTAMPTZ DEFAULT NOW(),
    model_version TEXT NOT NULL,
    company_count INTEGER NOT NULL,
    eligible_count INTEGER NOT NULL,
    scores JSONB NOT NULL,
    inputs_summary JSONB
);

-- migrate:down

DROP TABLE IF EXISTS ranking_runs;
