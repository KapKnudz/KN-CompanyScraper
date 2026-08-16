# Reverse-DCF v2 → v5 ranking-impact report

Analysis date: 2026-08-11  
Universe: 153 active stored Börsdata companies  
Fixed comparison cohort: 111 companies with an available v5 FCFF reverse DCF

## Executive conclusion

Do **not** tune the discount-rate thresholds yet. The ranking order is broadly stable, but the new reverse-DCF expectation signal is systematically compressed toward “very demanding”: its median score falls from 37.1 to 1.1, and 89 of 111 companies score 10 or below.

The dominant issue is FCF normalization, not the size premium. In all 552 inspected company-years, stored Börsdata `free_Cash_Flow` is equal to operating cash flow plus total investing cash flow within 0.1%. It therefore includes acquisition and other investing flows. Averaging this field over five years does not isolate recurring reinvestment and produces extreme margins for acquisition-heavy companies.

The size/risk policy then amplifies the effect by raising the baseline discount rate from the old fixed 10% to 12.3%–13.8% for this cohort. Its isolated direction and magnitude are mechanically sensible, but portfolio calibration is not interpretable until the reinvestment input is made reliable.

## Comparison method

- Old model: Git `HEAD`, `reverse-dcf-v2`, fixed 10% discount rate, current R12 EBIT and FCF margins.
- New model: current worktree, `reverse-dcf-v5`, five-year revenue-weighted EBIT/FCF normalization and dated required-return policy.
- Both versions were rerun on the same stored database inputs on 2026-08-11; no ranking run was persisted.
- Cohort ranks below are recalculated among the fixed 111-company cohort. A positive movement means the company moved up.
- v2 produced a reverse DCF for 88 of these companies. The other 23 were unavailable because current FCF was non-positive; v5 admits all 23 through historical normalization.
- All 111 cohort companies are SEK-denominated and rank-eligible. The remaining active universe contains 40 bank/property companies using other ranking models and two unsupported-currency companies.

## Ranking movement

| Measure | Result |
|---|---:|
| Spearman rank correlation | 0.991 |
| Median absolute movement | 2 places |
| Mean absolute movement | 3.23 places |
| Companies unchanged | 15 |
| Companies moving at least 10 places | 3 |
| Maximum movement | 17 places |
| Median total-score change | -1.3 points |
| Companies with a lower total score | 86 of 111 |
| Top-25 names retained | 23 of 25 |

Top-25 entrants are BioGaia and Apotea; exits are TagMaster and Softronic.

### Largest upward moves

| Company | Old rank | New rank | Move | Old → new reverse-DCF score |
|---|---:|---:|---:|---:|
| White Pearl Technology | 22 | 9 | +13 | 1.5 → 95.9 |
| AQ Group | 53 | 44 | +9 | 4.0 → 2.4 |
| Qualisys | 54 | 46 | +8 | 12.1 → 14.0 |
| C-RAD | 51 | 43 | +8 | 1.7 → 2.6 |
| Bahnhof | 59 | 52 | +7 | 3.4 → 4.4 |
| Vimian Group | 85 | 78 | +7 | 0.7 → 0.2 |
| AddLife | 87 | 80 | +7 | 2.2 → 0.3 |

White Pearl is a normalization warning, not evidence of a genuine improvement: its five annual FCF margins include approximately 243% and 40%, while its three-year versus five-year normalized FCF margins differ by 9.4 percentage points.

### Largest downward moves

| Company | Old rank | New rank | Move | Old → new reverse-DCF score |
|---|---:|---:|---:|---:|
| Catella B | 37 | 54 | -17 | 91.6 → 0.9 |
| Attendo | 42 | 53 | -11 | 83.8 → 12.5 |
| Humana | 77 | 86 | -9 | 80.5 → 12.6 |
| ITAB Group | 90 | 98 | -8 | 98.2 → 0.8 |
| Svedbergs Group | 73 | 81 | -8 | unavailable → 0.2 |
| Ellos Holding | 67 | 75 | -8 | 64.5 → 0.7 |
| Byggpartner | 8 | 15 | -7 | 99.7 → 1.2 |
| TagMaster | 24 | 31 | -7 | 98.0 → 1.3 |

## Implied expectations and bound failures

Medians below use solved cases only, so changes in the solved population also matter.

