# Reverse DCF assumption policy v2

This policy makes the reverse DCF reproducible and auditable. The deterministic
engine owns every calculation. A human or agent may critique the assumptions,
but cannot replace calculated values.

## Scope and eligibility

The v1 model is FCFF for ordinary operating companies. It does not run for:

- banks and consumer lenders, which require residual-income or dividend models;
- property companies, which require NAV/FFO-oriented models; or
- companies without positive revenue, EBIT, and reported free cash flow.

The calculation also requires a positive share count, Börsdata net debt, matching
report and price currencies, and a positive stock price no more than seven
calendar days old. Missing inputs make the result unavailable; they never receive
silent numeric defaults.

`Report.total_debt` is a legacy field name. Börsdata ingestion populates it from
the API's `net_Debt` value, so the DCF equity bridge subtracts net debt rather
than gross debt.

## Baseline assumptions

| Assumption | v1 policy | Source |
|---|---:|---|
| Explicit forecast period | 5 years | Fixed policy |
| Revenue growth | -5% to 15% | Annual revenue CAGR over up to three years; 0% disclosed fallback if unavailable |
| EBIT margin | Unclamped | Current R12 EBIT/revenue, falling back to latest annual report |
| Normalized tax rate | 21% | Fixed Nordic modeling proxy, not a company tax forecast |
| Discount rate | 10% | Fixed required-return policy |
| Perpetual growth | 2% | Fixed mature nominal-growth policy |
| Net reinvestment rate | -5% to 15% of revenue | `(EBIT × (1 − tax) − reported FCF) / revenue` |

The net-reinvestment assumption deliberately aggregates D&A, capital
expenditure, and changes in working capital because the current canonical report
model does not store those components separately. Reported FCF is therefore a
calibration proxy; this limitation must remain visible in agent context.

## Deterministic calculation

For each explicit forecast year:

1. `revenue[t] = revenue[t-1] × (1 + revenue growth)`
2. `EBIT[t] = revenue[t] × EBIT margin`
3. `NOPAT[t] = EBIT[t] × (1 − tax rate)`
4. `FCFF[t] = NOPAT[t] − revenue[t] × net reinvestment rate`
5. Discount FCFF using the fixed discount rate.

Terminal value uses the Gordon-growth formula. Enterprise value equals the
present value of explicit FCFF plus discounted terminal value. Equity value is
enterprise value minus Börsdata net debt, and per-share value divides equity
value by current shares outstanding.

## Reverse solvers

Each solver changes exactly one assumption while holding every other baseline
assumption fixed:

| Solved assumption | Bounds |
|---|---:|
| Revenue growth | -10% to 30% |
| EBIT margin | 0% to 50% |
| Perpetual growth | -1% to 4% |

If the current price is not attainable inside a bound, the output is
`outside_bounds` and includes the modeled endpoint price range. The engine does
not extrapolate an extreme implied assumption.

## Interpretation and versioning

Reverse DCF answers what one assumption must be for the model to reproduce the
current price, conditional on all other v2 assumptions. It does not show that the
implied assumption is likely or that the baseline policy is uniquely correct.

### Ranking signal

For ordinary operating companies with an available reverse DCF, ranking policy
v2 converts the three implied expectations into an **expectation-headroom**
score. Each implied value is compared with its evidence-based baseline:

- revenue-growth gaps are scaled over ±10 percentage points;
- EBIT-margin gaps are scaled over ±10 percentage points; and
- terminal-growth gaps are scaled over ±2 percentage points.

For each solved assumption, the normalized headroom is
`(baseline − implied) / material gap`. The final normalized headroom is the
median of available components. The median is deliberate: the solvers all
explain the same market price and are correlated sensitivity views, not three
independent observations.

The median is mapped to the 0–100 score with
`100 / (1 + 9^(-normalized headroom))`. A matching implied and baseline
assumption scores 50, half a material gap scores 75 or 25, and a full material
gap scores 90 or 10. The smooth mapping approaches but does not clip finite
values to 100 or 0.

An implied expectation outside its permitted solver bounds is treated as a
censored observation. Its normalized headroom starts at the relevant bound and
is adjusted by `log2(1 + |modeled endpoint − current price| / current price)`.
Thus a distance equal to the current price adds one material gap while preserving
the economically meaningful solver bounds and supporting negative modeled equity
values.

The signal receives 20% weight inside the valuation category when available.
The pre-existing valuation components share the other 80%. When reverse DCF is
unavailable, the remaining weights are normalized so absence neither rewards nor
penalizes the company. The standalone signal is persisted and included in
point-in-time backtest correlations. Scores of at least 70 flag undemanding
expectations; scores of at most 30 flag demanding expectations.

Any change to constants, bounds, eligibility rules, source hierarchy, or formulas
requires a new policy version. Historical evaluation must retain the policy
version and use point-in-time reports and prices to prevent look-ahead bias.
