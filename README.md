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
   - `DEEPSEEK_API_KEY` — DeepSeek API key used with `--provider deepseek`
   - `DEEPSEEK_MODEL` — optional DeepSeek model override (default: `deepseek-v4-pro`)
   - `DEEPSEEK_REASONING_EFFORT` — optional reasoning effort (default: `high`)
   - `DEEPSEEK_MAX_OUTPUT_TOKENS` — per-company output cap (default: `30000`)

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

### Backtesting and DCF ownership

The backtest engine validates the deterministic ranking policy. For each
historical observation date it reconstructs only information then available,
runs the ranking, and measures subsequent 6- and 12-month returns by decile and
score correlation. It is a policy-validation tool, not a valuation calculator,
forecast generator, or substitute for an investment decision.

DCF arithmetic belongs to the deterministic valuation engine. Reverse DCF is
implemented first. Its primary output is a growth–margin expectation curve:
at a fixed set of year-one revenue-growth rates that fade to mature growth, it
solves the year-five EBIT margin reached from the current reported margin and
needed to match the current price. The curve is also supplied for each
deterministic business-risk profile so the agent can select a cited cyclicality
lens. One-variable revenue-growth, EBIT-margin, and terminal-growth
solves remain diagnostic cross-checks. Reverse DCF has zero ranking weight. The FCFF implementation is
for ordinary operating companies. Bank branches are rejected pending a
residual-income/dividend model, and property companies are rejected pending a
NAV/FFO-oriented model.

For eligible operating companies, the analysis compares those implied
expectations with the evidence-based DCF baseline. Reverse DCF produces no
scalar score and cannot change the deterministic ranking.
Reinvestment responds to each modeled growth rate through point-in-time ROIC rather than
Börsdata's acquisition-contaminated reported FCF. Historical backtests reconstruct
the same reverse DCF only from reports, KPI snapshots, and prices available on
each observation date.

The agent may select or challenge assumptions using company evidence and explain
bounded bear/base/bull narratives. It is never the authoritative calculator;
identical valuation inputs must reproduce the same result without a model call.
The complete versioned input hierarchy, constants, solver bounds, equations, and
limitations are in [the reverse DCF assumption policy](docs/dcf_assumption_policy.md).

The watchlist importer expects a UTF-8, semicolon-delimited file with the
header `Id;Name;Ticker`. It upserts by Börsdata ID (falling back to ticker),
activates every imported company, and leaves companies not present in the file
unchanged. Running it again is safe and updates the existing rows.

Export model-ready prompts for the current shortlist without calling a model:

```
python -m kncompanyscraper.main sync-agent-evidence --max-candidates 5
python -m kncompanyscraper.main export-agent-prompts --output-dir ./agent-prompts --max-candidates 5
```

The evidence sync chooses the top eligible companies from the deterministic
ranking. It stores MFN release bodies and extracts text from attached annual,
year-end, and interim-report PDFs. Börsdata's report API supplies standardized
financial statement values, not CEO letters or outlook text; MFN/company report
attachments are therefore the primary textual source. PDF extraction is capped
at the first 30 pages, where the CEO letter and outlook normally appear, and
each stored document retains its publication time and source URL for citations.

Insider transactions are synced separately from Börsdata. They do not contribute
to the deterministic ranking. The agent receives raw transaction details plus
subsequent 90-, 180-, and 365-day unadjusted price returns calculated from stored
Börsdata prices. Missing future horizons remain null and no insider score is
created.

Call OpenAI for a deliberately bounded number of shortlisted companies,
validate each structured response, and persist it to PostgreSQL:

```
python -m kncompanyscraper.main analyze-shortlist --max-candidates 1
```

To retry or analyze exact shortlisted companies without rebilling earlier
candidates, add `--company-ids`, for example:

```
python -m kncompanyscraper.main analyze-shortlist \
  --provider deepseek --max-candidates 2 --company-ids 76 37
```

Use DeepSeek instead while keeping the same policy, evidence packet, local
schema validation, citation checks, and persistence boundary:

```
python -m kncompanyscraper.main analyze-shortlist --provider deepseek --max-candidates 1
```

This command makes paid API calls. It requires the selected provider's API key;
the mandatory candidate limit prevents accidentally analyzing the entire shortlist.
For the five-company shadow pilot, pass `--max-candidates 5` after inspecting
the exported prompts.

Build a durable portfolio-selection run from the latest accepted analyses:

```
python -m kncompanyscraper.main select-portfolio \
  --target-size 5 \
  --output ./analysis-results/portfolio-latest.json
```

Only analyses that explicitly mark an activated case as investable, have at
least medium confidence, use evidence no older than 45 days, and carry a
completed business-risk classification can be selected.
Five qualifying cases receive equal 20% target weights. If fewer qualify, the
run is `not_ready`, weights remain null, and exclusions identify the missing
analysis, stale evidence, valuation, thesis, or risk-concentration reason.

## Development

Run tests:
```
python -m pytest tests/ -v
```
