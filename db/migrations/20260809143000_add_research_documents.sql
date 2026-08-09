-- migrate:up
CREATE TABLE research_documents (
    id                  SERIAL PRIMARY KEY,
    company_id          INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    document_type       TEXT NOT NULL,
    title               TEXT NOT NULL,
    url                 TEXT NOT NULL UNIQUE,
    published_at        TIMESTAMPTZ,
    document_text       TEXT NOT NULL,
    source_release_url  TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_research_documents_company_published
    ON research_documents (company_id, published_at DESC);

-- migrate:down
DROP TABLE IF EXISTS research_documents;
