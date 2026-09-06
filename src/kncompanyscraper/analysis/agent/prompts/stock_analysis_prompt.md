Analyze the company candidate below using the system policy and workflow.

Do not repeat the deterministic ranking as your conclusion. Reconcile conflicting evidence, distinguish facts from assumptions, and make missing information visible. Do not invent financial values or management history.
Every material factual claim derived from a textual document or insider transaction must be represented in the relevant `structured_conclusions` claim or fact with the exact supplied `source_ids`. Use only the closed typed fields in that graph; readable prose is rendered deterministically after validation.
For each material conclusion, choose atomic typed claims and facts that connect
the observation to its implication, counterpoint, and limiting uncertainty.
Use the dedicated management, capital-allocation, evidence, and break-test
arrays rather than adding narrative or unstructured fields.
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
In `structured_conclusions.management_ledger`, use the closed management
fact codes and cite the supplied source IDs for each observation. Build
`company_facts` from closed capital-allocation fact codes and keep management
facts in `management_claims` or `management_ledger`; do not cross-route facts
between those sections. Every fact must cite at least one exact supplied
source ID; leave a section empty when it lacks support.
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
Produce one `individual-thesis-card-v3-structured-conclusions`. Set `evidence_as_of` to the exact supplied research-evidence cutoff. Use `full_results.financial_history` for report-by-report comparisons and cite its supplied `financial:*` source IDs. Put business-model, timing, margin, and resilience conclusions in their corresponding typed graph arrays; keep unsupported dimensions `unassessable`.
Use the typed `headline_case` and `falsifiable_case` components to define one
code-owned falsifiable case. State the concrete observation that would falsify
it, use the same horizon as `case_horizon_months`, and cite the evidence
establishing the current baseline. Do not use a valuation target or a generic
phrase such as "results disappoint" as the falsification test.
Set `analysis_status` to `complete`. Evidence-blocked and method-unsupported candidates are handled before this prompt by the deterministic readiness gate. Deterministic valuation limitations may still be present: preserve unavailable reverse-DCF conclusions as `unassessable`. Forward scenarios are produced by a separate scenario-authoring stage after this response; do not provide calculated prices, returns, or fair values here. Do not use `watch` merely as a synonym for a missing valuation calculation; choose the verdict from the remaining business and operating evidence.
Define timing through typed timing facts rather than a vague near-term/long-term label. Populate `revenue_resilience` with an evidence-backed assessment of contractual
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
`ownership_claims` is a closed typed union. Each item contains only
`claim_kind`, `subject_role`, `measure`, `binding`, and `limitation_codes`;
`binding` must use the exact canonical `deterministic_field`, packet value,
unit, and the exact `source_ids_by_measure` entry in
`research_evidence.ownership_liquidity`. It has no statement, destination, or
render-target field. Documentary founder/shareholder language is never an
ownership source. When that generated source map is empty, omit all ownership
claims and do not write a best-effort summary: the boundary supplies exactly
`Ownership and liquidity evidence are unavailable. No inference can be made
from their absence.` in the ownership projection. Changing a documentary
citation into an ownership citation is not permitted.
Treat every packet subsection whose `status` is `empty` or `unknown` and whose
`source_ids` list is empty as a limitation only. It is not citable evidence:
do not turn its packet location into a `full_results.*` citation or use it to
support a factual claim.

For `structured_conclusions.missing_information_details`, provide one typed
entry per missing input. Use `core` only for an unresolved
conclusion-determining input; use `supplemental` for context that does not
determine the fundamental case.
For a latent case, choose exactly one subtype and define one primary typed
`trigger`. The closed trigger codes must name the unresolved claim, an
observable company metric or event, a threshold or direction, an evidence
window, and why one observation is or is not sufficient.
When a trigger combines a price observation with a later report, state that the
report rechecks the named operating baseline or persistence risk; do not leave
the reason for multiple observations implicit.

Select exactly one typed `strongest_confirming_evidence` item and one typed
`strongest_disconfirming_evidence` item when citable evidence exists. Each
must select a claim, use a closed relevance code, and cite exact supplied
source IDs; use `null` only when the corresponding side genuinely has no
citable evidence.

Populate typed `thesis_break_tests` with one distinct test for each of the six fixed
types: `revenue_or_demand`, `margin_or_execution`,
`balance_sheet_or_dilution`, `management_credibility`,
`valuation_overshoot`, and `superior_evidence_or_opportunity`. Use only the
closed condition, metric, threshold, and response codes; cite the source IDs
establishing each current baseline. These are future decision rules, not
restatements of current risks.

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
