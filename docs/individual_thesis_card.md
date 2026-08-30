# Individual thesis card v2

`individual-thesis-card-v2` is the common company-level output contract. The
individual analyst receives no peer conclusions and must analyze the supplied
company on its own evidence. The same contract applies to general companies,
property companies, and banks; unsupported valuation methods remain visibly
unavailable rather than being replaced with model arithmetic.

`analysis_status` is separate from the investment `verdict`. A model-backed card
can be persisted only with `analysis_status=complete`. Evidence-blocked and
method-unsupported packets stop at the deterministic readiness gate. A packet
with valuation limitations may still produce a complete fundamental card, but
the affected reverse-DCF or forward-scenario output remains unavailable and the
card must be portfolio-ineligible. A missing valuation calculation is not by
itself an ordinary `watch` conclusion.

## Evidence packet

Each packet contains:

- deterministic rank, category scores, flags, and missing-data indicators;
- calculated financial, valuation, reverse-DCF, sector, and fundamental results;
- the newest 10 annual and 12 quarterly structured reports plus latest R12;
- deterministic latest-H1 versus prior-year-H1 framing when complete Q1/Q2
  pairs are available;
- up to four primary report documents and eight company releases;
- available insider events and evidence-backed revenue-resilience assessment.
- deterministic peer ranges, included/excluded peer reasons, and metric
  provenance when comparable coverage is available.

Structured report history is bounded to keep one company's packet reviewable
while normally covering a full operating cycle. Every report has a stable
`financial:<period-type>:<period-end>` source ID.

## Business-model profile

The profile is a normalized comparison layer, not a replacement for the atomic
fact ledger. It records:

- a short evidence-backed explanation of how the company makes money;
- fixed descriptions of the customer need, offering, revenue mechanics,
  distribution, cost structure, reinvestment, competitive position, and key
  dependencies;
- one or more revenue-model types, allowing genuine hybrids;
- customer types;
- recurring-revenue economics;
- pricing power;
- capital intensity;
- demonstrated or prospective operating leverage;
- circle-of-competence assessment;
- evidence source IDs and limitations.

Recurring revenue describes contractual or economically persistent revenue, not
merely customers who may return. Pricing power requires evidence that price
changes retained volume, customers, or economics. Operating leverage is
`demonstrated` only when report history shows it; a high gross margin alone is
insufficient. Unsupported dimensions are `unassessable`.

## Margin-expansion case

The card classifies the mechanism as `latent`, `early_evidence`, `active`,
`stalled`, `invalidated`, `not_applicable`, or `unassessable`. It states the
operating mechanism, required changes, supporting sources, contrary sources, and
limitations. It contains no separate downside estimate: numeric downside remains
the deterministic bear-case output.

## Revenue resilience

The card distinguishes contractual or subscription stickiness from transaction,
usage, project, or order volume. It records recurring and variable drivers,
observed revenue, margin, or cash-flow variability, source IDs, and limitations.
`resilient`, `mixed`, and `variable` assessments require positive evidence;
`unassessable` records an evidence gap rather than a confidence score. This
assessment does not select the required-return hurdle.

## Timing

Timing is the catalyst calendar within the fixed case horizon. Each catalyst has:

- a `0_12m`, `12_24m`, `24_48m`, or `uncertain` window;
- an observable confirmation condition;
- a current status;
- evidence source IDs.

An assumption horizon is not itself a catalyst. When `timing_assessment` and the
overall case both specify a horizon, they must match.

## Forward scenarios

General-company cards contain one sourced `scenario_bundles` entry for each of
`bear`, `base`, and `bull`. Each entry has one operating state and a low/high
terminal EV/EBIT multiple range. The execution boundary calculates the
corresponding price and annualized-return bands and stores them in
`forward_scenario_analysis`; the model cannot author those calculated values.
The public bear mechanism may describe multiple compression, fundamental
impairment, or both. Base bands wider than 15 percentage points are
`insufficient_evidence` and cannot enter an actionable ranking.

## Validation

The local boundary rejects:

- a mismatched thesis-card version or evidence cutoff;
- business-model summaries, margin mechanisms, or catalysts without evidence;
- unknown or duplicate source IDs;
- catalyst descriptions without observable confirmation;
- inconsistent timing and case horizons;
- model-authored fair values, expected returns, or downside estimates.

Insufficient evidence remains visible through `unassessable`, limitations,
missing-information fields, and the deterministic confidence cap.
