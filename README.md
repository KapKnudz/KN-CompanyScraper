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
   - `BORSDATA_SYNC_TIME` — nightly Börsdata sync time in scheduler-local `HH:MM` time (default: `02:00`)
   - `BORSDATA_INSIDER_SYNC_TIME` — nightly insider sync time (default: `03:00`)
   - `BORSDATA_API_KEY` — Borsdata API key
   - `OPENAI_API_KEY` — OpenAI API key used by `analyze-shortlist`
   - `OPENAI_MODEL` — optional model override (default: `gpt-5.6-sol`)
   - `OPENAI_REASONING_EFFORT` — optional reasoning effort (default: `medium`)
   - `OPENAI_MAX_OUTPUT_TOKENS` — per-company output cap (default: `6000`)

3. Set up the database:
   ```
   dbmate up
   ```
   Or apply the schema manually from `db/schema.sql`. Migration files are in `db/migrations/`.

## Run

```
python -m kncompanyscraper.main
```

Map active companies to Börsdata instruments, fetch and persist their inputs,
then rank exclusively from the stored PostgreSQL data:

```
python -m kncompanyscraper.main import-watchlist --csv /path/to/watchlist.csv
python -m kncompanyscraper.main map-borsdata
python -m kncompanyscraper.main sync-borsdata
python -m kncompanyscraper.main sync-borsdata-insiders
python -m kncompanyscraper.main rank-watchlist
```

`sync-borsdata` records one durable job result per company and continues if an
individual company fails. Starting the scheduler runs news scraping at the
configured interval and refreshes Börsdata inputs nightly. The sync refreshes
Börsdata sector/branch identities, annual/R12/quarterly reports, full available
price history, and dated KPI snapshots. The general-company ranking uses
per-share growth where share history is available, flags dilution and recent
quarterly slowdowns, and includes ROIC, net debt/EBITDA, operating cash
conversion, margin stability, and free-cash-flow consistency. Property
companies use occupancy, NAV discount/premium, property income, LTV, and
interest coverage in the deterministic ranking. Banks and consumer lenders use
ROE, cost/income, credit losses, CET1, capital adequacy, and LCR. Their ranking
output is labelled `property` or `bank`; other companies use `general`.

The score is a deterministic prioritization input for later analysis, not a
standalone buy/sell signal. Companies missing model-critical data remain visible
with `eligible=no`, but sort after eligible companies and are excluded from the
agent shortlist.

The watchlist importer expects a UTF-8, semicolon-delimited file with the
header `Id;Name;Ticker`. It upserts by Börsdata ID (falling back to ticker),
activates every imported company, and leaves companies not present in the file
unchanged. Running it again is safe and updates the existing rows.

Export model-ready prompts for the current shortlist without calling a model:

```
python -m kncompanyscraper.main export-agent-prompts --output-dir ./agent-prompts
```

Call OpenAI for a deliberately bounded number of shortlisted companies,
validate each structured response, and persist it to PostgreSQL:

```
python -m kncompanyscraper.main analyze-shortlist --max-candidates 1
```

This command makes paid API calls. It requires `OPENAI_API_KEY`; the mandatory
candidate limit prevents accidentally analyzing the entire shortlist.

## Development

Run tests:
```
python -m pytest tests/ -v
```
