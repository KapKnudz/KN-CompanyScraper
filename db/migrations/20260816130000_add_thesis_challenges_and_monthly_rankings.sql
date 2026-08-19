-- migrate:up
CREATE TABLE thesis_challenges (
    id                  BIGSERIAL PRIMARY KEY,
    company_id          INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    thesis_revision_id  BIGINT NOT NULL REFERENCES company_thesis_revisions(id) ON DELETE CASCADE,
    question            TEXT NOT NULL CHECK (length(trim(question)) > 0),
    challenged_claim    TEXT NOT NULL CHECK (length(trim(challenged_claim)) > 0),
    origin              TEXT NOT NULL CHECK (
        origin IN ('human', 'automatic_critic', 'comparative_agent')
    ),
    severity            TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high')),
    verdict             TEXT NOT NULL CHECK (
        verdict IN ('survives', 'revision_required', 'insufficient_evidence', 'reject')
    ),
    status              TEXT NOT NULL CHECK (
        status IN ('open', 'upheld', 'revised', 'rejected')
    ),
    content             JSONB NOT NULL,
    created_by          TEXT NOT NULL,
    resolution_note     TEXT,
    resolved_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_thesis_challenges_open_company
    ON thesis_challenges (company_id, severity, created_at DESC)
    WHERE status = 'open';

ALTER TABLE ranking_runs ADD COLUMN snapshot_month DATE;
CREATE UNIQUE INDEX idx_ranking_runs_monthly_model
    ON ranking_runs (model_version, snapshot_month)
    WHERE snapshot_month IS NOT NULL;

-- migrate:down
DROP INDEX IF EXISTS idx_ranking_runs_monthly_model;
ALTER TABLE ranking_runs DROP COLUMN IF EXISTS snapshot_month;
DROP TABLE IF EXISTS thesis_challenges;
