# Reverse-DCF v7 validation

Validation date: 2026-08-11  
Universe: 153 active companies  
FCFF cohort: 111 available, 40 bank/property models, 2 unsupported currencies

## Decision

Reverse DCF is now an expectations diagnostic, not a scalar ranking factor. Its
primary output is a growth–margin curve: for each fixed revenue-growth rate, the
model solves the EBIT margin required to reproduce the current share price.
The legacy 0–100 value remains visible for migration diagnostics with a ranking
weight of zero.

This is justified by the portfolio result. The legacy score became even more
compressed after making reinvestment economically responsive to growth: its
median is 0.4 and 101 of 111 companies score 10 or below. It does not contain
enough cross-sectional information to rank companies responsibly.

## Implemented changes

- Explicit-period reinvestment now responds to each modeled revenue-growth rate:
  `NOPAT × min(max(growth, 0) / ROIC, 100%)`.
- Added an eight-point growth–margin expectation curve at revenue growth of -5%,
  0%, 5%, 10%, 15%, 20%, 25%, and 30%.
- Kept one-variable growth, margin, and terminal solves as diagnostic
  cross-checks.
- Outside-bound results now state the direction and required-value hint.
- When growth divided by ROIC consumes all NOPAT, the curve explicitly says why
  changing EBIT margin cannot bridge the price.
- Removed reverse DCF from the weighted valuation calculation. Diagnostic score,
  flags, and explanatory messages remain available to the agent and reviewer.
- Updated the agent policy to interpret the curve as alternative combinations,
  never as one unique market forecast.

## Curve coverage

| Measure | Result |
|---|---:|
| Companies with at least one solved curve point | 98 / 111 (88.3%) |
| Companies with all eight points solved | 57 / 111 (51.4%) |
| Solved curve points | 628 / 888 (70.7%) |
| Companies with no solved curve point | 13 / 111 (11.7%) |
| Companies receiving a full-reinvestment/ROIC warning | 9 / 111 (8.1%) |

The 13 companies without a solved point are not silently capped. Their current
prices require an EBIT margin above the 50% policy bound at every tested growth
rate, or their low historical ROIC causes growth-implied reinvestment to consume
all NOPAT. These are useful findings, not solver failures.

### Required EBIT margin by fixed revenue growth

Medians and interquartile ranges use solved observations only.

| Revenue growth | Solved | Median required margin | Interquartile range |
|---:|---:|---:|---:|
| -5% | 68 | 24.8% | 17.5%–35.8% |
| 0% | 78 | 22.4% | 15.5%–34.5% |
| 5% | 64 | 25.2% | 16.4%–34.8% |
| 10% | 69 | 24.1% | 15.2%–33.9% |
| 15% | 78 | 22.6% | 13.4%–34.2% |
| 20% | 86 | 19.5% | 11.8%–30.9% |
| 25% | 92 | 16.6% | 10.4%–27.5% |
| 30% | 93 | 13.9% | 8.9%–23.0% |

The 0%–5% step is not expected to be monotonic for every company. At 0% growth
the ROIC formula requires no reinvestment; once growth becomes positive, part of
NOPAT must fund it. That trade-off is precisely why a curve is more informative
than a single implied-growth number.

## One-variable solver bounds

| Solve | Solved | Outside bounds | Main outside direction |
|---|---:|---:|---|
| Revenue growth | 18 | 93 (83.8%) | 81 above 30%; 12 below -10% |
| EBIT margin | 75 | 36 (32.4%) | 30 above 50%; 6 not directionally identifiable |
| Terminal growth | 2 | 109 (98.2%) | 51 above 4%; 58 below -1% |

The terminal-growth result confirms the earlier finding rather than solving it:
the scalar terminal solve is structurally uninformative for this cohort. It
remains available only as a sensitivity diagnostic and has no ranking or verdict
weight.

## Normalization reliability

- Low confidence: 80 companies; medium: 31; high: 0 because Börsdata lacks clean
  recurring-capex and working-capital-change series.
- At least one non-positive reported-FCF year: 77 companies.
- Highly volatile annual reported FCF: 68.
- Material aggregate investing flows: 34.
- Material disagreement between three- and five-year margins: 31.
- Positive ROIC unavailable for reinvestment calibration: 7.

Reported FCF and aggregate investing cash flow therefore remain confidence
evidence only. They never calibrate recurring reinvestment. Both three- and
five-year windows remain exposed whenever the average is unstable.

## Size-bucket read-through

| Size bucket | Companies | Any curve point solved | Median solved points | Median margin required at 10% growth | Baseline required return |
|---|---:|---:|---:|---:|---:|
| Micro | 24 | 91.7% | 8.0 | 20.0% | 13.8% |
| Small | 37 | 97.3% | 8.0 | 19.8% | 13.3% |
| Lower mid | 44 | 81.8% | 6.5 | 29.0% | 12.8% |
| Upper mid | 6 | 66.7% | 5.5 | 47.1% | 12.3% |

The demanding upper-mid result does not look like a mechanical size-premium
penalty—that bucket has the lowest required return—and only contains six names.
No discount-rate or size threshold should be changed from this sample alone.
The next calibration should compare company-level curves across the supplied
risk-profile sensitivities and review the outliers.

## Ranking impact versus v6

| Measure | v6 | v7 |
|---|---:|---:|
| Median raw reverse-DCF score | 0.8 | 0.4 |
| Raw score at or below 10 | 97 | 101 |
| Median valuation score | 33.0 | 36.3 |
| Median total score | 47.7 | 48.4 |

Removing the compressed signal produces a controlled change: Spearman rank
correlation is 0.998, median absolute movement is one place, 90% move no more
than three places, and the maximum movement is eleven places. Forty-two of the
111 companies retain exactly the same rank.

## Conclusion and next step

v7 answers the useful reverse-DCF question: *which combinations of sustained
growth and EBIT margin can justify today's price under the explicit return and
reinvestment policy?* It does not pretend that price reveals one unique forecast
or that the result can be compressed into a calibrated quality score.

The next step is discount-rate calibration, not further score tuning. Review the
curve shifts under the noncyclical, slightly cyclical, and cyclical profiles for
the 31 medium-confidence companies first, then decide whether any size or risk
adjustment causes systematic distortion.
