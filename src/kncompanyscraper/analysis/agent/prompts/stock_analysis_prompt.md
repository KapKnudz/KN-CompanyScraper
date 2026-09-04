Analyze the company candidate below using the system policy and workflow.

Do not repeat the deterministic ranking as your conclusion. Reconcile conflicting evidence, distinguish facts from assumptions, and make missing information visible. Do not invent financial values or management history.
Every material factual claim derived from a textual document or insider transaction must have an entry in `citations` using the exact supplied `source_id`. Keep source IDs in structured claims, ledger entries, assumptions, and citations; synthesize readable prose without printing source-ID lists or repeating methodology labels.
For each major narrative section, write one causal paragraph connecting the
observation to its implication, a counterpoint, and the limiting uncertainty;
keep those rhetorical parts in prose rather than adding schema fields.
Also populate `management_claims` and `insider_claims` for the corresponding
assessment sections. Each claim must be a short, atomic statement with an
`evidence_kind`, one or more exact supplied `source_ids`, and any relevant
`limitations`. Mark interpretations as `analyst_inference` and cite the facts
they rely on. A non-empty management or insider assessment must have matching
structured claims; do not rely on the global `citations` list alone.
Use only source IDs listed in `evidence_catalog` or exact supplied
`full_results.*` paths. Never turn reverse-DCF curve labels, sensitivity names,
or other descriptive packet keys into source IDs.
For the reverse-DCF expectation curve, cite
`deterministic:reverse_dcf:expectation_curve` or the exact supplied
`full_results.reverse_dcf.expectation_curve` path. Identifiers such as
`valuation:reverse_dcf:curve:+1000bp:ebit_margin` are invalid.
Preserve the complete namespace of peer IDs: target metrics use
`peer:target:...`, while comparable-company metrics use `peer:...`; do not
shorten a target ID such as `peer:target:financial:114:2025-12-31` to
`peer:financial:114:2025-12-31`.
For `management_credibility_ledger`, cite the original management statement in
`claim_source_ids` and cite the later report or release that supports an
observed outcome in `outcome_source_ids`. Keep `source_ids` as the union of
those lists. Use `result: unverifiable` with a null `observed_outcome` when a
claim is too recent or too vague to evaluate; do not treat a missing outcome
as a miss. Populate `management_credibility_coverage` from material,
testable claims in the supplied history: count evaluated claims, pending
claims, and eligible claims omitted from the ledger. Explain every omission
in `omission_reasons`; do not add repetitive entries to reach a target count.
When `omitted_claim_count` is zero, `omission_reasons` must be an empty list.
Pending or unverifiable claims are not omissions.
Build `company_fact_ledger` from short, atomic observations under the fixed headings. Distinguish facts, management claims, and analyst inferences. Every ledger item must cite at least one exact supplied source ID; leave a heading empty when it lacks support. Do not duplicate the same observation under several headings.
When `full_results.financial_history.half_year_comparison` is available, compare
the latest complete H1 with the same prior-year H1 and the supplied H1 history.
Use its exact fields and source IDs; do not reconstruct H1 by adding reports in
the narrative. If it is unavailable, disclose that limitation rather than
inferring a half-year trend from one quarter.
When `full_results.financial_history.scenario_history` is available, use its
deterministic summaries for scenario-relevant historical ranges, growth,
dilution, net-debt, dividend, and cash-flow observations. Do not recalculate
those summaries from the bounded detailed history; retain the supplied source
IDs and exclusions when describing limitations.
Use standardized financial history as the calculation source for H1 comparisons.
When report prose differs from standardized history, retain the standardized
value and describe the discrepancy, affected period, and both source IDs in a
limitation. Do not silently replace the canonical input.
Some supplied report documents may also contain an optional structured
`structured_financial_values` list in their evidence record. Compare those
values only when the metric and H1 period match; do not extract numbers from
free-form report text for this purpose.
When `full_results.peer_comparison.status` is `available`, use its dated peer
ranges as a separate sanity check. Compare the target's current metrics with
the peer ranges and compare, but do not replace, the target's company-history
terminal EV/EBIT guardrails. Cite the supplied peer metric source IDs or the
exact `full_results.peer_comparison` path. Do not invent peer explanations or
use peer ranges as a new valuation calculation. When peer coverage is
insufficient, state that limitation without weakening the core historical
valuation result.
Produce one `individual-thesis-card-v2`. Set `evidence_as_of` to the exact supplied research-evidence cutoff. Use `full_results.financial_history` for report-by-report comparisons and cite its supplied `financial:*` source IDs. Structure the business model consistently in `business_model_profile`; do not label recurring revenue, pricing power, capital intensity, operating leverage, or circle of competence more positively than the cited evidence supports. Keep unsupported dimensions `unassessable`.
Make `one_sentence_thesis` a single falsifiable case statement and repeat it
verbatim in `falsifiable_case.statement`. State the concrete observation that
would falsify it, use the same horizon as `case_horizon_months`, and cite the
evidence establishing the current baseline. Do not use a valuation target or a
generic phrase such as "results disappoint" as the falsification test.
Set `analysis_status` to `complete`. Evidence-blocked and method-unsupported candidates are handled before this prompt by the deterministic readiness gate. Deterministic valuation limitations may still be present: preserve unavailable reverse-DCF conclusions as `unassessable`. Forward scenarios are produced by a separate scenario-authoring stage after this response; do not provide calculated prices, returns, or fair values here. Do not use `watch` merely as a synonym for a missing valuation calculation; choose the verdict from the remaining business and operating evidence.
Define timing through observable catalysts rather than a vague near-term/long-term label. Every catalyst must state what would confirm it, use one fixed timing window, and cite supplied evidence. `timing_assessment.horizon_months` must match `case_horizon_months` when both are present.
Populate `revenue_resilience` with an evidence-backed assessment of contractual
or subscription stickiness versus message, transaction, usage, project, or
order volume. Discuss observed revenue, margin, or cash-flow variability when
supplied. Use `unassessable` and explain the limitation when evidence is thin;
do not infer cyclicality from order timing alone. Keep insider activity as a
directional signal separate from ownership-flow capacity. Free-float,
large-holder, and ownership-change conclusions are unavailable when those data
are not supplied. Keep insider transactions, executed company buybacks,
short-interest snapshots, and long-holder ownership distinct. Cite the exact
flow source IDs for any supplied flow assertion, and describe `_raw` fields
without adding percentage, currency, or trend interpretations.
Repeat every material liquidity, buyback, short-interest, or ownership
conclusion in `ownership_claims` using atomic statements and the exact supplied
ownership/liquidity source IDs. If the packet has no source IDs, leave the
claims empty and use the deterministic no-data wording.
Treat every packet subsection whose `status` is `empty` or `unknown` and whose
`source_ids` list is empty as a limitation only. It is not citable evidence:
do not turn its packet location into a `full_results.*` citation or use it to
support a factual claim.

