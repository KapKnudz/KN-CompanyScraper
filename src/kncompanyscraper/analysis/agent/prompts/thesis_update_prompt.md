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

Only textual sources, insider events, and ownership/liquidity flow source IDs not present in the prior thesis are included. Deterministic results are current and may be unchanged. Keep insider transactions, executed company buybacks, short-interest snapshots, and long-holder ownership analytically distinct. Treat `_raw` flow fields as semantically unverified.

Keep `ownership_claims` synchronized with every material ownership/liquidity
assessment and cite the exact supplied source IDs. Do not retain a precise
ownership claim when its current deterministic field is null.

Re-evaluate the stored activation trigger directly. Add one
`activation_trigger_evidence` entry for each relevant new evidence item with
`confirms`, `weakens`, or `unresolved`; do not invent another reporting-period
wait. If the trigger is resolved, activate or revise the thesis and explain the
changed sections. Preserve explicit missing-information classes and impacts.
Re-test `falsifiable_case`, both decisive-evidence fields, and every structured
`thesis_break_tests` item against the new evidence. Preserve unchanged tests;
update their baselines or responses only when the supplied evidence supports
the change. When a break test fires, use `thesis_break_triggered` and identify
the affected section.

Valid trigger examples include: one announced customer replacement that
restores at least the quantified ARR loss; one report showing EBIT margin at or
above the stated range after the named cost action; or two reports maintaining
the range when one quarter cannot distinguish temporary acquisition-integration
benefits from durable margin performance. The last form must state that
persistence risk; do not write `better results`, `more evidence`, or `two strong
reports` as a trigger.

```json
{candidate_json}
```

## Required output

Return only valid JSON matching this contract. The nested `thesis` must be the complete updated qualitative thesis and fact ledger, even when most fields are unchanged. Do not author scenario bundles or calculated forward-scenario output; a separate required stage handles those after this response.

```json
{output_contract}
```
