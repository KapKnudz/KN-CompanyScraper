-- migrate:up
CREATE TABLE ranking_challenger_snapshots (
    id                          BIGSERIAL PRIMARY KEY,
    snapshot_month              DATE NOT NULL,
    source_ranking_run_id       INTEGER NOT NULL REFERENCES ranking_runs(id) ON DELETE RESTRICT,
    source_as_of                DATE NOT NULL,
    policy_version              TEXT NOT NULL,
    status                      TEXT NOT NULL CHECK (status = 'evaluation_only'),
    company_count               INTEGER NOT NULL CHECK (company_count > 0),
    eligible_count              INTEGER NOT NULL CHECK (eligible_count >= 0),
    affected_company_count      INTEGER NOT NULL CHECK (affected_company_count >= 0),
    scores                      JSONB NOT NULL,
    production_top_company_ids  JSONB NOT NULL,
    challenger_top_company_ids  JSONB NOT NULL,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (snapshot_month, policy_version)
);

CREATE INDEX idx_ranking_challenger_source_run
    ON ranking_challenger_snapshots (source_ranking_run_id);

CREATE TABLE ranking_challenger_performance_evaluations (
    id                      BIGSERIAL PRIMARY KEY,
    challenger_snapshot_id  BIGINT NOT NULL REFERENCES ranking_challenger_snapshots(id) ON DELETE CASCADE,
    horizon_months          INTEGER NOT NULL CHECK (horizon_months > 0),
    target_date             DATE NOT NULL,
    status                  TEXT NOT NULL CHECK (status IN ('pending', 'complete')),
    policy_version          TEXT NOT NULL,
    result                  JSONB NOT NULL,
    evaluated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (challenger_snapshot_id, horizon_months)
);

CREATE INDEX idx_ranking_challenger_performance_status_target
    ON ranking_challenger_performance_evaluations (status, target_date);

-- migrate:down
DROP TABLE IF EXISTS ranking_challenger_performance_evaluations;
DROP TABLE IF EXISTS ranking_challenger_snapshots;
