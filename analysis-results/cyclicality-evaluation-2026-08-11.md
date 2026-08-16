# Agent cyclicality evaluation — 2026-08-11

## Outcome

The classifier is **not yet reliable enough to route companies to discount-rate
curves**. It uses `unclassified` conservatively when evidence is absent, but
evidence-backed citation validity, classification defensibility, and repeated-run
consistency do not pass this pilot.

The evaluated model was `deepseek/deepseek-v4-pro` at high reasoning effort.
The sample was Lime Technologies, Clas Ohlson, Byggpartner, Scandic Hotels,
BioGaia, and Norsk Titanium. Each company received three normal runs plus one
evidence-withheld negative control.

## Data readiness

The first run correctly returned `unclassified` for every company because none
had stored documents. Evidence was then synced from MFN for the same sample.

| Company | Documents supplied | Evaluation role |
|---|---:|---|
| Lime Technologies | 12 | recurring SaaS candidate |
| Clas Ohlson | 12 | consumer demand candidate |
| Byggpartner | 0 | genuine no-evidence case |
| Scandic Hotels | 0 | genuine no-evidence case |
| BioGaia | 12 | healthcare demand candidate |
| Norsk Titanium | 9 | project/customer concentration candidate |

The empty Byggpartner and Scandic feeds are an ingestion-coverage limitation,
not evidence that those businesses are unclassifiable in principle.

## Mechanical results

- Normal validation pass rate: **8/18 (44.4%)**.
- Evidence-bearing validation pass rate: **3/12 (25.0%)**.
- Unsupported verbatim quotes: **9/12 evidence-bearing runs**.
- Other contract failures: **1 normal run and 1 negative control**.
- Negative-control pass rate: **5/6 (83.3%)**. Every valid control selected
  `unclassified` with low confidence and no citations.
- Valid no-evidence normal runs: **5/6**. Every valid run selected
  `unclassified` with low confidence and no citations.

The reported 100% pairwise agreement is not evidence of general consistency.
Only the two no-evidence companies had at least two valid normal runs. Lime,
Clas Ohlson, and BioGaia each had one valid run; Norsk Titanium had none.

## Defensibility review of accepted classifications

### Clas Ohlson — defensible

The accepted `slightly_cyclical` classification cites management's concern
about customers' willingness and capacity to consume, balanced against an
"all-weather" need-based product portfolio. This directly supports moderate
demand sensitivity.

### Lime Technologies — confidence too high

The accepted `noncyclical_recurring` classification cites SaaS subscriptions,
recurring revenue growth, and ARR. Those citations support recurrence, but they
do not establish limited sensitivity to customer budgets or the economic cycle.
The rationale additionally calls CRM software essential and non-discretionary
without cited support. `high` confidence is therefore not defensible from the
supplied evidence.

### BioGaia — classification not supported

The accepted `slightly_cyclical` classification relies on regional order-timing
variation and one quarter's order variability. Timing volatility is not the same
as sensitivity to the economic cycle. The evidence supports lumpy ordering, not
the selected cyclicality profile.

### Norsk Titanium — no valid result

All three runs attempted citations whose quoted text was not present in the
named source. No profile can be assessed from accepted output.

## Decision

Keep `unclassified` mapped to the baseline slightly-cyclical curve. Do not use
classified model output to select another curve yet.

Before rerunning the pilot:

1. Require exact extractive citations or supply stable evidence spans to the
   model; retain raw failed responses for diagnosis.
2. Clarify that recurring revenue alone does not prove noncyclicality, and that
   order timing or quarterly volatility alone does not prove cyclicality.
3. Repair or replace missing MFN mappings for Byggpartner and Scandic Hotels.
4. Repeat the same sample until all evidence-bearing companies have three valid
   runs, then calculate profile agreement.

Raw results are in `cyclicality-evaluation-2026-08-11-with-evidence.json`. The
initial no-document diagnostic is in `cyclicality-evaluation-2026-08-11.json`.
