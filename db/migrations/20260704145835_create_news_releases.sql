-- migrate:up
CREATE TABLE news_releases (
    id           SERIAL PRIMARY KEY,
    company_id   INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    slug         TEXT NOT NULL,
    url          TEXT NOT NULL UNIQUE,
    title        TEXT,
    body         TEXT,
    scraped_at   TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_news_releases_slug ON news_releases(slug);

-- migrate:down
DROP TABLE IF EXISTS news_releases;