-- migrate:up
ALTER TABLE thesis_challenges
    ADD COLUMN response_raw_analysis_id BIGINT REFERENCES analysis(id),
    ADD COLUMN response_analysis_id BIGINT REFERENCES analysis(id),
    ADD COLUMN response_thesis_revision_id BIGINT
        REFERENCES company_thesis_revisions(id);

CREATE UNIQUE INDEX idx_thesis_challenges_response_raw_analysis
    ON thesis_challenges (response_raw_analysis_id)
    WHERE response_raw_analysis_id IS NOT NULL;

CREATE UNIQUE INDEX idx_thesis_challenges_response_analysis
    ON thesis_challenges (response_analysis_id)
    WHERE response_analysis_id IS NOT NULL;

CREATE UNIQUE INDEX idx_thesis_challenges_response_revision
    ON thesis_challenges (response_thesis_revision_id)
    WHERE response_thesis_revision_id IS NOT NULL;

-- migrate:down
DROP INDEX IF EXISTS idx_thesis_challenges_response_revision;
DROP INDEX IF EXISTS idx_thesis_challenges_response_analysis;
DROP INDEX IF EXISTS idx_thesis_challenges_response_raw_analysis;
ALTER TABLE thesis_challenges
    DROP COLUMN IF EXISTS response_thesis_revision_id,
    DROP COLUMN IF EXISTS response_analysis_id,
    DROP COLUMN IF EXISTS response_raw_analysis_id;
