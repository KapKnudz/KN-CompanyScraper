# KN Company Scraper

Tracks companies, scrapes financial/news data, stores results in PostgreSQL, and optionally notifies Discord when new releases are found.

## Setup

1. Install requirements:
   ```
   pip install -e ".[dev]"
   playwright install chromium
   ```

2. Copy `.env.example` to `.env` and fill in the values:
   - `DATABASE_URL` — PostgreSQL connection string
   - `DISCORD_WEBHOOK_URL` — (optional) Discord webhook for notifications
   - `HEADLESS` — `true` to run Chromium in headless mode
   - `SCRAPE_INTERVAL_MINUTES` — how often to scrape (default: 60)
   - `BORSDATA_API_KEY` — Borsdata API key

3. Set up the database:
   ```
   dbmate up
   ```
   Or apply the schema manually from `db/schema.sql`. Migration files are in `db/migrations/`.

## Run

```
python -m kncompanyscraper.main
```

Fetch and persist Börsdata inputs for the active watchlist, then rank exclusively
from the stored PostgreSQL data:

```
python -m kncompanyscraper.main sync-borsdata
python -m kncompanyscraper.main rank-watchlist
```

## Development

Run tests:
```
python -m pytest tests/ -v
```
