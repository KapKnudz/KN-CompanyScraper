Update the persisted company thesis using the incremental workflow.

## Current thesis and provenance

```json
{current_thesis_json}
```

## Current structured fact ledger

```json
{current_facts_json}
```

## New evidence and current deterministic context

Only textual sources and insider events not present in the prior thesis are included. Deterministic results are current and may be unchanged.

```json
{candidate_json}
```

## Required output

Return only valid JSON matching this contract. The nested `thesis` must be the complete updated thesis and fact ledger, even when most fields are unchanged.

```json
{output_contract}
```
