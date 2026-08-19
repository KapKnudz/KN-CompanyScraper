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
   - `COMPARATIVE_RANKING_TIME` — daily idempotent monthly-ranking check (default: `04:00`)
   - `BENCHMARK_SYNC_TIME` — daily incremental OMXS30GI refresh (default: `04:10`)
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
python -m kncompanyscraper.main sync-borsdata-dividends
python -m kncompanyscraper.main sync-borsdata-insiders
python -m kncompanyscraper.main rank-watchlist
```

Annual ROIC and net-debt/EBITDA histories are included in the regular Börsdata
sync. Existing databases can backfill only those point-in-time series with:

```
python -m kncompanyscraper.main sync-fundamental-history
```

Use `sync-borsdata-dividends` for an initial or repaired dividend-only backfill;
it batches up to 50 instruments per Börsdata call. `sync-borsdata` records one
durable job result per company and continues if an
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

The research workload uses an immutable monthly cohort rather than rebuilding a
volatile shortlist on every command. The top 30 eligible deterministic companies
enter immediately. An incumbent that falls outside the top 30 remains for two
grace snapshots and exits on its third consecutive monthly miss, so new entrants
can temporarily lift the cohort above 30. Refresh or inspect the current month's
cohort with:

```
python -m kncompanyscraper.main refresh-agent-cohort
```

Prompt export, initial analysis, thesis updates, and evidence synchronization all
consume this persisted cohort automatically.

### Backtesting and DCF ownership

The backtest engine validates the deterministic ranking policy. For each
historical observation date it reconstructs only information then available,
runs the ranking, and measures subsequent 6- and 12-month gross total returns by
decile and score correlation. Cash dividends use the same coverage-certified
ex-date reinvestment calculator as monthly ranking evaluation. Each period also
records OMXS30GI gross total return, top-decile excess, coverage counts, and exact
company IDs excluded from return statistics. It is a policy-validation tool,
not a valuation calculator, forecast generator, or substitute for an investment
decision.

Export company-level diagnostics for every reconstructed period with:

```
python -m kncompanyscraper.main backtest \
  --periods 24 \
  --attribution-csv ./analysis-results/backtest-attribution.csv \
  --scoring-audit-csv ./analysis-results/scoring-audit.csv
```

Each row retains historical rank and decile, all deterministic component scores,
coverage-certified total and price returns, return issues and end dates, and the
company's additive contribution to its decile average. It also includes the
point-in-time market capitalization, sector, ranking model, and matching benchmark
return needed for controlled weight diagnostics.
The optional long-form scoring audit contains every general-model metric's raw
value, transformation, configured and missingness-adjusted effective weight,
category and total-score contribution, underlying dependencies, and any
cross-category dependencies. Its reconstruction error detects drift between the
audited formula and production scoring without changing ranking behavior.
Historical reconstruction uses the fundamental KPI value for the same annual
report year already admitted by the 90-day publication lag. Recent growth uses
only matching quarterly reports admitted by the 45-day lag; neither path falls
back to today's snapshot.
The aggregate report also shows median and positive-month consistency for
top–bottom spreads and OMXS30GI excess. These are explicitly labelled as
overlapping monthly observations, not independent statistical trials.

Analyze bounded five-percentage-point weight candidates without changing the
production ranking policy:

```
python -m kncompanyscraper.main calibrate-weights \
  --attribution-csv ./analysis-results/backtest-attribution.csv \
  --ranking-model general \
  --horizon-months 12
```

The diagnostic selects on the chronological first half and reports the second
half separately. It also reports component ablations and correlations after
sector and market-cap-tercile demeaning. Alongside the top-decile diagnostics,
it reports the realized excess return of the actual top-30 agent shortlist and
its spread over the rest of the eligible universe. A candidate cannot be declared ready
unless at least four non-overlapping outcome windows exist and it improves both
holdout OMXS30GI excess and holdout top-minus-bottom spread. It never writes new
production weights. Six-month results are a robustness check only; the longer
12-month outcome is the primary calibration gate.

After generating the long-form scoring audit, inspect internal metrics without
changing production policy:

```
python -m kncompanyscraper.main analyze-scoring-audit \
  --scoring-audit-csv ./analysis-results/scoring-audit.csv \
  --horizon-months 12
