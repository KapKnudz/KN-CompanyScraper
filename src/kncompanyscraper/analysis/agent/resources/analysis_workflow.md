# Stock-analysis workflow

Follow the steps in order. If a core step cannot be completed, preserve the missing information and lower confidence rather than filling gaps with assumptions.

## 1. Audit the supplied evidence

- Identify the reporting period and freshness of each metric.
- Separate raw values from derived scores and narrative flags.
- List missing data that could materially change the decision.
- Treat the existing ranking as a shortlist mechanism only.
- Cite material factual claims with the supplied `source_id`. Never cite a source ID that is not present in the evidence packet.

## 2. Explain the business model

Describe the customer, problem, product or service, pricing, route to market, gross economics, operating-cost structure, reinvestment needs, and principal dependencies. State whether the business falls within the defined circle of competence.

Populate `business_model_profile` as the normalized comparison layer. Permit
multiple revenue-model types for genuinely hybrid businesses; do not force one
label. `recurring_revenue_profile` describes the economics of the revenue, not
merely repeat customer behavior. Pricing power requires evidence of retained
volume, customers, or economics after price changes. Operating leverage is
`demonstrated` only when supplied report history shows revenue growth accompanied
by slower operating-cost growth or expanding EBIT margins. Cite the exact report
or document source IDs supporting the profile and list unresolved dimensions in
its limitations.

## 3. Apply the profitability gate

Determine whether the company is currently profitable. If not, require an explicit rule exception, document prior profitability where available, identify the expected recovery period, and analyze liquidity, financing, and dilution risk.

## 4. Build the fundamental case

State the two-to-three-year revenue mechanism. Distinguish organic growth from acquisition-driven growth and price from volume where possible.

Estimate a defensible EBIT-margin path. If gross margin is available, investigate the gross-to-EBIT spread. Explain the operational change required for every material margin increase.

Populate `margin_expansion_case` separately from the scenario arithmetic. Its
status identifies whether the mechanism is latent, has early evidence, is
active, stalled, invalidated, not applicable, or unassessable. Name the operating
mechanism and required changes, cite supporting and contrary evidence, and leave
the status unassessable when the mechanism cannot be observed. Do not place a
second qualitative downside estimate here.

Do not use unsupported precision. Give ranges when the evidence only supports ranges.

The main model produces only the qualitative thesis. Forward scenario bundles are
authored by a separate required scenario stage after this response. That stage
receives the bounded deterministic readiness packet and must supply exactly one
bear, base, and bull bundle at one shared 24-, 36-, or 48-month horizon for an
eligible `general` company. Each bundle states sourced revenue CAGR, EBIT margin,
low/high terminal EV/EBIT multiples, net-debt change, full-horizon decimal-fraction
full-horizon decimal-fraction share-count growth, cumulative distributions per share, and a concise operating
`mechanism`. Every assumption requires source IDs and a rationale. Historical
multiple ranges are anchors and optimistic ceilings, not a hard downside floor;
the scenario stage may place bear multiples below historical p10. Leave scenario
authoring to the deterministic readiness boundary for bank/property companies
or genuinely missing inputs; those analyses remain blocked rather than complete.
Deterministic valuation limitations may still be present in the qualitative
thesis; they do not make a ready general-company scenario optional.

`forward_scenario_analysis` must be `null` in the model response. Forward scenario bundles are authored in a separate required stage after this qualitative response. The execution boundary owns all calculated prices and returns. Never state a point estimate or probability weight in prose.

Use `full_results.reverse_dcf.price_fundamental_attribution` to explain material
one-, three-, and five-year share-price moves. Separate the portions accompanied
by revenue, EBIT, EPS, margin, and share-count change from changes in the
price/earnings multiple. A prior price increase is context, never proof of future
returns, but do not call a move speculative when supplied fundamentals explain it.

## 5. Interpret the reverse DCF

Use `full_results.reverse_dcf.expectation_curve` as the primary explanation of what the current price requires. Each point sets year-one revenue growth, which fades linearly to mature terminal growth by year five, and solves the year-five EBIT margin reached linearly from the current reported margin. Present the curve as alternative fading growth–margin paths rather than one unique market forecast. Never describe either endpoint as a constant five-year assumption. Use the one-variable results under `full_results.reverse_dcf.implied_expectations` only as cross-checks; when a solve is outside bounds, report its `required_value_hint` instead of treating the bound as the answer. Terminal growth is diagnostic only and must not drive the verdict or ranking interpretation. Check `full_results.reverse_dcf.normalization` before relying on any solve; when confidence is low, show both supplied three- and five-year windows and explain the exact reliability flags.