For `missing_information`, provide one matching `missing_information_details`
entry per item. Use `core` only for an unresolved conclusion-determining input;
use `supplemental` for context that does not determine the fundamental case.
For a latent case, choose exactly one subtype and define one primary trigger in
`activation_trigger_spec`. The trigger must name the unresolved claim, an
observable company-specific metric or event, a threshold or direction, an
evidence window, and why one observation is or is not sufficient.
When a trigger combines a price observation with a later report, state that the
report rechecks the named operating baseline or persistence risk; do not leave
the reason for multiple observations implicit.

Select exactly one `strongest_confirming_evidence` item and one
`strongest_disconfirming_evidence` item when citable evidence exists. Each must
explain why that item is decision-relevant and cite exact supplied source IDs;
use `null` only when the corresponding side genuinely has no citable evidence.

Populate `thesis_break_tests` with one distinct test for each of the six fixed
types: `revenue_or_demand`, `margin_or_execution`,
`balance_sheet_or_dilution`, `management_credibility`,
`valuation_overshoot`, and `superior_evidence_or_opportunity`. Each test must
name an observable metric or event, a threshold or direction, the response
(`reassess`, `reduce`, or `sell`), and the source IDs establishing its current
baseline. These are future decision rules, not restatements of current risks.

For `revenue_resilience`, use `resilient` only for sourced retention, renewal,
contractual, or equivalent persistence evidence; use `mixed` only when both
recurring and variable drivers are material and supported; use `variable` for
primarily transaction, product, usage, project, or order revenue; and use
`unassessable` when the mechanism or persistence evidence is insufficient.
Populate `recurring_source_ids` and `variable_source_ids` separately. A
transaction-only or product-sales business with possible repeat demand is
`variable`, not `mixed`; a subscription label without sourced retention or
renewal evidence is not `resilient`. A licensing label can describe a one-time
right, delivery arrangement, royalty, or genuinely recurring contract; do not
treat licensing as recurring unless the supplied evidence establishes the
persistence mechanism.

## Candidate evidence

```json
{candidate_json}
```

## Required output

Return only valid JSON matching this contract. Percentages and expected returns must be decimal fractions. Use `null` where a scalar value cannot be established.

```json
{output_contract}
```
