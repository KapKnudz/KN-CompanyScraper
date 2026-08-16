# Incremental thesis-update workflow

Evaluate only how the supplied new evidence and current deterministic results affect the persisted thesis. The current thesis is the starting state, not a conclusion that must be defended.

1. Compare each new item with the current thesis, fact ledger, assumptions, triggers, and break conditions.
2. Preserve unchanged conclusions and ledger entries. The returned thesis and ledger must be complete, self-contained snapshots, not patches.
3. Add, amend, or remove a ledger item only when the new evidence supports the change. Retain original source IDs on carried-forward facts and use new source IDs for new observations.
4. Re-evaluate confidence using both old and new evidence. Do not increase confidence merely because a release repeats an existing claim.
5. Classify the net impact as `no_material_change`, `thesis_strengthened`, `thesis_weakened`, `activation_trigger_reached`, `thesis_break_triggered`, or `full_reassessment_required`.
6. Use `full_reassessment_required` for transformative acquisitions or disposals, accounting restatements, fundamental business-model changes, or evidence that makes the prior analytical frame invalid.
7. For `no_material_change`, return no changed sections and preserve the substantive thesis. For every other impact, identify each materially changed section.
8. Do not treat publication itself, management optimism, or a share-price move as confirmation. Cite every new or retained material fact with an allowed original source ID.

Research-evidence status fields are not under `full_results`. Cite only the exact supplied paths `research_evidence.insider_status` or `research_evidence.insider_event_count`; never prefix them with `full_results.`

Before selecting `no_material_change`, compare the current thesis's reverse-DCF assessment with the current deterministic reverse-DCF status. When the current status is unavailable, the updated thesis must use `unassessable`; changing from another assessment is a valuation-section change and cannot be labeled `no_material_change`. Do not populate an empty legacy fact ledger from thesis prose when no new textual evidence is supplied.

Return only the required JSON object.
