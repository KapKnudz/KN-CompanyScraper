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

For a `general` ranking model, populate `forward_scenario_assumptions` only when the supplied deterministic context includes positive current price, revenue, and shares, current net debt, and both EV/EBIT guardrails. Supply exactly eight complete endpoints at one shared 24-, 36-, or 48-month horizon: low/high endpoints for base, bull, multiple-compression bear, and fundamental-impairment bear. Every numeric assumption requires source IDs and a rationale. Express `share_count_growth` as a decimal fraction over the full horizon, for example `-0.0074` for a 0.74% reduction. The deterministic engine derives diluted shares from the supplied current share count; do not supply a second absolute share-count assumption. Net debt must likewise reconcile through `net_debt_change`. A multiple-compression endpoint copies its corresponding base operating and financing assumptions and changes only the terminal multiple. A fundamental-impairment endpoint improves no driver versus base and worsens at least one. Do not combine independent range extremes. Leave the list empty when evidence is insufficient or the ranking model is bank/property; the deterministic boundary will preserve a visible insufficiency or unsupported-method result.

`forward_scenario_analysis` must be `null` in the model response. The execution boundary owns its calculation. Never state a point estimate or probability weight in prose.

Use `full_results.reverse_dcf.price_fundamental_attribution` to explain material
one-, three-, and five-year share-price moves. Separate the portions accompanied
by revenue, EBIT, EPS, margin, and share-count change from changes in the
price/earnings multiple. A prior price increase is context, never proof of future
returns, but do not call a move speculative when supplied fundamentals explain it.

## 5. Interpret the reverse DCF

Use `full_results.reverse_dcf.expectation_curve` as the primary explanation of what the current price requires. Each point sets year-one revenue growth, which fades linearly to mature terminal growth by year five, and solves the year-five EBIT margin reached linearly from the current reported margin. Present the curve as alternative fading growth–margin paths rather than one unique market forecast. Never describe either endpoint as a constant five-year assumption. Use the one-variable results under `full_results.reverse_dcf.implied_expectations` only as cross-checks; when a solve is outside bounds, report its `required_value_hint` instead of treating the bound as the answer. Terminal growth is diagnostic only and must not drive the verdict or ranking interpretation. Check `full_results.reverse_dcf.normalization` before relying on any solve; when confidence is low, show both supplied three- and five-year windows and explain the exact reliability flags.

Do not independently classify cyclicality. When `full_results.cyclicality_consensus.status` is `complete`, copy its `risk_profile` exactly, set `risk_profile_confidence` to high for unanimous consensus or medium for majority consensus, and copy the consensus evidence source IDs into `risk_profile_evidence`. When consensus is absent or incomplete, output `unclassified`, low confidence, and no profile evidence. A completed consensus may select only a supplied deterministic profile; never alter its decision from your own reading of the evidence.

Use the consensus profile's curve under `full_results.reverse_dcf.discount_rate_sensitivities` when consensus is complete. Otherwise retain the baseline slightly-cyclical curve and explicitly state that the discount-rate profile is unverified. The deterministic policy owns the risk-free rate, equity-risk premium, size adjustment, profile adjustments, and all sensitivity arithmetic. Classification selects a supplied lens for discussion; it must not modify inputs or create a new valuation calculation.

The legacy model-authored `valuation_scenarios` field must remain empty and every scalar in `expected_return_components` must remain `null`. Do not independently calculate or state a forward fair value, target price, expected return, upside percentage, substitute P/E, EPS, or DCF value. Forward numeric output is valid only when supplied by the deterministic forward-scenario engine from stored sourced bundles; quote its ranges exactly and preserve all methodology and insufficient-evidence flags.

Deterministic implied expectations carry `source_id` values beginning with `valuation:reverse_dcf:`. Cite material reverse-DCF claims with those exact IDs. For other scalar deterministic metrics that do not carry a `source_id`, cite the exact supplied path beginning with `full_results.`; the execution boundary will normalize a resolvable path to a canonical `deterministic:` ID. Never invent or abbreviate a path.