| Assumption | v2 solved / available | v2 median | v5 solved / available | v5 median | v5 outside bounds |
|---|---:|---:|---:|---:|---:|
| Revenue growth | 57 / 88 | 6.6% | 35 / 111 | 15.8% | 76 (68.5%) |
| EBIT margin | 78 / 88 | 11.7% | 93 / 111 | 21.2% | 18 (16.2%) |
| Terminal growth | 23 / 88 | 1.7% | 5 / 111 | 2.0% | 106 (95.5%) |

Across the same 88 companies available in both versions, total bound failures rise from 106/264 (40.2%) to 151/264 (57.2%). Of the 26 companies where implied revenue growth remains solved in both versions, the median increase is 15.4 percentage points. For the 71 comparable EBIT solves, the median increase is 8.0 points.

The terminal-growth solve is not useful as currently bounded: 95.5% of v5 cases fall outside its -1% to 4% interval. It should not be treated as a stable ranking signal without redesigning the solve or its interpretation.

## Effect of normalized margins

| Diagnostic | Result |
|---|---:|
| Median normalized-minus-current EBIT margin | -0.5 pp |
| Mean absolute EBIT-margin change | 3.4 pp |
| EBIT changes of at least 5 pp | 22 / 111 |
| Median normalized-minus-current FCF margin | -3.4 pp |
| Mean absolute FCF-margin change | 11.0 pp |
| FCF changes of at least 5 pp | 59 / 111 |
| FCF changes of at least 10 pp | 30 / 111 |
| Non-positive normalized FCF margins | 35 / 111 |
| Reinvestment assumptions clamped at +15% | 21 / 111 |
| Reinvestment assumptions clamped at -5% | 6 / 111 |

At a counterfactual fixed 10% discount rate, normalization alone raises the median implied revenue-growth requirement by 5.3 points and the implied EBIT-margin requirement by 3.2 points among cases solved under both old and counterfactual models. Thus normalization already causes material tightening before the new discount policy is applied.

The 23 newly admitted companies all had non-positive current FCF under v2. Their median new reverse-DCF score is only 0.4; 21 of 23 score 1.5 or below. Historical averaging increases coverage, but without a confidence penalty it converts unreliable cash flow into an apparently precise and overwhelmingly negative signal.

### Three-year versus five-year stability

Five full annual observations are present for 107 of 111 companies.

| Difference threshold | Companies |
|---|---:|
| EBIT margin differs by at least 5 pp | 9 |
| FCF margin differs by at least 5 pp | 28 |
| Either margin differs by at least 5 pp | 31 |
| FCF margin differs by at least 10 pp | 12 |

Largest FCF-window disagreements include Surgical Science (+68.6 pp for 3y minus 5y), Swedencare (+61.3 pp), Mips (-26.5 pp), Karnov (+18.5 pp), Catella B (+17.4 pp), EQL Pharma (-15.5 pp), and ShaMaran Petroleum (+15.4 pp). These should show both windows and receive reduced confidence.

## FCF reliability screen

Screen definition over up to five annual FCF margins:

- negative: at least one non-positive annual FCF margin;
- volatile: at least three observations and any of standard deviation ≥10 pp, range ≥25 pp, at least two sign changes, or standard deviation at least equal to the absolute mean when the mean is at least 1 pp;
- unreliable: either negative or volatile.

Results: 78/111 are unreliable, 77 have at least one non-positive year, 68 are volatile, and 67 meet both conditions.

| Company | Negative years | FCF-margin SD | FCF-margin range | Sign changes |
|---|---:|---:|---:|---:|
| Surgical Science | 2/5 | 297.7 pp | 756.4 pp | 2 |
| BioArctic | 4/5 | 211.6 pp | 569.6 pp | 1 |
| Swedencare | 3/5 | 116.3 pp | 251.6 pp | 2 |
| White Pearl Technology | 1/5 | 94.4 pp | 247.0 pp | 2 |
| Yubico | 0/3 | 82.4 pp | 176.1 pp | 0 |
| Karnov | 3/5 | 59.1 pp | 176.2 pp | 3 |
| HMS Networks | 1/5 | 56.5 pp | 146.8 pp | 2 |
| Catella B | 2/5 | 45.2 pp | 138.3 pp | 3 |
| Better Collective | 4/5 | 39.1 pp | 110.9 pp | 1 |
| Mips | 2/5 | 37.7 pp | 96.5 pp | 3 |
| ShaMaran Petroleum | 1/5 | 34.6 pp | 96.3 pp | 2 |
| Svedbergs Group | 2/5 | 33.8 pp | 89.3 pp | 3 |
| Verve Group Media | 4/5 | 32.0 pp | 90.9 pp | 2 |
| Scandinavian Astor | 5/5 | 29.5 pp | 76.7 pp | 0 |
| EQL Pharma | 3/5 | 28.6 pp | 77.2 pp | 1 |

