-- migrate:up
CREATE TYPE scrape_status AS ENUM ('running', 'success', 'failed', 'partial');

CREATE TABLE companies (
    id           SERIAL PRIMARY KEY,
    name         TEXT NOT NULL,
    ticker       VARCHAR(10) UNIQUE,
    borsdata_id  INTEGER UNIQUE,
    last_updated TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE company_profiles (
    company_id              INTEGER PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
    description              TEXT,
    business_model           TEXT,
    competitive_advantages   TEXT,
    management               JSONB,
    updated_at                TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE scrape_runs (
    id           SERIAL PRIMARY KEY,
    started_at   TIMESTAMPTZ DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    status       scrape_status NOT NULL DEFAULT 'running',
    errors       JSONB
);

CREATE TABLE watchlist (
    company_id  INTEGER PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
    active      BOOLEAN DEFAULT TRUE
);

-- migrate:down
DROP TABLE IF EXISTS watchlist, scrape_runs, company_profiles, companies CASCADE;
DROP TYPE IF EXISTS scrape_status;