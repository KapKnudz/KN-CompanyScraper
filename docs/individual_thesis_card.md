# Individual thesis card v1

`individual-thesis-card-v1` is the common company-level output contract. The
individual analyst receives no peer conclusions and must analyze the supplied
company on its own evidence. The same contract applies to general companies,
property companies, and banks; unsupported valuation methods remain visibly
unavailable rather than being replaced with model arithmetic.

`analysis_status` is separate from the investment `verdict`. A model-backed card
can be persisted only with `analysis_status=complete`. Evidence-blocked,
valuation-blocked, and method-unsupported packets stop at the deterministic
readiness gate and must not be represented as ordinary `watch` conclusions.

## Evidence packet

Each packet contains:

- deterministic rank, category scores, flags, and missing-data indicators;
- calculated financial, valuation, reverse-DCF, sector, and fundamental results;
- the newest 10 annual and 12 quarterly structured reports plus latest R12;
- up to four primary report documents and eight company releases;
- available insider events and completed cyclicality consensus.

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

## Timing

Timing is the catalyst calendar within the fixed case horizon. Each catalyst has:

- a `0_12m`, `12_24m`, `24_48m`, or `uncertain` window;
- an observable confirmation condition;
- a current status;
- evidence source IDs.

An assumption horizon is not itself a catalyst. When `timing_assessment` and the
overall case both specify a horizon, they must match.

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
