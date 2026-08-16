-- migrate:up
CREATE TABLE company_thesis_revisions (
    id                      BIGSERIAL PRIMARY KEY,
    company_id              INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    revision                INTEGER NOT NULL CHECK (revision > 0),
    previous_revision_id    BIGINT REFERENCES company_thesis_revisions(id),
    source_analysis_id      INTEGER NOT NULL UNIQUE REFERENCES analysis(id),
    change_type             TEXT NOT NULL CHECK (
        change_type IN ('initial', 'full_reassessment', 'incremental_update')
    ),
    evidence_as_of          DATE,
    confidence              TEXT NOT NULL CHECK (confidence IN ('low', 'medium', 'high')),
    confidence_limitations  TEXT[] NOT NULL DEFAULT '{}',
    content                 JSONB NOT NULL,
    created_by              TEXT NOT NULL,
    metadata                JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_id, revision)
);

CREATE INDEX idx_company_thesis_revisions_latest
    ON company_thesis_revisions (company_id, revision DESC);

CREATE TABLE company_facts (
    id                  BIGSERIAL PRIMARY KEY,
    company_id          INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    thesis_revision_id  BIGINT NOT NULL REFERENCES company_thesis_revisions(id) ON DELETE CASCADE,
    heading             TEXT NOT NULL CHECK (heading IN (
        'business_model',
        'revenue_drivers',
        'margins_and_operating_leverage',
        'balance_sheet_and_capital_allocation',
        'management_and_execution',
        'ownership_and_insiders',
        'valuation_expectations',
        'risks_and_disconfirming_evidence'
    )),
    statement           TEXT NOT NULL CHECK (length(trim(statement)) > 0),
    evidence_kind       TEXT NOT NULL CHECK (
        evidence_kind IN ('fact', 'management_claim', 'analyst_inference')
    ),
    source_ids          TEXT[] NOT NULL CHECK (cardinality(source_ids) > 0),
    source_date         DATE,
    reporting_period    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (thesis_revision_id, heading, statement)
);

CREATE INDEX idx_company_facts_company_heading
    ON company_facts (company_id, heading, thesis_revision_id DESC);

-- migrate:down
DROP TABLE IF EXISTS company_facts;
DROP TABLE IF EXISTS company_thesis_revisions;
