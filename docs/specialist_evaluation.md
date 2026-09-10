# Specialist evaluation fixtures and comparison

The specialist path is non-authoritative. This evaluation reads frozen packets and
stored specialist artifacts; it does not run models or change production verdicts.

## Complete shadow run

For a frozen packet JSON document, the supported opt-in path runs the first-wave
specialists, uses validated forward-scenario results and the packet's deterministic reverse-DCF inputs,
runs sell conditions and deterministic conflicts, and then runs the Petter
aggregator. It persists raw specialist, raw aggregator, and validated aggregator
artifacts in the existing raw-analysis store, and writes a bundle made from those
stored records:

```sh
python -m kncompanyscraper.main run-shadow-analysis \
  --packets frozen-packets.json --scenario-results forward-scenario-results.json \
  --output shadow-artifacts.json \
  --allow-model-calls
```

`forward-scenario-results.json` is a JSON object keyed by company ID. Each value
is a validated `forward_scenario_analysis` object from the current deterministic
scenario policy; available results must contain the three bear/base/bull bands.

The command prints a bounded call plan before launching. Without
`--allow-model-calls` it performs no model execution. The bundle can be passed
directly to `evaluate-specialists` for both inputs; validated aggregator artifacts
are adapted at their artifact boundary into the case-level verdict metric and are
not mistaken for specialist outputs:

```sh
python -m kncompanyscraper.main evaluate-specialists \
  --cases cases.json --artifacts shadow-artifacts.json \
  --packets shadow-artifacts.json --output report.json
```

`--packets` may contain any number of packets, although the initial pilot is
exactly three.

## Case format

A labeled file is a JSON object with `schema_version: "specialist-evaluation-cases-v1"`
and a `cases` array. Each case has a stable `case_id`, `company_id`, `ticker`, and the
SHA-256 `packet_hash` of its frozen packet. `packet_ref` can identify a packet supplied
to the harness; a small packet may instead be embedded as `packet` for tests. Labels
are human-authored and are never inferred from an artifact:

- `claims`: expected `agent_name`/`claim_id`, with `expected_direction` and/or
  `expected_value`.
- `management_rows`: expected ledger result by `claim_id`.
- `conflicts.expected_triggered` and `expected_not_triggered`: the four named
  deterministic conflict rules.
- `final_verdict`: optional case-level verdict from an artifact whose metadata has
  `result_scope: "case"` and whose content is a validated
  `specialist-case-result-v1` object (or a validated aggregator candidate+manifest)
  bound to the case packet hash; otherwise use `"not_applicable"`.
- `source_validity`: `all_valid`, `invalid_present`, `unavailable`, or
  `not_applicable`.
- `activation`: human-labeled boolean or `not_applicable`; reports include full
  true/false positive and negative outcomes.
- `confidence`: an `agent_name` to expected low/medium/high mapping, or
  `not_applicable`.

Missing labels are reported as skipped or unavailable, never as passes. The fixture
`tests/fixtures/specialist_evaluation/cases.json` is deliberately synthetic and is
not the trusted 12–20 company benchmark.

## Run comparison

Artifacts are the existing raw specialist or packet-bound case-level records,
represented as a JSON array or `{"artifacts": [...]}`. Each record contains
`content` and stored metadata. Specialist records normally include `agent_name`,
`run_id`, `packet_hash`, `prompt_sha256`, usage, and attempts when available;
case-level records use the same packet and run metadata without requiring a
specialist agent name. Optional `model`, `tier`, `latency_ms`, `cost`, `repairs`,
and final verdict metadata are recorded when present; unavailable values remain
`null`.

```sh
python -m kncompanyscraper.main evaluate-specialists \
  --cases tests/fixtures/specialist_evaluation/cases.json \
  --artifacts path/to/artifacts.json \
  --packets path/to/frozen-packets.json \
  --output evaluation-report.json
```

The command prints concise metrics and optionally writes
`specialist-evaluation-report-v1` JSON. Metrics include parse/semantic rejection,
source-ID validity, claim and management-row agreement, conflict precision/recall,
final-verdict agreement, activation outcomes and false-positive rate, per-agent
confidence calibration, and availability of run metadata including run and agent
identity, packet hash, and prompt hash.

## Paired tier comparison

`compare_paired_specialist_evaluations` runs the best-tier and candidate-tier
artifact sets separately, then aligns their reports by case ID, frozen packet
hash, run ID, and specialist agent. Pass an explicit
`specialist-evaluation-manifest-v1` document through `manifest`; each assignment
maps a case, packet hash, run ID, and agent name to `best` or `candidate`. This
keeps tier ownership outside the production artifact contract. Missing or
conflicting assignments are rejected, while a declared assignment with no stored
artifact is reported as unavailable. Packet-bound case-level verdict artifacts
may be paired without specialist tier assignments. Its `metric_deltas` are
candidate minus best, while the nested reports preserve each run's metadata and
rejection accounting. Do not combine the two artifact arrays before calling the
paired entry point.

For the first real cohort, copy
`docs/specialist_evaluation_three_company_pilot.json`, select exactly three
companies, freeze one reviewed packet per company, and record each packet hash in
a new case. Have humans assign labels for claims, management rows, source
validity, conflict triggers, and any verdict/activation expectations; do not
invent labels or investment ground truth. Run the same frozen three-packet input once per model tier with distinct run
prefixes (for example `best` and `candidate`), then set `best_run_id` and
`candidate_run_id` after each tier run. The manifest is intentionally extensible
by adding companies later, but this pilot validator requires three.

Compare the two persisted bundles without copying or editing their artifacts:

```sh
python -m kncompanyscraper.main compare-shadow-evaluations \
  --cases cases.json --best-artifacts best.json \
  --candidate-artifacts candidate.json --packets frozen-packets.json \
  --pilot-manifest three-company-pilot.json --output paired-report.json
```

For a larger trusted cohort, freeze one reviewed packet per company and have two
humans label the claims, management rows, source validity, conflict triggers,
and any verdict/activation expectations.
Do not label from model output and do not invent investment ground truth. Store
best-tier and candidate-tier artifacts against the same packet hashes, with each
tier's selected run ID recorded in the manifest, then compare the paired reports
on a holdout cohort before changing routing.
Keep the synthetic fixture separate and do not treat it as benchmark evidence.
