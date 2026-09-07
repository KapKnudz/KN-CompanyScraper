# Deterministic/model contract remediation and controlled rollout plan

## Objective

Resolve the deterministic-validator and model-prompt mismatches exposed by the
latest company-analysis runs before spending more model calls. Then process the
newly ready companies in controlled, sequential runs, retry only the affected
failed companies as fresh jobs, and keep evidence- or method-blocked companies
out of the accepted cohort.

The required execution order is:

1. validator and prompt remediation;
2. a fresh deterministic readiness check;
3. controlled IVSO and RAY runs, one company at a time;
4. targeted fresh retries of the seven failed companies; and
5. the property/holding-company methodology workstream.

## Current rollout snapshot

This plan starts from the supplied 2026-09-04 operating snapshot:

- the evidence refresh changed readiness from 13 ready and 8 blocked to 17
  ready and 4 blocked;
- IVSO and RAY now have primary evidence;
- the latest accepted-card baseline is 7 of 22 complete;
- every one of those seven complete cards contains all six required thesis
  break-test types; and
- HEM, WPTG B, HUFV A, and CATE remain blocked.

These counts are baselines to reproduce, not constants to hard-code. The next
readiness and coverage exports become the authoritative dated artifacts.

## Fixed decisions and guardrails

### Ownership-source policy

Documentary statements are not an approved substitute for a licensed,
point-in-time ownership source. Therefore:

- `ownership_claims` may use only exact source IDs supplied by the dedicated
  ownership/liquidity evidence section;
- when no approved ownership source IDs exist, the model must leave
  `ownership_claims` empty and use the deterministic no-data wording;
- the model must omit holder, free-float, concentration, institutional,
  beneficial-owner, voting-control, ownership-change, and index assertions
  from ownership-specific conclusions when the corresponding approved data is
  absent;
- documentary evidence may still support non-ownership conclusions such as
  reported capital-allocation actions, but it must not be recast as holder or
  free-float data; and
- insider transactions, treasury shares, company buybacks, venue, and model
  prose must never be used as ownership proxies.

This keeps the prompt aligned with the current deterministic whitelist in
`AgentExecutionBoundary` and with the existing point-in-time source policy.

### Retry and audit policy

- A validation-exhausted job is immutable audit history.
- Do not resume, repair, overwrite, or revalidate an exhausted raw attempt to
  obtain a new thesis after a prompt-contract change.
- Preserve all existing job IDs, raw responses, validation errors, input
  hashes, and policy versions.
- A post-fix rerun must be a fresh `analyze-company` job with a fresh packet and
  current policy versions.
- Provider interruptions may still use the existing frozen-input resume path;
  deterministic validation exhaustion may not.
- Run exact companies sequentially so one failure cannot obscure another
  company's audit trail or spend.

### Blocked-company policy

- Keep HEM and WPTG B evidence-blocked until primary evidence is present.
- Keep HUFV A and CATE method-blocked until an approved property method is
  implemented and passes the readiness gate.
- Treat NAVIGO as part of the holding/property methodology workstream. Do not
  accept it under the general-company EV/EBIT method merely to clear readiness.
- Do not infer ownership, free float, holder, voting-control, or index data for
  any blocked or ready company.
- Exclude blocked companies explicitly from accepted-cohort coverage
  denominators; do not count them as failed or incomplete accepted cards.

## Failure matrix

| Family | Companies | Contract issue | Required outcome |
|---|---|---|---|
| Ownership claims | GULD, CLAS B, NELLY | The model can turn documentary ownership language into claims that the ownership-specific whitelist rejects. | Prompt and examples require omission when approved ownership IDs are absent; the validator continues to reject unsupported precision and source substitution. |
| Verdict triggers | BETS B, VUXEN, LIME | Price- or operating-latent prose does not reliably satisfy the structured activation-trigger contract and verdict-coherence checks. | Each latent verdict contains one dominant blocker and a complete, observable, validator-compatible trigger specification. |
| Revenue-model coherence | BYGGP, NAVIGO STAM | Hybrid or variable revenue descriptions can conflict with `revenue_model_types`, recurring profile, resilience assessment, and their cited evidence. | Hybrid classification names its component mechanics; mixed resilience includes distinct recurring and variable drivers with matching source IDs. |
| Holding/property methodology | NAVIGO, HUFV A, CATE | The general-company forward scenario is not an approved valuation method for holding/property economics. | Readiness remains blocked until a deterministic NAV/FFO or another explicitly approved method is implemented and tested. |

The seven fresh retry candidates are GULD, CLAS B, NELLY, BETS B, VUXEN,
LIME, and BYGGP. NAVIGO is intentionally excluded from that set until the
methodology decision is complete.

## Workstream 1 — Freeze the failures as targeted regressions