Populate `revenue_resilience` from supplied evidence. Distinguish contractual or subscription stickiness from message, transaction, usage, project, or order volume. Discuss observed revenue, margin, or cash-flow variability when supplied; order timing alone is not economic cyclicality evidence. Use `resilient`, `mixed`, or `variable` only with at least one cited fact and explain both recurring and variable drivers. Use `unassessable` when the evidence is insufficient and record the gap in `limitations` rather than inventing a confidence score.
Use `resilient` only with sourced retention, renewal, contractual, or equivalent persistence evidence. Use `mixed` only when the structured recurring and variable drivers are both supported and the business-model profile contains both model types. Repeat demand, consumables, membership, or brand familiarity is not contractual recurrence.
Record recurring and variable driver source IDs separately. A product-sales
business with possible repeat purchases is `variable`, while a
subscription-heavy business with sourced retention or renewal evidence may be
`resilient`; a business with both evidenced mechanisms is `mixed`.

The required return is a deterministic hurdle selected only by the market-cap bucket in `full_results.reverse_dcf.required_return`. The revenue-resilience assessment must not alter it. There is one hurdle, not a profile-specific sensitivity table.

`forward_scenario_analysis` must be `null` in the model response. Do not independently calculate or state a forward fair value, target price, expected return, upside percentage, substitute P/E, EPS, or DCF value. Forward numeric output is valid only when supplied by the deterministic forward-scenario engine from stored sourced bundles; quote its ranges exactly and preserve all methodology and insufficient-evidence flags.

The deterministic engine derives diluted shares from current shares and the
full-horizon decimal-fraction `share_count_growth` assumption.

Deterministic implied expectations carry `source_id` values beginning with `valuation:reverse_dcf:`. Cite material reverse-DCF claims with those exact IDs. For other scalar deterministic metrics that do not carry a `source_id`, cite the exact supplied path beginning with `full_results.`; the execution boundary will normalize a resolvable path to a canonical `deterministic:` ID. Never invent or abbreviate a path.

Set `reverse_dcf_expectation_assessment` to `plausible`, `demanding`, `unsupported`, or `unassessable` and explain the conclusion in `reverse_dcf_expectation_rationale`. Reverse DCF produces no scalar score. These are qualitative evidence labels, never scores, probabilities, or generic valuation grades. Do not assign points or map the labels to numeric thresholds.

Ground the assessment in the company's own record under `full_results.reverse_dcf.operating_history` and cited prospective evidence. Compare required margins with its supplied three- and five-year averages, historical peak, and demonstrated operating leverage. Compare required revenue growth with its annual history, exact three- and five-year CAGRs when available, and cited addressable-market or industry growth evidence. Use `plausible` only when at least one relevant growth–margin combination fits defensible company-specific ranges; use `demanding` when the combinations require performance near historical peaks or materially ahead of supported market growth; and use `unsupported` only when the relevant combinations lack company or industry precedent and the proposed mechanism is speculative. Use `unassessable`, not `unsupported`, when the history, market-growth evidence, or normalization quality is insufficient. Never apply a universal growth or margin cutoff. Identify the exact comparison and missing evidence that drives the label.
When `full_results.financial_history.half_year_comparison` is available, use
its deterministic latest-H1 versus prior-year-H1 comparison as recent context.
It is built only from complete Q1/Q2 pairs; if its limitations say that a
comparable H1 is unavailable, do not infer one from a single quarter.
Standardized financial history is the calculation source for H1 comparisons. If
report prose and standardized values differ, describe both source IDs and the
affected metric or period in `limitations`; do not replace the canonical value.
Deterministic reconciliation is performed only for explicitly supplied
structured report values. Do not parse free-form document prose to manufacture
a mismatch; when no structured report value is available, leave the
reconciliation unavailable.

When `full_results.peer_comparison.status` is `available`, use its dated
metric ranges as a separate sector sanity check. Compare the target's current
metrics and company-history terminal EV/EBIT guardrails with the peer ranges,
but never replace the company-history guardrails or calculate a new valuation
from peer multiples. Peer coverage is additive; missing peers do not block the
core analysis.

Reported FCF is diagnostic only because Börsdata includes aggregate investing cash flow. A 0% net-reinvestment input means positive ROIC was unavailable or baseline growth was non-positive; it does not mean the company requires no reinvestment.

Use supplied deterministic reverse-DCF output as authoritative arithmetic. You may critique assumptions and explain what the current price implies, but do not replace, silently modify, or independently invent calculated values. If deterministic output is unavailable, identify the required inputs rather than presenting model-generated arithmetic as authoritative.

Discuss revenue growth, margin change, balance-sheet change, and dilution qualitatively. Do not invent a numerical return decomposition.

## 6. Assess management

The ledger must separate `claim_source_ids` from `outcome_source_ids`. Report
coverage as eligible, assessed, pending, and omitted material claims, with a
reason for every omission. A sparse ledger is acceptable when the supplied
history contains few eligible claims or insufficient elapsed time.

Evaluate founder or owner-operator alignment, ownership, capital allocation, cost consciousness, customer orientation, and execution. When historical statements are supplied, compare concrete claims with observed outcomes in a credibility ledger.

Keep the narrative assessment readable, but repeat each material conclusion in
`management_claims` as an atomic, section-owned claim. Use `fact` or
`management_claim` for sourced statements and `analyst_inference` for an
interpretation grounded in the cited premises. Every structured claim must cite
the supplied document IDs directly; the global `citations` list is not a
substitute.

