-- migrate:up
CREATE TABLE comparative_agent_reviews (
    id                  BIGSERIAL PRIMARY KEY,
    ranking_run_id      INTEGER NOT NULL UNIQUE
        REFERENCES ranking_runs(id) ON DELETE CASCADE,
    status              TEXT NOT NULL CHECK (
        status IN ('pending', 'accepted', 'rejected')
    ),
    raw_response        TEXT NOT NULL,
    content             JSONB,
    final_scores        JSONB,
    created_by          TEXT NOT NULL,
    metadata            JSONB NOT NULL DEFAULT '{}'::JSONB,
    validation_error    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    validated_at        TIMESTAMPTZ,
    CHECK (content IS NULL OR jsonb_typeof(content) = 'object'),
    CHECK (final_scores IS NULL OR jsonb_typeof(final_scores) = 'array')
);

-- migrate:down
DROP TABLE IF EXISTS comparative_agent_reviews;
