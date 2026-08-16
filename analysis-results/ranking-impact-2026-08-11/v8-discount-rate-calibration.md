# Reverse-DCF v8 discount-rate calibration

Validation date: 2026-08-11  
Universe: 153 active companies  
FCFF cohort: 111 available  
Calibration cohort: 31 medium-confidence companies

## Calibration question

Do the current dated risk-free rate, 5% equity-risk premium, size adjustments,
and 2%/4%/7% business-risk adjustments produce coherent differences in
price-implied growth–margin expectations across the stored portfolio?

The objective is not to make demanding market prices appear inexpensive. A
policy change requires evidence of mechanical distortion: unordered profile
results, unusable curves across a profile, or worse implied expectations in the
size buckets receiving lower size premiums.

## Decision

Keep the current discount rates and size thresholds unchanged.

The three profiles produce economically material and correctly ordered curve
shifts. The size-bucket result does not show that micro and small companies are
systematically penalized relative to larger companies. The demanding lower-mid
and upper-mid observations occur despite their lower size adjustments, so
reducing micro/small premiums would not address the portfolio pattern.

## Implemented output improvement

Every deterministic discount-rate profile now includes its own eight-point
growth–margin curve. Previously only the baseline slightly-cyclical profile had a
curve, while the alternate profiles exposed one-variable solves. The analysis
agent can now:

1. classify business risk from cited company evidence;
2. select the matching deterministic profile;
3. read the matching growth–margin curve; and
4. compare it with the supplied historical margins and normalization confidence.

If classification is `unclassified`, agent policy retains the baseline
slightly-cyclical curve and requires disclosure that the profile is unverified.
No agent-created intermediate discount rate is permitted.

## Risk-profile calibration

Results below use only the 31 medium-confidence companies.

| Profile | Median required return | Companies with any solved point | Solved curve points | Median required margin at 10% growth |
|---|---:|---:|---:|---:|
| Noncyclical recurring | 10.8% | 31 / 31 | 223 / 248 | 21.2% |
| Slightly cyclical | 12.8% | 31 / 31 | 208 / 248 | 24.5% |
| Cyclical/other material risk | 15.8% | 28 / 31 | 180 / 248 | 28.6% |

The medians above use solved observations and therefore have survivor effects.
The paired-company comparison is more informative:

| Profile change | Discount-rate change | Paired observations at 10% growth | Median increase in required EBIT margin | Interquartile range |
|---|---:|---:|---:|---:|
| Noncyclical → slightly cyclical | +2 percentage points | 24 | +4.83 points | +3.15 to +7.42 |
| Slightly cyclical → cyclical | +3 percentage points | 19 | +7.05 points | +4.74 to +9.28 |

This is a sensible sensitivity gradient. Higher required returns demand
materially stronger operating economics, and the profiles remain distinct
enough to make evidence-based cyclicality classification consequential.

The cyclical profile has no solved curve point for BioGaia, CellaVision, and
Hemnet. That does not justify widening margins or lowering the rate: it says the
current price cannot be reconciled with the bounded operating assumptions under
that risk lens. Whether the lens is defensible is an evidence-classification
question for the agent.

## Size-bucket calibration

All figures use the baseline slightly-cyclical profile. Required-margin gaps are
relative to the supplied normalized historical EBIT margin at 10% growth and
use solved observations only.

| Bucket | Companies | Baseline required return | Solved curve points | Median required margin at 10% growth | Median margin gap |
|---|---:|---:|---:|---:|---:|
| Micro | 5 | 13.8% | 38 / 40 | 20.3% | +5.0 points |
| Small | 10 | 13.3% | 72 / 80 | 18.7% | +8.3 points |
| Lower mid | 14 | 12.8% | 86 / 112 | 29.2% | +18.7 points |
| Upper mid | 2 | 12.3% | 12 / 16 | 22.4% | +13.9 points |

The upper-mid sample is too small for a threshold decision. More importantly,
the largest observed gaps are not in the buckets with the largest size
adjustments.

### Zero-size-premium counterfactual

Removing the size adjustment lowers the required margin, as it must, but does
not explain the cross-bucket pattern:

| Bucket | Current size adjustment | Current/zero-premium solves at 10% growth | Median margin cost of size adjustment |
|---|---:|---:|---:|
| Micro | 2.0% | 4 / 5 vs 5 / 5 | +4.22 points |
| Small | 1.5% | 9 / 10 vs 9 / 10 | +2.61 points |
| Lower mid | 1.0% | 10 / 14 vs 11 / 14 | +3.82 points |
| Upper mid | 0.5% | 1 / 2 vs 2 / 2 | +1.21 points |

The counterfactual confirms that premiums matter, but not that the existing
thresholds create systematic distortion. Company economics, balance sheets,
ROIC, and market pricing dominate the small cohort comparison.

## Ranking impact

v8 changes deterministic analysis output only. All 153 ranks and total scores
are identical to v7, confirming that profile-specific curves do not leak back
into the ranking after reverse DCF was made diagnostic-only.

## Next validation

The next dependency is the agent's cyclicality classifier. Test a deliberately
diverse sample for citation support, defensibility, correct use of
`unclassified`, and between-run consistency. The rate profiles should not be
recalibrated again until that test establishes how reliably companies are routed
to the curves.
