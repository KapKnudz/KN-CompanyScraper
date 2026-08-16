# Passage-grounded cyclicality rerun — 2026-08-12

## Decision

The new passage-grounded design is a material improvement, but it is **not yet
ready to select valuation curves**. Passage grounding and no-evidence abstention
now work. The remaining blockers are output-contract compliance, an ambiguous
recurrence scale, over-weighting order timing, and incomplete evidence retrieval
for Norsk Titanium.

The production boundary should continue rejecting model-selected profiles.

## Run setup

- Model: `deepseek/deepseek-v4-pro`
- Reasoning effort: high
- Companies: Lime Technologies, Clas Ohlson, Byggpartner, Scandic Hotels,
  BioGaia, and Norsk Titanium
- Three evidence-backed runs per company
- One evidence-withheld control per company
- Maximum 48 application-generated passages per company

The first attempt stopped on an output-length response at 2,000 output tokens.
The retry used a 6,000-token cap and completed all 24 calls. Generation failures
are now retained as failed runs rather than aborting the evaluation.

## Mechanical validation

Strict validation passed for **0/18 normal runs** and **0/6 controls**. The error
distribution across all calls was:

- `missing_information` returned as a string rather than an array: 19 calls
- extra echoed identity fields or another top-level contract mismatch: 4 calls
- empty required rationale: 1 call

These failures mean the run cannot count as a formal pass. Most are mechanical
JSON-contract deviations rather than evidence failures. DeepSeek's JSON-object
mode does not enforce the supplied schema.

## Passage grounding

The normal runs returned **87 passage references**. Every referenced passage ID
resolved to an application-owned excerpt from the supplied evidence. The model
no longer had to reproduce a quote, eliminating the unsupported copied-quote
failure that affected 9/12 evidence-bearing runs in the prior pilot.

All six evidence-withheld controls:

- marked all five dimensions `unclassified`;
- returned zero passage references; and
- made no unsupported classification.

This is a clear pass for conservative no-evidence behavior at the semantic
level, despite the mechanical `missing_information` type mismatch.

## Repeated-run assessment

The table below derives the likely profile from the raw dimension assessments
for diagnostic purposes only. These are not formally accepted results.

| Company | Stable dimension signal | Diagnostic profiles | Assessment |
|---|---|---|---|
| Lime Technologies | Recurrence evidence and moderate demand sensitivity in 3/3 | slightly / slightly / slightly | Directionally defensible, but recurrence polarity was inverted |
| Clas Ohlson | Moderate consumer and input-cost sensitivity in 3/3 | slightly / slightly / slightly | Defensible; some claimed low-risk dimensions use indirect evidence |
| Byggpartner | High macro sensitivity and high project exposure in 3/3 | high-risk / high-risk / high-risk | Strongest and most defensible classification |
| Scandic Hotels | Demand sensitivity in 3/3, severity varied | high-risk / slightly / high-risk | Directionally cyclical, but severity is not stable |
| BioGaia | High order lumpiness in 3/3 | high-risk / high-risk / high-risk | Stable but not defensible as a curve driver from timing evidence alone |
| Norsk Titanium | Mostly unclassified; one moderate project signal | unclassified / unclassified / slightly | Retrieval failure; known project/customer evidence was not surfaced reliably |

Ignoring formal schema failures, exact diagnostic-profile pairwise agreement is
14/18 pairs, or **77.8%**. This is below the proposed 90% threshold and includes
BioGaia's consistently questionable classification.

## Specific findings

### Lime Technologies

DeepSeek consistently cited recurring revenue and ARR, plus cautious customer
behaviour, postponed decisions, and longer sales cycles. Moderate demand
sensitivity supports the baseline slightly-cyclical profile. However, it labelled
`revenue_recurrence` as `low` while explaining that recurring revenue was high.
The scale was interpreted as risk rather than amount of recurrence.

### Clas Ohlson

The moderate demand assessment is supported by management's concern about
customers' willingness and capacity to consume. Moderate material and freight
cost exposure is plausible. Inferring low customer concentration from loyalty
club membership and low order lumpiness from product-range breadth is indirect
and should not receive the same weight as explicit revenue-distribution evidence.

### Byggpartner

This result is well supported. The cited report explicitly says the market is
sensitive to interest rates and the general economy, identifies several large
projects, and describes large project-payment fluctuations. It belongs in the
cyclical-or-other-material-risk lens if the classifier eventually becomes active.

### Scandic Hotels

The evidence directly describes weak demand, room-rate pressure, and expected
demand improvement with the economy. Economic sensitivity is supported, but the
model alternated between moderate and high severity. The deterministic mapping
therefore alternated between the baseline and high-risk profiles.

### BioGaia

The model consistently found regional and quarterly order phasing, including an
approximately SEK 35 million quarterly effect. This supports timing volatility,
not necessarily economic cyclicality or durable business risk. The present rule
incorrectly lets high order timing alone select the high-risk curve, contrary to
the intended policy.

### Norsk Titanium

The passage selector surfaced a purchase order and generic milestone language,
but did not reliably surface enough evidence about customer concentration,
project dependence, or end-market exposure. The classifier mostly abstained.
This is an evidence-retrieval problem rather than evidence that the company is
low risk.

## Required changes before another paid rerun

1. Replace recurrence `low/moderate/high` with unambiguous values such as
   `none_or_limited`, `meaningful`, `predominant`, and `unclassified`.
2. Separate material project or large-order dependence from mere order timing.
   Timing/phasing alone must not select the high-risk curve.
3. Rank and balance passages per dimension instead of taking the first 48
   keyword matches. Ensure customer, project, end-market, and risk-factor
   evidence is represented.
4. Normalize harmless DeepSeek JSON deviations while recording warnings, or use
   a provider/model mode that enforces the complete schema.
5. Require explicit evidence for `low` risk. Large customer-club membership or a
   broad product range is not enough to prove low concentration or lumpiness.
6. Rerun only after local contract fixtures cover these cases.

Raw results are stored in `cyclicality-evaluation-2026-08-12-passages.json`.
