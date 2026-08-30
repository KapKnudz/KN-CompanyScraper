# Forward scenario sensitivity policy

## Purpose

The forward scenario engine compares ordinary operating-company cases over a
24-, 36-, or 48-month holding period. It produces reproducible sensitivity
ranges, not forecasts, price targets, or probability-weighted expected values.

The model may not assert a forward return or fair value as a free-text claim.
Every displayed number must be produced by
`ForwardScenarioEngine` from individually stated, bounded assumptions with
source IDs and rationales. A third party must be able to reproduce the result
from the stored input bundle.

Banks, lenders, and property companies remain `method_not_supported` until
dedicated residual-income/dividend and NAV/FFO engines exist. They remain
visible in ranking output as insufficient forward-method evidence.

## Holding-period bridge

For each scenario bundle:

```text
Revenue_horizon = Revenue_current × (1 + revenue_CAGR) ^ years
EBIT_horizon = Revenue_horizon × EBIT_margin_horizon
Enterprise_value_horizon = EBIT_horizon × terminal_EV_EBIT
Equity_value_horizon = Enterprise_value_horizon - net_debt_horizon
Value_per_share_horizon = Equity_value_horizon / diluted_shares_horizon
Holding_value_per_share = Value_per_share_horizon + cumulative_distributions_per_share
Annualized_return = (Holding_value_per_share / current_price) ^ (1 / years) - 1
```

Current price, revenue, shares, and net debt are deterministic starting inputs.
Future net debt must reconcile to current net debt plus the stated net-debt
change. Future diluted shares are derived from current shares and the stated
full-horizon decimal-fraction `share_count_growth`.

The persisted analysis also includes a compact capital-allocation bridge for
each case: current and resulting net debt, net-debt change, current and
resulting diluted shares, share-count change, and cumulative distributions per
share. A zero caused by missing data is labelled as an analyst sensitivity; it
is not presented as an evidence-backed forecast.

## Scenario bundles

Every company supplies exactly three complete bundles at one shared horizon:

- bear;
- base; and
- bull.

Each bundle owns one operating state and a low/high terminal EV/EBIT multiple
range. The engine varies only that multiple within the bundle; it never creates
Cartesian extremes by mixing assumptions across cases.

The bear bundle replaces the former public multiple-compression and
fundamental-impairment cases. Its mechanism may identify compression,
fundamental impairment, or both. Bear drivers may not improve on base, and bull
drivers may not worsen from base.

Every assumption must be finite, sourced, and accompanied by a rationale.
Terminal multiples must remain within deterministic historical guardrails.
An out-of-range value makes the analysis `insufficient_evidence`; it cannot be
rescued by a model-authored exception.

The base terminal multiple may not exceed the greater of the current raw
EV/EBIT and the company's historical 25th percentile. The bull terminal
multiple may not exceed the greater of the current raw EV/EBIT and the
historical 75th percentile. Base bundles may not exceed demonstrated revenue
growth or EBIT-margin ceilings. A bull bundle may exceed at most one of its
demonstrated growth, margin, or terminal-multiple ceilings; stacking two or
more makes the scenario insufficient evidence. Growth and margin comparisons
use the versioned absolute tolerance of 0.005; the tolerance applies only to
validation and does not alter valuation inputs.

Management guidance remains a management claim. It may anchor a base endpoint
only when the credibility ledger and current operating evidence support it.
Otherwise it may support only the favorable base endpoint or bull sensitivity.

## Methodology review

The critic reviews both inputs and method:

- common as-of date, currency, current price, and horizon;
- allowed 24-, 36-, or 48-month horizon;
- complete sourced bundles;
- revenue compounding and EBIT-margin units;
- terminal-multiple guardrails and declared exceptions;
- net-debt reconciliation and deterministic diluted-share derivation;
- distribution treatment and absence of double counting;
- bear/base/bull ordering;
- positive, finite equity and holding values; and
- annualization consistency.

Any unresolved high-severity finding moves the company out of the actionable
ranking and into research. Other methodology failures produce a visible
`insufficient_evidence` result; they never silently become null or zero.
An individual thesis cannot be marked `investable` unless its deterministic
forward scenario is `available`.

## Ranking aggregation

The company-specific required return is the hurdle. OMXS30 total return is the
ex-post evaluation benchmark, not a forecast input.

Monthly evaluation freezes both the actionable final-ranking membership and the
contemporaneous top-30 eligible deterministic shortlist. Every completed horizon
requires price, dividend, and currency coverage for every frozen constituent.
Cash dividends are reinvested at the first available close on or after the
ex-date. Agent value added and the OMXS30GI comparison therefore use the same
gross-total-return basis; close-price return remains visible only as a diagnostic.

Screening recall is evaluated at 30 against the frozen eligible deterministic
universe: after each horizon, identify the 30 highest realized gross total returns and
measure the fraction present in that month's persisted research cohort. The
cohort admits current top-30 companies immediately and retains misses for two
monthly grace snapshots before removal. Recall remains pending unless every
eligible-universe company has both boundary prices.

- Tier A: the entire base band clears the hurdle.
- Tier B: the base band overlaps the hurdle.
- Tier C: the entire base band is below the hurdle.
- Tier IE: a valid range cannot be calculated.
- Tier RESEARCH: an unresolved high-severity challenge blocks actionability.

Low evidence confidence lowers A to B or B to C. IE remains visible and cannot
enter A. Within a tier the order is:

1. better bear lower bound;
2. better base lower bound;
3. higher evidence confidence;
4. narrower base band; and
5. better bull lower bound.

After the baseline ranking is frozen, a separate comparative agent may calibrate
only `low`, `medium`, or `high` evidence confidence across the exact stored
theses. Every changed label requires company evidence IDs. Its prose contains no
numbers, and it cannot set tiers, returns, fair values, downside, probabilities,
or scores. The same deterministic aggregation reruns with the calibrated labels
to create the comparative-final ordering. Baseline and comparative-final
memberships remain separate so their subsequent returns can be evaluated
independently.

The bull lower bound is only a final economic tie-break. It cannot compensate
for materially worse downside, base return, or confidence. Bull upper bounds
are display-only sensitivity context.

Numeric comparisons use versioned two-percentage-point annualized-return
buckets. Cases equal on all ranking dimensions share a rank. Monthly snapshots
are immutable. An adjacent A/B or B/C economic-tier move whose relevant base-band
endpoint is within two annualized percentage points of the hurdle is held at the
prior economic tier on its first monthly observation. The same proposed move in
the following monthly snapshot is applied; a reversion clears it. Non-adjacent
or larger economic moves, confidence changes, thesis breaks, insufficient
evidence, and unresolved high-severity findings apply immediately. Both proposed
and effective economic tiers and pending transitions are stored with the monthly
snapshot.
