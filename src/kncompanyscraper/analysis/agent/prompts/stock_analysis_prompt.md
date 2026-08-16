Analyze the company candidate below using the system policy and workflow.

Do not repeat the deterministic ranking as your conclusion. Reconcile conflicting evidence, distinguish facts from assumptions, and make missing information visible. Do not invent financial values or management history.
Every material factual claim derived from a textual document or insider transaction must have an entry in `citations` using the exact supplied `source_id`.
Build `company_fact_ledger` from short, atomic observations under the fixed headings. Distinguish facts, management claims, and analyst inferences. Every ledger item must cite at least one exact supplied source ID; leave a heading empty when it lacks support. Do not duplicate the same observation under several headings.

## Candidate evidence

```json
{candidate_json}
```

## Required output

Return only valid JSON matching this contract. Percentages and expected returns must be decimal fractions. Use `null` where a scalar value cannot be established.

```json
{output_contract}
```