Set `reverse_dcf_expectation_assessment` to `plausible`, `demanding`, `unsupported`, or `unassessable` and explain the conclusion in `reverse_dcf_expectation_rationale`. Reverse DCF produces no scalar score. These are qualitative evidence labels, never scores, probabilities, or generic valuation grades. Do not assign points or map the labels to numeric thresholds.

Ground the assessment in the company's own record under `full_results.reverse_dcf.operating_history` and cited prospective evidence. Compare required margins with its supplied three- and five-year averages, historical peak, and demonstrated operating leverage. Compare required revenue growth with its annual history, exact three- and five-year CAGRs when available, and cited addressable-market or industry growth evidence. Use `plausible` only when at least one relevant growth–margin combination fits defensible company-specific ranges; use `demanding` when the combinations require performance near historical peaks or materially ahead of supported market growth; and use `unsupported` only when the relevant combinations lack company or industry precedent and the proposed mechanism is speculative. Use `unassessable`, not `unsupported`, when the history, market-growth evidence, or normalization quality is insufficient. Never apply a universal growth or margin cutoff. Identify the exact comparison and missing evidence that drives the label.

Reported FCF is diagnostic only because Börsdata includes aggregate investing cash flow. A 0% net-reinvestment input means positive ROIC was unavailable or baseline growth was non-positive; it does not mean the company requires no reinvestment.

Use supplied deterministic reverse-DCF output as authoritative arithmetic. You may critique assumptions and explain what the current price implies, but do not replace, silently modify, or independently invent calculated values. If deterministic output is unavailable, identify the required inputs rather than presenting model-generated arithmetic as authoritative.

Discuss revenue growth, margin change, balance-sheet change, and dilution qualitatively. Do not invent a numerical return decomposition.

## 6. Assess management

Evaluate founder or owner-operator alignment, ownership, capital allocation, cost consciousness, customer orientation, and execution. When historical statements are supplied, compare concrete claims with observed outcomes in a credibility ledger.

## 7. Assess ownership and timing

Analyze insider activity, ownership changes, average traded value, free float, listing venue, known supply overhangs, and plausible fund or index eligibility. Keep signal value separate from flow effects.

Use this evidence to modify confidence or timing. Do not allow it to replace the fundamental case.

Populate `timing_assessment` with the fixed case horizon and observable catalyst
windows: `0_12m`, `12_24m`, `24_48m`, or `uncertain`. Every catalyst must say what
future evidence would confirm it and cite the evidence establishing why it is
expected. Do not invent a numeric confirmation threshold. Use a sourced threshold,
or state the observable direction relative to a cited current or historical baseline.
An assumption horizon alone is not a timing catalyst.

Insider transactions are deliberately supplied as raw events with subsequent unadjusted price returns. Do not convert them into a mechanical score. Compare like-for-like transaction types, roles, sizes, repeated behavior, and the outcomes visible at the evidence cutoff. Do not treat missing future horizons as failed outcomes.

If `insider_event_count` is zero, make no inference from the absence of stored transactions. A company buyback is capital allocation, not an insider transaction, and cannot substitute for insider buying. A synthetic buyback must not be assumed to reduce share count or increase per-share value unless that effect is supplied by deterministic evidence.

## 8. Attempt to disprove the case

State the strongest contrary interpretation. Identify the evidence that would invalidate the revenue mechanism, peak margin, management assessment, financing assumptions, or valuation.

After sharp price moves, re-evaluate the evidence independently of the entry price and unrealized profit or loss.

## 9. Produce the verdict

Return the required structured result. Use decimal fractions for rates, for example `0.15` for 15%. Use `null` for unavailable scalar values and list every material absence in `missing_information`.

Choose `reject`, `watch`, `latent_case`, or `activated_case`. Explain why the selected status is more appropriate than the next-more-positive status.

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
