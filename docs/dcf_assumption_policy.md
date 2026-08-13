# Reverse DCF assumption policy v8

This policy makes the reverse DCF reproducible and auditable. The deterministic
engine owns every calculation. An agent may critique assumptions, but cannot
replace calculated values.

## Scope and eligibility

The model is FCFF for ordinary operating companies. It does not run for banks,
consumer lenders, or property companies. It requires positive revenue and share
count, Börsdata net debt, a supported report/price currency, and a positive stock
price no more than seven calendar days old.

Positive reported FCF is not an eligibility requirement. Börsdata reported FCF
is retained as a reliability diagnostic, not used as recurring FCFF.

`Report.total_debt` is a legacy field name populated from Börsdata `net_Debt`.

## Börsdata cash-flow limitation

The report schema supplies operating, investing, financing, annual, and free
cash flow. It does not supply separate maintenance capex, growth capex,
acquisitions, disposals, depreciation/amortization, or annual working-capital
changes.

Live KPI metadata labels KPI 64 as `Capex`, but sampled KPI histories show that
it equals aggregate investing cash flow. KPI 93 is `Workingcapital-%`, a balance
sheet ratio rather than an annual working-capital change. Neither can support a
clean recurring FCFF calculation. See
[`borsdata_reverse_dcf_data_audit.md`](borsdata_reverse_dcf_data_audit.md).

## Baseline assumptions

| Assumption | v10 policy | Source |
|---|---:|---|
| Explicit forecast period | 5 years | Fixed policy |
| Year-one revenue growth | -5% to 15% | Annual revenue CAGR over up to three years; disclosed 0% fallback |
| Year-five revenue growth | 2% | Linear fade to fixed mature nominal growth |
| Current EBIT margin | Unclamped | Current R12 or latest annual report |
| Year-five EBIT margin | Unclamped | Revenue-weighted five-year annual margin, then 3y/latest annual/R12 fallback |
| Normalized tax rate | 21% | Fixed Nordic modeling proxy |
| Discount rate | Required-return policy | Dated currency rate + 5% ERP + size + baseline business-risk adjustment |
| Perpetual growth | 2% | Fixed mature nominal-growth policy |
| Net reinvestment | Growth-responsive | Normalized NOPAT × `max(growth, 0) / ROIC`, with reinvestment capped at 100% of NOPAT |

Börsdata ROIC is supplied in percentage points and converted to a fraction. If
ROIC is missing or non-positive, net reinvestment is set to 0% and normalization
confidence is low. Reported FCF never calibrates reinvestment.

## Normalization diagnostics

The result exposes revenue-weighted three- and five-year windows for:

- EBIT margin;
- reported FCF margin; and
- operating-cash-flow margin when available.

Confidence is at most `medium` because clean recurring capex is unavailable. It
is `low` when any of these deterministic checks fires:

- fewer than three valid annual observations;
- one or more non-positive annual reported-FCF years;
- annual FCF-margin standard deviation at least 10 percentage points;
- annual FCF-margin range at least 25 points;
- at least two FCF sign changes;
- FCF standard deviation at least equal to its absolute mean when the mean is at least 1 point;
- a three-year/five-year EBIT or FCF disagreement of at least 5 points;
- the absolute average aggregate investing cash flow is at least 15% of revenue, or an annual value is at least 30%; or
- missing/non-positive ROIC.

Confidence controls how prominently the expectations may be interpreted. It does
does not alter the deterministic ranking because reverse DCF has zero ranking
weight.

## Deterministic calculation

For each explicit forecast year:

1. Linearly interpolate revenue growth from the year-one rate to 2% in year five.
2. `revenue[t] = revenue[t-1] × (1 + revenue growth[t])`
3. Linearly interpolate EBIT margin from the current margin to the year-five margin.
4. `EBIT[t] = revenue[t] × EBIT margin[t]`
5. `NOPAT[t] = EBIT[t] × (1 − tax rate)`
6. `reinvestment share[t] = min(max(revenue growth[t], 0) / ROIC, 100%)`
7. `FCFF[t] = NOPAT[t] × (1 − reinvestment share[t])`
8. Discount FCFF using the required return.

Terminal FCFF recomputes the share of NOPAT reinvested as
`terminal growth / ROIC` rather than carrying the higher explicit-growth
reinvestment rate into perpetuity. Terminal value then uses Gordon growth. Enterprise
value is explicit FCFF plus discounted terminal value. Equity value subtracts
Börsdata net debt and divides by current shares outstanding.

## Reverse solvers

Each solver changes exactly one path endpoint while holding the other baseline
assumptions fixed. Explicit revenue growth starts at the supplied or solved rate
in year one and fades linearly to mature terminal growth in year five. EBIT
margin starts at the current reported margin and fades linearly to the supplied
or solved year-five margin.

| Solved assumption | Bounds | Use |
|---|---:|---|
| Revenue growth | -10% to 30% | Diagnostic cross-check |
| EBIT margin | 0% to 50% | Diagnostic cross-check |
| Perpetual growth | -1% to 4% | Diagnostic only |

If the current price is not attainable within a bound, output is
`outside_bounds` with the modeled endpoint range, direction, and a required-value
hint such as `revenue_growth > 30.0%`. Terminal growth remains visible
for sensitivity review but has zero ranking weight because terminal-value
sensitivity made it outside bounds for 95.5% of the prior 111-company cohort.

## Growth–margin expectation curve

The primary output fixes year-one revenue growth at -5%, 0%, 5%, 10%, 15%, 20%,
25%, and 30%, fades it linearly to mature terminal growth in year five, then
solves the year-five EBIT margin reached linearly from the current reported
margin and required to reproduce the current price. Each solved pair is one
fading path of operating expectations consistent with price, not a forecast and
not a claim that the market expects one unique combination.
The same curve is calculated independently for each supplied discount-rate risk
profile. The one-variable solvers remain visible as cross-checks.

## Ranking policy

Reverse DCF produces no scalar score and does not affect the deterministic
ranking. It supplies auditable expectation paths for qualitative case analysis.

Any change to constants, eligibility, source hierarchy, confidence thresholds,
or formulas requires a new policy version. Historical evaluation must use only
reports, KPI snapshots, rates, and prices available at each observation date.
