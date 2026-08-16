# Reverse-DCF v6 validation

Validation date: 2026-08-11  
Universe: 153 active companies  
FCFF cohort: 111 available, 40 bank/property models, 2 unsupported currencies

## Implemented changes

- Removed Börsdata reported FCF from reinvestment calibration.
- Calibrated explicit-period reinvestment from normalized NOPAT, historical
  revenue growth, and point-in-time Börsdata ROIC.
- Recomputed terminal reinvestment from terminal growth and ROIC instead of
  carrying explicit high-growth reinvestment into perpetuity.
- Exposed revenue-weighted 3y/5y EBIT, reported-FCF, and operating-cash-flow
  margins.
- Added deterministic negative-FCF, volatility, window-disagreement, material
  investing-flow, history-length, and ROIC checks.
- Reduced reverse-DCF valuation weight to 25% of nominal for low confidence and
  50% for medium confidence.
- Retained terminal-growth output as a diagnostic but removed it from ranking.

## Börsdata finding

The report API does not contain clean capex, acquisitions, disposals, D&A, or
annual working-capital changes. Live KPI 64 is labeled `Capex`, but sampled
history equals total investing cash flow; KPI 63 equals KPI 62 plus KPI 64.
KPI 93 is a working-capital percentage, not a working-capital change. See
`docs/borsdata_reverse_dcf_data_audit.md`.

## Portfolio result

| Measure | v5 | v6 |
|---|---:|---:|
| Available FCFF companies | 111 | 111 |
| Median raw reverse-DCF score | 1.1 | 0.8 |
| Raw scores ≤10 | 89 | 97 |
| Revenue-growth solves | 35 | 27 |
| EBIT-margin solves | 93 | 91 |
| Terminal-growth solves | 5 | 2 |
| Median valuation score | 29.7 | 33.0 |
| Median total score | 46.5 | 47.7 |

The raw expectation signal remains systematically harsh after removing
contaminated FCF. This is not hidden: confidence-weighting raises the median
valuation and total scores because the unreliable raw signal has less influence.
Rank order remains stable versus v5 (Spearman 0.996; median absolute movement one
place; maximum movement fourteen places).

## Confidence distribution

- Low: 80 companies.
- Medium: 31 companies.
- High: 0 companies because clean recurring-capex data is unavailable.

Primary flags are high FCF volatility (68), material aggregate investing flows
(34), material 3y/5y disagreement (31), and unavailable/non-positive ROIC (7).

Even the 31 medium-confidence companies have a median raw reverse-DCF score of
1.4, with 23 scoring 10 or below. This is the portfolio-level evidence needed to
move to discount-rate calibration: the harsh distribution is no longer
explainable primarily by acquisition-contaminated FCF.

## Interpretation

v6 fixes data ownership and prevents unreliable normalization from receiving a
full-strength ranking weight. It does not make the raw expectation score look
better by loosening assumptions. The next calibration should test the required
return components and size premiums against the 31 medium-confidence companies
first, while keeping the v6 cash-flow and confidence policy fixed.
