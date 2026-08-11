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

## 3. Apply the profitability gate

Determine whether the company is currently profitable. If not, require an explicit rule exception, document prior profitability where available, identify the expected recovery period, and analyze liquidity, financing, and dilution risk.

## 4. Build the fundamental case

State the two-to-three-year revenue mechanism. Distinguish organic growth from acquisition-driven growth and price from volume where possible.

Estimate a defensible EBIT-margin path. If gross margin is available, investigate the gross-to-EBIT spread. Explain the operational change required for every material margin increase.

Do not use unsupported precision. Give ranges when the evidence only supports ranges.

## 5. Interpret the reverse DCF

Use `full_results.reverse_dcf.expectation_curve` as the primary explanation of what the current price requires. Each point fixes revenue growth and solves the matching EBIT margin, so present the curve as alternative growth–margin combinations rather than one unique market forecast. Use the one-variable results under `full_results.reverse_dcf.implied_expectations` only as cross-checks; when a solve is outside bounds, report its `required_value_hint` instead of treating the bound as the answer. Terminal growth and the legacy scalar reverse-DCF score are diagnostic only and must not drive the verdict or ranking interpretation. Check `full_results.reverse_dcf.normalization` before relying on any solve; when confidence is low, show both supplied three- and five-year windows and explain the exact reliability flags.

Classify the business as `noncyclical_recurring`, `slightly_cyclical`, or `cyclical_or_other_risk` only when supplied evidence supports the demand cyclicality, revenue recurrence, customer dependence, commodity exposure, or another material risk. Otherwise use `unclassified`. Put the exact supporting source IDs in `risk_profile_evidence` and calibrate `risk_profile_confidence` to the evidence quality.

Use the matching profile under `full_results.reverse_dcf.discount_rate_sensitivities` when discussing that classification, and use that profile's `expectation_curve` rather than the baseline curve. If the risk profile is `unclassified`, retain the baseline slightly-cyclical curve and explicitly state that the selected discount-rate profile is unverified. The deterministic policy owns the risk-free rate, equity-risk premium, size adjustment, profile adjustments, and all sensitivity arithmetic. The classification selects a lens for discussion; it must not modify inputs or create a new valuation calculation.

`valuation_scenarios` must be empty and every scalar in `expected_return_components` must remain `null`. Do not calculate or state a forward fair value, target price, expected return, upside percentage, substitute P/E, EPS, or DCF value.

Deterministic implied expectations carry `source_id` values beginning with `valuation:reverse_dcf:`. Cite material reverse-DCF claims with those exact IDs. For other scalar deterministic metrics that do not carry a `source_id`, cite the exact supplied path beginning with `full_results.`; the execution boundary will normalize a resolvable path to a canonical `deterministic:` ID. Never invent or abbreviate a path.

Compare each implied expectation with company history and cited business evidence. State whether it appears undemanding, demanding, or cannot be judged, and identify the assumption or missing evidence that drives that conclusion. Reported FCF is diagnostic only because Börsdata includes aggregate investing cash flow. A 0% net-reinvestment input means positive ROIC was unavailable or baseline growth was non-positive; it does not mean the company requires no reinvestment.

Use supplied deterministic reverse-DCF output as authoritative arithmetic. You may critique assumptions and explain what the current price implies, but do not replace, silently modify, or independently invent calculated values. If deterministic output is unavailable, identify the required inputs rather than presenting model-generated arithmetic as authoritative.

Discuss revenue growth, margin change, balance-sheet change, and dilution qualitatively. Do not invent a numerical return decomposition.

## 6. Assess management

Evaluate founder or owner-operator alignment, ownership, capital allocation, cost consciousness, customer orientation, and execution. When historical statements are supplied, compare concrete claims with observed outcomes in a credibility ledger.

## 7. Assess ownership and timing

Analyze insider activity, ownership changes, average traded value, free float, listing venue, known supply overhangs, and plausible fund or index eligibility. Keep signal value separate from flow effects.

Use this evidence to modify confidence or timing. Do not allow it to replace the fundamental case.

Insider transactions are deliberately supplied as raw events with subsequent unadjusted price returns. Do not convert them into a mechanical score. Compare like-for-like transaction types, roles, sizes, repeated behavior, and the outcomes visible at the evidence cutoff. Do not treat missing future horizons as failed outcomes.

If `insider_event_count` is zero, make no inference from the absence of stored transactions. A company buyback is capital allocation, not an insider transaction, and cannot substitute for insider buying. A synthetic buyback must not be assumed to reduce share count or increase per-share value unless that effect is supplied by deterministic evidence.

## 8. Attempt to disprove the case

State the strongest contrary interpretation. Identify the evidence that would invalidate the revenue mechanism, peak margin, management assessment, financing assumptions, or valuation.

After sharp price moves, re-evaluate the evidence independently of the entry price and unrealized profit or loss.

## 9. Produce the verdict

Return the required structured result. Use decimal fractions for rates and returns, for example `0.15` for 15%. Use `null` for unavailable scalar values and list every material absence in `missing_information`.

Choose `reject`, `watch`, `latent_case`, or `activated_case`. Explain why the selected status is more appropriate than the next-more-positive status.