## 7. Assess ownership and timing

Analyze insider activity, executed buybacks, short-interest snapshots, ownership changes, average traded value, free float, listing venue, known supply overhangs, and plausible fund or index eligibility. Keep insider transactions, executed company buybacks, short-side positioning, and long-holder ownership analytically distinct; none is a proxy for another. Treat fields suffixed `_raw` as uninterpreted provider values and do not attach percentage, currency, or directional semantics beyond those explicitly supplied. When free-float or holder coverage is unavailable, state that long-ownership conclusions cannot be made and add the gap to `missing_information`.

Use this evidence to modify confidence or timing. Do not allow it to replace the fundamental case.

`ownership_claims` is a closed typed union with no model-authored statement or
destination. Each claim selects a fixed `claim_kind`, `subject_role`, and
`measure`, then supplies the registry's canonical `deterministic_field`, exact
packet value/unit, and exact generated source set from
`research_evidence.ownership_liquidity.source_ids_by_measure`.
Documentary founder/shareholder language cannot authorize an ownership claim.
If that source map has no approved IDs, omit every ownership claim and use only
the deterministic no-data assessment. Changing a documentary citation into an
ownership citation is not permitted. A null deterministic field makes the
measure unavailable; do not substitute insider events, buybacks, liquidity, or
short interest.

Populate `timing_assessment` with the fixed case horizon and observable catalyst
windows: `0_12m`, `12_24m`, `24_48m`, or `uncertain`. Every catalyst must say what
future evidence would confirm it and cite the evidence establishing why it is
expected. Do not invent a numeric confirmation threshold. Use a sourced threshold,
or state the observable direction relative to a cited current or historical baseline.
An assumption horizon alone is not a timing catalyst.

Insider transactions are deliberately supplied as raw events with subsequent unadjusted price returns. Do not convert them into a mechanical score. Compare like-for-like transaction types, roles, sizes, repeated behavior, and the outcomes visible at the evidence cutoff. Do not treat missing future horizons as failed outcomes.

Repeat each material insider conclusion in `insider_claims` with an atomic
statement, an evidence kind, and the exact insider event source IDs supporting
it. Analyst inferences must cite the underlying events. If there are no insider
events, leave the claims empty and use the deterministic no-data wording.

If `insider_event_count` is zero, make no inference from the absence of stored transactions. A company buyback is capital allocation, not an insider transaction, and cannot substitute for insider buying. A synthetic buyback must not be assumed to reduce share count or increase per-share value unless that effect is supplied by deterministic evidence.

## 8. Attempt to disprove the case

State the strongest contrary interpretation. Identify the evidence that would invalidate the revenue mechanism, peak margin, management assessment, financing assumptions, or valuation.

Express the headline case in `falsifiable_case`, reconciled to the same
statement and horizon used elsewhere. Select one sourced decisive item on each
side in `strongest_confirming_evidence` and
`strongest_disconfirming_evidence`. Define separate observable
`thesis_break_tests` for revenue/demand, margin/execution, balance
sheet/dilution, management credibility, valuation overshoot, and superior
evidence/opportunity. Each test needs a current sourced baseline and an explicit
`reassess`, `reduce`, or `sell` response.

After sharp price moves, re-evaluate the evidence independently of the entry price and unrealized profit or loss.

## 9. Produce the verdict

Return the required structured result. Use decimal fractions for rates, for example `0.15` for 15%. Use `null` for unavailable scalar values and list every absence in `missing_information`. For every listed absence, add one matching `missing_information_details` entry with `limitation_class` `core` or `supplemental` and a short explanation of its impact on the conclusion.

Choose `reject`, `watch`, `latent_case`, or `activated_case`. Explain why the selected status is more appropriate than the next-more-positive status. When choosing `latent_case`, set exactly one `latent_case_type` and provide one primary `activation_trigger` plus its structured `activation_trigger_spec`. Use `price` only when the current price or valuation is the blocker; use `operating` only when the return range can clear the hurdle but a named operating mechanism remains unresolved.

Populate the structured company fact ledger with concise, reusable observations rather than thesis prose. Each item must be atomic, identify whether it is a fact, management claim, or analyst inference, and cite original supplied evidence. Use an ISO date for `source_date` when the source date is known. Empty headings are preferable to unsupported entries.

List the material reasons why confidence cannot be higher in `confidence_limitations`. Confidence may be reduced by the deterministic validation boundary when evidence coverage, valuation evidence, or risk classification is incomplete.

Set `portfolio_eligibility` independently and explicitly. Only an
`activated_case` may be `investable`; all other verdicts must be
`not_investable`. Use `portfolio_reason_code` to distinguish valuation-only
exclusion, weak business quality, insufficient evidence, an unactivated thesis,
liquidity, balance-sheet risk, or another stated reason. An investable case must
use the `investable` reason code and no reconsideration trigger. A
`valuation_only` or `thesis_not_activated` exclusion must provide a concrete,
observable `reconsideration_trigger`; do not give a generic lower-price or
better-results statement without identifying what changes the case.
