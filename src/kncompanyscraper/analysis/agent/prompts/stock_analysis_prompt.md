Analyze the company candidate below using the system policy and workflow.

Do not repeat the deterministic ranking as your conclusion. Reconcile conflicting evidence, distinguish facts from assumptions, and make missing information visible. Do not invent financial values or management history.
Every material factual claim derived from a textual document or insider transaction must have an entry in `citations` using the exact supplied `source_id`.
Build `company_fact_ledger` from short, atomic observations under the fixed headings. Distinguish facts, management claims, and analyst inferences. Every ledger item must cite at least one exact supplied source ID; leave a heading empty when it lacks support. Do not duplicate the same observation under several headings.
Produce one `individual-thesis-card-v1`. Set `evidence_as_of` to the exact supplied research-evidence cutoff. Use `full_results.financial_history` for report-by-report comparisons and cite its supplied `financial:*` source IDs. Structure the business model consistently in `business_model_profile`; do not label recurring revenue, pricing power, capital intensity, operating leverage, or circle of competence more positively than the cited evidence supports. Keep unsupported dimensions `unassessable`.
Set `analysis_status` to `complete`. Evidence-blocked, valuation-blocked, and method-unsupported candidates are handled before this prompt by the deterministic readiness gate; never encode those states as a `watch` verdict.
Define timing through observable catalysts rather than a vague near-term/long-term label. Every catalyst must state what would confirm it, use one fixed timing window, and cite supplied evidence. `timing_assessment.horizon_months` must match `case_horizon_months` when both are present.

## Candidate evidence

```json
{candidate_json}
```

## Required output

Return only valid JSON matching this contract. Percentages and expected returns must be decimal fractions. Use `null` where a scalar value cannot be established.

```json
{output_contract}
```
