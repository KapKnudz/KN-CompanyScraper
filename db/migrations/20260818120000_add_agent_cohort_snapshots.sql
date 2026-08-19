-- migrate:up
CREATE TABLE agent_cohort_snapshots (
    id                              BIGSERIAL PRIMARY KEY,
    snapshot_month                  DATE NOT NULL UNIQUE,
    deterministic_run_id            INTEGER NOT NULL
        REFERENCES ranking_runs(id) ON DELETE RESTRICT,
    policy_version                  TEXT NOT NULL,
    target_size                     INTEGER NOT NULL CHECK (target_size > 0),
    grace_months                    INTEGER NOT NULL CHECK (grace_months > 0),
    eligible_universe_company_ids   JSONB NOT NULL,
    top_company_ids                 JSONB NOT NULL,
    members                         JSONB NOT NULL,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(eligible_universe_company_ids) = 'array'),
    CHECK (jsonb_typeof(top_company_ids) = 'array'),
    CHECK (jsonb_typeof(members) = 'array')
);

-- migrate:down
DROP TABLE IF EXISTS agent_cohort_snapshots;