```

The report reconstructs the frozen ranking after removing one metric at a time,
shows first-half and chronological-holdout changes in benchmark excess and
top-minus-bottom spread, and lists highly correlated metrics, shared raw inputs,
and explicit cross-category dependencies. It also tests every available metric
at half and double its within-category weight and rescales supported scoring
thresholds by ±20%. These are bounded sensitivity diagnostics, not an optimizer.
Monthly cohorts remain overlapping, so the command never modifies a metric or
weight automatically.
It also evaluates named challengers that remove EV/EBIT percentile, remove net
margin, remove both together, or recompute margin of safety with neutral quality
and growth inputs. These counterfactuals remain audit-only.

Persist the accepted combined removal as a versioned monthly challenger, then
evaluate each matured monthly horizon:

```
python -m kncompanyscraper.main rank-watchlist
python -m kncompanyscraper.main snapshot-ranking-challenger
python -m kncompanyscraper.main evaluate-ranking-challengers \
  --max-horizon-months 48
python -m kncompanyscraper.main report-ranking-challengers
```

The challenger is explicitly `evaluation_only` and lives outside `ranking_runs`,
so it cannot reorder the production shortlist or change agent-cohort membership.
Each monthly snapshot freezes both production and challenger top-30 company IDs.
At the 1-, 3-, 6-, 12-, 24-, 36-, and 48-month horizons, matured results use the same reviewed
gross-total-return calculation as ranking performance. They report production
and challenger top-30 returns, excess over OMXS30GI, full-universe Spearman rank
correlation, top-minus-bottom decile spreads, and entrant-minus-exit attribution.
The same forward report separates general, property, and bank rank correlation
and spread so sector-specific rules can accumulate evidence even when Börsdata
does not expose their current-only screener KPIs through historical endpoints.
Missing price, dividend, currency, or benchmark coverage keeps a horizon pending
instead of computing rank statistics from a partial universe.

Historical attribution and metric-audit exports include 6-, 12-, 24-, 36-, and
48-month company and OMXS30GI total returns. Request enough monthly periods to
reach old, fully matured long-horizon observations, for example:

```
python -m kncompanyscraper.main backtest --periods 72 \
  --attribution-csv ./analysis-results/backtest-attribution-72m.csv \
  --scoring-audit-csv ./analysis-results/scoring-audit-72m.csv

python -m kncompanyscraper.main calibrate-weights \
  --attribution-csv ./analysis-results/backtest-attribution-72m.csv \
  --ranking-model general --horizon-months 24
```

Long-horizon results are required investment-horizon evidence, while the
previously accepted 12-month calibration remains the primary production gate.
No single horizon can update production weights automatically.

Dividend events that individually equal or exceed their reinvestment price, or
that push the unreviewed reinvestment multiplier above 2x, are quarantined rather
than capped or silently omitted. Inspect and resolve exact stored events without
deleting their source record:

```
python -m kncompanyscraper.main audit-dividends \
  --company-id 154 --after 2025-07-31 --through 2026-07-31

python -m kncompanyscraper.main review-dividends \
  --company-id 154 --after 2025-07-31 --through 2026-07-31 \
  --status excluded \
  --reason "Preference-share distributions attached to NAVIGO STAM" \
  --evidence-url "https://navigoinvest.com/wp-content/uploads/2025/04/NavigoInvestAR2024_Uppslag-2.pdf"
```

`pending` blocks total-return evaluation, `approved` permits verified exceptional
cash distributions, and `excluded` retains but omits a mismatched event. Reviews
use the event's stable natural key and therefore survive calendar replacement.

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
python -m kncompanyscraper.main check-agent-readiness --max-candidates 5
python -m kncompanyscraper.main export-agent-prompts --output-dir ./agent-prompts --max-candidates 5
```