The cash-flow identity check is stronger than a heuristic: all 552 available annual observations satisfy `FCF ≈ operating cash flow + total investing cash flow` within 0.1%. Total investing cash flow mixes capex, acquisitions, and disposals. A proxy screen based on unusually negative investing cash flow flags 32 companies, but current data cannot identify which portion is acquisition spending. Working-capital extremes also cannot be isolated because changes in working capital are not stored separately.

## Discount-rate and size-bucket effects

The v5 baseline is the “slightly cyclical” profile. No company in the cohort is in the large-cap bucket.

| Size bucket | Companies | Size premium | Baseline rate | Revenue solves | Median solved revenue growth | EBIT solves | Median solved EBIT margin |
|---|---:|---:|---:|---:|---:|---:|---:|
| Micro | 24 | 2.0% | 13.8% | 11/24 | 19.7% | 22/24 | 19.6% |
| Small | 37 | 1.5% | 13.3% | 10/37 | 11.6% | 35/37 | 19.0% |
| Lower-mid | 44 | 1.0% | 12.8% | 13/44 | 18.1% | 33/44 | 24.3% |
| Upper-mid | 6 | 0.5% | 12.3% | 1/6 | 17.5% | 3/6 | 35.8% |

The non-monotonic portfolio medians show that company mix dominates simple bucket comparisons. A counterfactual holding normalized economics constant and removing the size premium gives the expected monotonic policy effect:

| Bucket | Added rate | Median increase in implied revenue growth | Median increase in implied EBIT margin |
|---|---:|---:|---:|
| Micro | +2.0 pp | +5.4 pp | +2.2 pp |
| Small | +1.5 pp | +3.8 pp | +1.9 pp |
| Lower-mid | +1.0 pp | +2.8 pp | +2.0 pp |
| Upper-mid | +0.5 pp | +1.4 pp | +1.3 pp |

This is directionally coherent, but the micro-cap growth penalty is large enough to warrant later calibration once FCF is fixed.

### Risk-profile sensitivity

| Profile | Rates across represented buckets | Revenue outside | EBIT outside | Terminal-growth outside | All solves outside |
|---|---:|---:|---:|---:|---:|
| Noncyclical recurring | 10.3%–11.8% | 70/111 | 13/111 | 98/111 | 54.4% |
| Slightly cyclical | 12.3%–13.8% | 76/111 | 18/111 | 106/111 | 60.1% |
| Cyclical / other risk | 15.3%–16.8% | 88/111 | 30/111 | 109/111 | 68.2% |

Moving to a higher-risk profile consistently increases bound failures. The behavior is mechanically sensible, but even the lowest-risk profile has more than half of all solves outside bounds, confirming that discount-rate selection is not the only problem.

## Currency coverage

Two active general-model companies remain unavailable:

- Norsk Titanium — NOK risk-free-rate policy missing.
- Verisure — EUR risk-free-rate policy missing.

No DKK company is currently in the 111-company cohort. NOK, DKK, and EUR policies remain necessary before broader Nordic coverage.

## Recommended sequence

1. Fix normalization before changing discount thresholds. Separate recurring capex from acquisitions/disposals if source data permits; otherwise avoid treating total investing cash flow as recurring reinvestment.
2. Add deterministic confidence checks for negative FCF, volatility, and 3y/5y disagreement. Show both windows for the 31 material disagreements and prevent low-confidence normalized FCF from receiving a full-strength ranking score.
3. Redesign or de-weight the terminal-growth solve, which is outside bounds for 95.5% of the cohort.
4. Rerun this exact impact analysis. Only then calibrate the size premiums and 10%/12%/15% business-risk profiles against stable portfolio-level expectations.
5. Separately validate cyclicality classifications and citations, add NOK/DKK/EUR dated rate snapshots, and replace the historical 3% proxy with actual dated series before backtesting.

## Artifacts

- `company-impact.csv` — one row per cohort company with ranks, scores, margins, implied expectations, size bucket, and FCF reliability diagnostics.
- `old-v2.json` and `new-v5.json` — complete read-only rerun snapshots used for this report.
- `scripts/collect_ranking_impact_snapshot.py` — reproducible snapshot collector.
