-- migrate:up
DROP INDEX IF EXISTS idx_ranking_runs_monthly_model;
CREATE UNIQUE INDEX idx_ranking_runs_monthly_model
    ON ranking_runs (snapshot_month)
    WHERE snapshot_month IS NOT NULL;

-- migrate:down
DROP INDEX IF EXISTS idx_ranking_runs_monthly_model;
CREATE UNIQUE INDEX idx_ranking_runs_monthly_model
    ON ranking_runs (model_version, snapshot_month)
    WHERE snapshot_month IS NOT NULL;