The readiness check is deterministic and makes no model call. It reports missing
primary evidence, stale or missing prices, incomplete risk classification,
unavailable terminal-multiple guardrails, and unsupported company methods. The
paid analysis command runs the same gate before constructing any prompt and
fails the full requested batch if a candidate is blocked.

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

Each accepted stock analysis also creates a versioned company-thesis revision.
The response is an `individual-thesis-card-v1` with one shared schema for
general, property, and bank candidates. Its evidence packet includes the latest
ten annual reports, twelve quarterly reports, and latest rolling-12-month report
as structured financial records, in addition to calculated financial results and
textual primary-source evidence. Each structured report has a stable
`financial:*` source ID.

The card normalizes the business model across revenue model, customer types,
recurring-revenue economics, pricing power, capital intensity, operating
leverage, and circle of competence. Hybrid revenue models may carry more than
one label; unsupported dimensions remain `unassessable`. It also separates the
margin-expansion mechanism from deterministic scenario arithmetic and defines
timing through sourced, observable catalyst windows. See
`docs/individual_thesis_card.md` for the field policy.

Its structured fact ledger keeps concise observations under fixed business-model,
revenue, margin, balance-sheet, management, ownership, valuation, and risk headings.
Every populated fact retains its original evidence source IDs and distinguishes
reported facts, management claims, and analyst inferences. Older accepted analyses
are retained as initial thesis revisions, so later evidence updates can compare
against the current thesis without rebuilding the case from an empty state.

For ordinary operating companies, the analysis contract may also submit eight
sourced forward-sensitivity assumption bundles at a shared 24-, 36-, or
48-month horizon. The local execution boundary—not model prose—recalculates the
multiple-compression bear, fundamental-impairment bear, base, and bull return
bands. Terminal EV/EBIT assumptions are checked against the company's positive
historical 10th–90th percentile range when at least five observations exist.
Missing inputs, invalid bundle coherence, and unsupported bank/property methods
remain visible as insufficient evidence.

Persist an immutable comparative snapshot from the latest accepted individual
theses:

```
python -m kncompanyscraper.main rank-analyzed-candidates \
  --output ./analysis-results/comparative-ranking-latest.json
```

The combined ranking uses the company-specific required-return hurdle, then
orders within tiers by calculated bear downside, base return, evidence
confidence, band width, and finally the bull lower bound. It permits ties and
persists the exact analysis IDs used in `ranking_runs` for later monthly return
evaluation. Adjacent A/B or B/C economic-tier changes within two annualized
percentage points of the hurdle require the same signal in two consecutive
monthly snapshots. Larger moves, confidence changes, missing evidence, thesis
breaks, and critic blocks apply immediately; proposed, pending, and effective
tiers are all retained for audit.

Run the separate comparative verdict agent once for a monthly snapshot:

```
python -m kncompanyscraper.main adjudicate-monthly-ranking \
  --ranking-run-id 60 \
  --provider openai
```

This agent cannot author returns, fair values, downside estimates, probabilities,
tiers, or scores. It compares the frozen individual theses and returns only a
source-linked confidence calibration for every company. The deterministic
hurdle/downside ranker then reruns with those calibrated confidence labels, which
can reorder or downgrade cases without introducing a second valuation source of
truth. The raw response, accepted calibration, and resulting final ranks are
stored once per monthly snapshot; rejected responses are revalidated without a
second model call.

Each monthly snapshot also freezes its actionable company IDs and the top 30
eligible companies from the latest deterministic ranking. Sync the official
OMXS30 gross-total-return series (`OMXS30GI`) directly from Nasdaq, then evaluate
every completed monthly horizon. A reproducible `date`/`close` CSV import remains
available as a manual fallback:

