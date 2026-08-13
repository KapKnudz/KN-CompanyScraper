-- migrate:up
CREATE TABLE company_cyclicality_consensus (
    company_id                 INTEGER PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
    classifier_policy_version  TEXT NOT NULL,
    consensus_policy_version   TEXT NOT NULL,
    consensus                  JSONB NOT NULL,
    classified_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- migrate:down
DROP TABLE IF EXISTS company_cyclicality_consensus;