### Tasks

- [x] Record the existing failed job IDs, raw response IDs, failure stage,
  validation message, packet hash, prompt-contract version, and policy versions
  for all seven retry candidates.
- [x] Create minimal, private-text-free fixtures that reproduce each failure
  shape rather than copying entire live prompts or reports.
- [x] Add one characterization test per company-shaped failure before changing
  validator or prompt behavior.
- [x] Confirm that NAVIGO is classified as a methodology case and not included
  in the seven-job retry manifest.
- [x] Store a dated retry manifest that maps each fresh job to its preserved
  predecessor job for audit comparison without mutating the predecessor.

### Acceptance criteria

- Every proposed contract change is preceded by a failing focused test.
- The retry manifest contains exactly seven distinct active companies.
- Existing raw attempts are byte-for-byte untouched.
- No model call is made during this workstream.

## Workstream 2 — Ownership prompt/validator alignment

### Tasks

- [x] Update the qualitative prompt and analysis workflow to state that
  documentary ownership language is not eligible for `ownership_claims` when
  the dedicated ownership source whitelist is empty.
- [x] Require omission rather than a best-effort ownership summary for GULD-,
  CLAS B-, and NELLY-shaped packets with no approved ownership IDs.
- [x] Ensure the deterministic no-data assessment is the sole accepted
  ownership-specific conclusion in that state.
- [x] Keep document-backed capital-allocation and management facts available in
  their appropriate non-ownership sections.
- [x] Make repair feedback identify the exact offending claim and explain that
  changing a document citation into an ownership citation is not permitted.
- [x] Bump the qualitative prompt-contract or policy version because the
  model-facing source semantics change.

### Tests

- [x] A document mentioning a founder or shareholder does not authorize an
  `ownership_claims` entry when approved ownership IDs are absent.
- [x] Empty ownership evidence produces an empty claims list and deterministic
  no-data wording.
- [x] A valid claim using an exact supplied ownership/liquidity source ID still
  passes.
- [x] Free-float, holder, concentration, voting, ownership-change, and index
  precision remain rejected when their deterministic fields are null.
- [x] Insider events, buybacks, and liquidity sources cannot masquerade as
  long-holder ownership evidence.
- [x] GULD-, CLAS B-, and NELLY-shaped fixtures pass after unsupported claims
  are omitted.

### Acceptance criteria

- Prompt, workflow, schema examples, repair instructions, and execution
  boundary describe the same ownership-source policy.
- The validator is not weakened to accept unknown or semantically wrong source
  IDs.
- Existing valid ownership/liquidity tests remain green.

## Workstream 3 — Validator-compatible verdict triggers

### Trigger contract

A `latent_case` must have exactly one subtype and one primary trigger:

- `price`: the current price or valuation is the dominant blocker. The trigger
  names a concrete price or valuation condition tied to the deterministic
  valuation inputs, states the observation window, and does not add an
  unrelated operating hurdle.
- `operating`: an identified operating uncertainty is the dominant blocker.
  The trigger names a company-reported metric or event, a numeric threshold or
  direction relative to a cited baseline, the reporting window, whether one
  observation is sufficient, and why.

For both subtypes, all six fields in `activation_trigger_spec` must be present:
`unresolved_claim`, `observable_metric_or_event`, `threshold_or_direction`,
`evidence_window`, `single_observation_sufficient`, and
`observation_requirement`. The prose `activation_trigger` must express the same
condition rather than introduce a second blocker.

### Tasks

- [ ] Add prompt examples for one valid price trigger and one valid operating
  trigger using the exact structured field names.
- [ ] Add an explicit instruction to choose `watch` or `reject` when no single,
  evidence-backed latent trigger can be stated.
- [ ] Make validation errors field-specific and repairable: missing field,
  subtype mismatch, non-observable threshold, conflicting primary blockers, or
  verdict-coherence failure.
- [ ] Ensure price triggers refer to a concrete price/valuation condition and
  operating triggers refer to a named operating mechanism.
- [ ] Preserve the rule that the validator accepts or rejects but never
  upgrades a verdict.
- [ ] Bump the relevant prompt/verdict policy versions.

### Tests

- [ ] BETS B-shaped operating-latent output has one named operating mechanism
  and a complete trigger spec.
- [ ] VUXEN- and LIME-shaped price triggers identify a concrete valuation
  condition, evidence window, and observation requirement.
- [ ] Generic phrases such as "a lower price" or "better results" fail.
- [ ] A trigger combining price and operating confirmation without selecting a
  dominant blocker fails.
- [ ] Price-latent, operating-latent, watch, reject, and activated-case fixtures
  remain consistent with deterministic return and reverse-DCF gates.

### Acceptance criteria

- The three company-shaped regressions pass without weakening verdict
  coherence.