```
python -m kncompanyscraper.main sync-omxs30gi

# Manual fallback for a previously downloaded Nasdaq export converted to CSV:
python -m kncompanyscraper.main import-benchmark-prices \
  --csv ./data/omxs30gi.csv \
  --series-code OMXS30GI \
  --return-basis gross_total_return \
  --source "Nasdaq OMXS30GI history export"

python -m kncompanyscraper.main evaluate-ranking-performance \
  --max-horizon-months 48

python -m kncompanyscraper.main report-ranking-performance \
  --limit 24
```

After the initial sync, both the command and the daily scheduler request only a
seven-day overlap from the latest stored observation. The overlap permits Nasdaq
corrections to be upserted before the daily ranking-performance check.

The normal `sync-borsdata` run also stores Börsdata's historical dividend
calendar and a per-company coverage window tied to the stored price history.
An omitted instrument or malformed historical dividend fails that company's
sync; it is never interpreted as a zero dividend.

Evaluation is equal-weighted and requires complete price, dividend, and currency
coverage for every frozen member. Gross cash dividends are grouped by ex-date
and reinvested at the first available close on or after that date. Raw
close-price return is retained beside gross total return for diagnosis, but all
ranking comparisons use gross total return. Agent value added is the
comparative-final actionable ranking's total return minus the deterministic
shortlist's like-for-like return. The evaluator separately records the
incremental contribution of comparative calibration over the individual-thesis
ranking. Excess versus OMXS30GI is labelled
`gross_total_return_vs_gross_total_return`. The scheduler retries due horizons
daily after the monthly ranking check, and completed evaluations are immutable.
Recall at 30 is the share of the frozen eligible universe's 30 best subsequent
gross total returns that belonged to the monthly research cohort; incomplete
coverage remains visibly pending rather than being zero-filled.
The report command is read-only: it shows the deterministic, individual-thesis,
and comparative-final stages independently, alongside price-return diagnostics,
benchmark attribution, recall, and exact company IDs blocking completion.

Challenge an exact stored thesis revision using only the evidence that belonged
to that revision:

```
python -m kncompanyscraper.main grill-thesis \
  --company-id 42 \
  --question "What evidence supports the assumed peak EBIT margin?"
```

The command makes one paid model call and persists the claim, cited findings,
severity, decision impact, and original evidence IDs. An open high-severity
challenge automatically moves the company out of the actionable ranking and
into `RESEARCH`. Give the original analyst one response using that same frozen
evidence packet:

```
python -m kncompanyscraper.main respond-to-thesis-challenge \
  --challenge-id 7
```

The response must pass the complete thesis validation and forward-scenario
calculation boundary before the challenge can resolve. A preserved thesis resolves
as `upheld`; a persisted material revision resolves as `revised`. A response that
requires full reassessment or fails validation leaves the challenge open. Its raw
reply is retained and revalidated on retry, so the loop never buys a second analyst
response. The challenge stores links to both the accepted analysis and its thesis
revision.

An operator can still resolve exceptional cases without rewriting the audit content:

```
python -m kncompanyscraper.main resolve-thesis-challenge \
  --challenge-id 7 \
  --status revised \
  --note "Thesis revision 4 replaced the unsupported margin assumption."
```

The scheduler checks comparative ranking daily at
`COMPARATIVE_RANKING_TIME`, but a database uniqueness constraint permits only
one combined snapshot per calendar month. If no accepted analyses exist, it
waits and retries the next day.

After syncing new reports, releases, insiders, and deterministic inputs, update
existing theses without resending their original document packets:

```
python -m kncompanyscraper.main update-shortlist \
  --provider deepseek --max-candidates 5
```

The update command calls the model only when it finds a previously unseen source
ID or a changed deterministic-context hash. It supplies the current thesis and
fact ledger, persists a complete linked snapshot for accepted incremental updates,
and reports when a company instead requires a full reassessment.
If a response was rejected because a local validation defect was subsequently
fixed, add `--retry-rejected` to revalidate the stored response without another
paid model call.

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
