Produce only the forward-scenario assumptions for the completed qualitative
thesis supplied below. Return JSON matching the output contract exactly.

Use the deterministic readiness, financial-history summaries, current inputs,
and valuation anchors as the source of truth. Return exactly one bear, base,
and bull bundle for an eligible general company at the thesis horizon. Do not
calculate or state prices, holding values, annualized returns, probabilities,
or fair values. The local deterministic engine calculates those values.

Historical terminal multiples are anchors and optimistic ceilings, not a hard
downside floor. A bear multiple may be below historical p10. If historical
coverage is missing, use current EV/EBIT as the base anchor and do not assume
unsupported multiple expansion. The scenario packet and output contract are
provided as separate JSON fields alongside these instructions.

Every assumption `source_ids` value must be copied exactly from the packet's
top-level `source_ids` whitelist. Scenario provenance is strict: use no
deterministic paths, catalog aliases, field names, warnings, prose, or invented
IDs, even when they refer to supplied deterministic values.

The deterministic boundary applies these hard constraints. Return exactly one
bear, base, and bull bundle, and use the selected `case_horizon_months` for all
three bundles. Every numeric value must be finite; every assumption must have a
whitelisted source ID and a rationale; terminal multiple ranges must be
positive and ordered; EBIT margin must be positive; revenue CAGR and share-count
growth must be greater than -100%; distributions per share cannot be negative;
and non-zero share-count growth or distributions must have a mechanism.
The base annualized-return spread calculated by the local deterministic engine
must not exceed the maximum declared in `scenario_constraints`. Do not calculate
or reproduce that return spread yourself. If a repair packet supplies a
deterministic output diagnostic, change only sourced scenario assumptions to
resolve it while preserving the accepted qualitative thesis and horizon.

For `net_debt_change`, always include a mechanism. When its numeric `value` is
exactly zero, its `provenance_type` must be exactly `not_applicable`. A non-zero
value must use `source_backed` or `analyst_sensitivity`; never use
`not_applicable` for a non-zero change. Keep bear drivers no better than base
and bull drivers no worse than base. The base case may not exceed demonstrated
growth, margin, or supported multiple bounds; the bull case may exceed at most
one demonstrated growth, margin, or multiple bound, using the supplied 0.005
growth/margin validation tolerance. Preserve the qualitative thesis exactly.