- A single validation error contains enough exact field context for the one
  permitted qualitative repair.
- Activated cases cannot retain unresolved triggers.

## Workstream 4 — Revenue-model and resilience coherence

### Classification rules

- `hybrid` means two or more economically material revenue mechanics. The
  profile must name those mechanics in `revenue_mechanics`; it must not use
  `hybrid` as a synonym for uncertainty.
- A business with both recurring and volume-, transaction-, project-, usage-,
  order-, or market-dependent revenue may be `mixed` only when both sides are
  described and separately sourced.
- `variable` is appropriate when variability dominates and no adequately
  evidenced recurring mechanism offsets it.
- `unassessable` is required when the packet cannot support the classification.
- Revenue-model type, recurring-revenue profile, resilience assessment,
  recurring driver, variable driver, and their source IDs must tell one
  consistent economic story.

### Tasks

- [ ] Add prompt definitions and short valid/invalid examples for hybrid,
  mixed, variable, and unassessable classifications.
- [ ] Extend validation messages to name the conflicting fields rather than
  returning only a broad resilience error.
- [ ] Add BYGGP-shaped coverage for project/product or other variable revenue
  with the correct resilience result.
- [ ] Add NAVIGO STAM-shaped coverage for a holding-company mix, but do not let
  revenue classification bypass its valuation-method gate.
- [ ] Keep source validation exact for overall, recurring, and variable
  evidence lists.

### Tests

- [ ] `hybrid` without at least two named material mechanics fails.
- [ ] `mixed` without both recurring and variable drivers and source IDs fails.
- [ ] A variable revenue model cannot claim majority recurring resilience
  without supporting evidence.
- [ ] BYGGP-shaped coherent output passes.
- [ ] NAVIGO STAM-shaped revenue classification can pass qualitative validation
  while final readiness remains methodology-blocked.

### Acceptance criteria

- Classification tests cover the allowed cross-product of revenue model,
  recurring profile, and resilience assessment without introducing
  company-specific validator exceptions.
- BYGGP is eligible for a fresh controlled retry after the focused suite passes.
- NAVIGO remains outside the retry cohort until an approved valuation method is
  available.

## Workstream 5 — Re-run deterministic readiness

### Tasks

- [ ] Refresh or rebuild candidates without invoking the model.
- [ ] Run `check-agent-readiness` across the full 21-company operating cohort,
  not only a truncated shortlist.
- [ ] Export a dated machine-readable readiness artifact with company ID,
  ticker, status, blocker codes, limitations, evidence cutoff, and method.
- [ ] Compare the result with the supplied 17-ready/4-blocked snapshot.
- [ ] Confirm IVSO and RAY have non-empty primary documentary evidence and no
  hard method blocker.
- [ ] Confirm HEM, WPTG B, HUFV A, and CATE remain explicitly blocked unless
  new approved evidence or methodology has actually changed their status.

### Acceptance criteria

- The readiness command makes zero model calls.
- Any difference from 17 ready and 4 blocked is explained by a dated evidence
  or methodology change before rollout continues.
- IVSO and RAY are individually `ready` at the same evidence cutoff used to
  build their fresh packets.
- The four blocked companies are excluded from the accepted-ready cohort.

## Workstream 6 — Controlled IVSO and RAY runs

Run IVSO first. Start RAY only after IVSO has passed every gate or has reached a
terminal, fully audited state.

### Per-company procedure

1. Resolve exactly one active company by ticker or company ID.
2. Refresh required upstream inputs and run the deterministic readiness gate.
3. Inspect the frozen packet measurements, primary-document list, source
   whitelist, prompt/policy versions, and packet hash.
4. Start one fresh `analyze-company` job.
5. Allow only the established qualitative attempt/repair and scenario
   attempt/repair ceilings.
6. Require deterministic validation, successful persistence, thesis revision,
   scenario audit, source audit, and job audit before marking the run accepted.
7. Run the thesis-contract coverage audit and verify all six break-test types
   for the accepted card.
8. Record job ID, analysis ID, thesis revision ID, evidence cutoff, hashes,
   model settings, call counts, timings, warnings, and final status.
9. If validation is exhausted, preserve the job and stop. Diagnose before any
   new fresh job; do not retry merely because the run failed.

### Acceptance criteria

- IVSO and RAY each have at most one newly accepted analysis from this rollout.
- No batch invocation contains both companies.
- Each accepted card passes deterministic validation and has all six complete,
  distinct thesis break-test types with source IDs.
- A failure in IVSO does not automatically authorize a RAY run or an IVSO
  retry; it first receives a recorded post-run diagnosis.

## Workstream 7 — Fresh retries of the seven failures

Proceed only after Workstreams 1–6 pass. Use this fixed order to isolate each
contract family:

