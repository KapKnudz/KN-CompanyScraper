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

## Falsifiable case and decisive evidence

`falsifiable_case` makes the headline thesis testable. Its statement is the
same text as `one_sentence_thesis`, while its separate falsification test names
an observable failure condition, uses the fixed case horizon, and cites the
evidence establishing the current baseline.

`strongest_confirming_evidence` and `strongest_disconfirming_evidence` each
select one decision-relevant item with source IDs and an explanation of why it
matters. The older confirming/disconfirming lists remain as broad narrative
support; the decisive fields prevent the key evidence from being buried in
free text.

## Thesis-break tests

`thesis_break_tests` stores observable decision rules under six non-overlapping
types: revenue or demand, margin or execution, balance sheet or dilution,
management credibility, valuation overshoot, and superior evidence or
opportunity. Every test states the condition, metric or event, threshold or
direction, prescribed response, and the evidence establishing its baseline.
The legacy `thesis_break_conditions` strings remain readable for historical
cards, but new analysis should use the structured tests.

## Confidence limitations and latent cases

`missing_information` remains a flattened consumer-facing list. New cards also
store one matching `missing_information_details` object per item, with an
explicit `core` or `supplemental` class and a conclusion-impact explanation.
Only unresolved core items can impose the deterministic medium-confidence cap;
the absence of textual company evidence still caps confidence at low.

`latent_case` is split internally into `latent_case_type=price` and
`latent_case_type=operating`. A price-latent card is a credible business whose
current price is not sufficient, while an operating-latent card has return
capacity but one named operating mechanism remains unproven. Each latent card
stores one structured primary activation trigger. Historical cards without
these fields remain readable and export with a null subtype and no inferred
trigger.

The trigger specification names the unresolved claim, observable metric or
event, threshold or direction, bounded evidence window, and whether one
observation is sufficient. Incremental updates append trigger evidence with
`confirms`, `weakens`, or `unresolved`; they cannot silently start an equivalent
new waiting period. Revenue resilience separately records source IDs for its
recurring and variable drivers. `resilient` requires persistence evidence,
`mixed` requires both supported components, and product or transaction revenue
without contractual stickiness is `variable`.

## Forward scenarios

General-company cards contain one sourced `scenario_bundles` entry for each of
`bear`, `base`, and `bull`. Each entry has one operating state and a low/high
terminal EV/EBIT multiple range. The execution boundary calculates the
corresponding price and annualized-return bands and stores them in
`forward_scenario_analysis`; the model cannot author those calculated values.
The public bear mechanism may describe multiple compression, fundamental
impairment, or both. Base bands wider than 15 percentage points are
`insufficient_evidence` and cannot enter an actionable ranking.

`peak_margin_bridge` is deterministic post-processing. It reports the current
and observed peak EBIT margins, historical gross-to-EBIT spreads, margin
runway, and scenario EBIT margins. Forecast gross margin and forecast
gross-to-EBIT spread remain `null` unless an independently sourced forecast
gross-margin input is added.

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