1. GULD, CLAS B, NELLY — ownership omission policy;
2. BETS B, VUXEN, LIME — verdict-trigger contract; and
3. BYGGP — revenue-model coherence.

### Per-company gates

- [ ] The exact company-shaped regression is green before launch.
- [ ] Current deterministic readiness is `ready`.
- [ ] The job is fresh and links diagnostically to, but does not resume or
  mutate, the preserved failed attempt.
- [ ] The job uses the remediated prompt and policy versions.
- [ ] All raw model responses and validation outcomes are persisted.
- [ ] An accepted result passes the post-run source, scenario, verdict,
  ownership, revenue-coherence, and thesis-contract audits.
- [ ] The next company starts only after the current company has a terminal
  audit record.

### Acceptance criteria

- No retry is launched solely because its predecessor failed.
- Every new model call traces to a specific green regression and readiness
  result.
- Accepted retries contain no validator normalization that conceals a model
  contract violation.
- Failed fresh retries remain preserved and trigger a new diagnosis rather than
  an automatic loop.

## Workstream 8 — Property and holding-company methodology

This workstream follows the controlled operating-company batch. It must not be
implemented as a special-case prompt that leaves the deterministic engine on
the general EV/EBIT method.

### Method selection gate

Choose and document one approved deterministic method per economic structure:

- property companies: NAV discount/premium and FFO or another sourced,
  reproducible property method;
- holding companies: look-through NAV, holding-value, or another sourced,
  reproducible method that accounts for relevant liabilities and
  distributions; and
- hybrids: an explicit sum-of-parts or dominant-method rule with no double
  counting.

The method specification must define required inputs, source freshness,
currency handling, per-share reconciliation, debt treatment, distributions,
scenario assumptions, output bands, missing-input behavior, and readiness
blockers.

### Tasks

- [ ] Audit which required NAV, FFO, property income, share count, liabilities,
  distributions, and look-through holding values are already stored for
  NAVIGO, HUFV A, and CATE.
- [ ] Separate missing methodology from missing source data.
- [ ] Write the deterministic calculation and policy version before changing
  readiness support.
- [ ] Add unit tests for arithmetic, stale/missing inputs, currency mismatch,
  negative or nonsensical values, and per-share reconciliation.
- [ ] Add readiness tests proving unsupported or incomplete packets remain
  blocked without a model call.
- [ ] Add prompt/scenario support only after deterministic outputs and allowed
  source IDs exist.
- [ ] Run private-text-free NAVIGO-, HUFV A-, and CATE-shaped fixtures.
- [ ] Reassess live readiness; do not launch a model merely because the method
  code exists.

### Acceptance criteria

- Identical inputs reproduce identical outputs without a model call.
- No general-company EV/EBIT fallback silently substitutes for NAV/FFO or
  holding-company valuation.
- Missing required inputs yield typed blockers, not zero-filled values or model
  estimates.
- NAVIGO, HUFV A, or CATE becomes ready only when both the approved method and
  its required evidence are available.

## Verification sequence before any live model call

Run the smallest focused suites first, then the complete non-live suite:

1. prompt and workflow contract tests;
2. execution-boundary ownership, trigger, verdict, and revenue-coherence tests;
3. readiness and forward-scenario tests;
4. company-pipeline retry/resume/audit tests;
5. thesis-contract coverage tests; and
6. the complete non-live test suite with live integrations deselected.

The focused suite must prove both sides of every rule: the prior invalid shape
is rejected or omitted, and a valid sourced shape is still accepted. Test
failures must be fixed before readiness or live rollout begins.

## Baseline refresh and completion criteria

After IVSO/RAY and each accepted retry batch:

- export the latest validated thesis summaries;
- run `audit-thesis-contract-coverage`;
- retain the dated readiness, retry-manifest, job-audit, and coverage artifacts;
- report accepted-ready and blocked cohorts separately; and
- compare the new result with the 7/22 starting baseline.

The immediate target is 100% falsifiable-case and six-type break-test coverage
among the accepted ready cohort. Blocked companies are explicitly excluded from
that denominator and reported in a separate blocked table with their current
blocker codes. No target requires manufacturing analyses for blocked companies
or rewriting historical accepted cards.

This plan is complete when:

- all four failure families have focused regression coverage;
- IVSO and RAY have terminal audited outcomes from sequential fresh jobs;
- each of the seven failed companies has either one accepted fresh post-fix job
  or a documented new blocker/failure with no automatic retry;
- HEM, WPTG B, HUFV A, and CATE remain blocked until their stated gates are
  genuinely resolved;
- NAVIGO is handled only through an approved holding/property methodology; and
- the refreshed accepted-ready cohort has 100% complete falsifiable-case and
  six-type thesis-break-test coverage.
