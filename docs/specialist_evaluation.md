# Specialist evaluation fixtures and comparison

The specialist path is non-authoritative. This evaluation reads frozen packets and
stored specialist artifacts; it does not run models or change production verdicts.

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
  `specialist-case-result-v1` object bound to the case packet hash; otherwise use
  `"not_applicable"`.
- `source_validity`: `all_valid`, `invalid_present`, or `not_applicable`.
- `activation`: human-labeled boolean or `not_applicable`; reports include full
  true/false positive and negative outcomes.
- `confidence`: an `agent_name` to expected low/medium/high mapping, or
  `not_applicable`.

Missing labels are reported as skipped or unavailable, never as passes. The fixture
`tests/fixtures/specialist_evaluation/cases.json` is deliberately synthetic and is
not the trusted 12–20 company benchmark.

## Run comparison

Artifacts are the existing raw specialist records, represented as a JSON array or
`{"artifacts": [...]}`. Each record contains `content` and the stored `metadata`
(`agent_name`, `run_id`, `packet_hash`, `prompt_sha256`, usage, and attempts when
available). Optional `model`, `tier`, `latency_ms`, `cost`, `repairs`, and final
verdict metadata are recorded when present; unavailable values remain `null`.

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
hash, and specialist agent. Its `metric_deltas` are candidate minus best, while
the nested reports preserve each run's metadata and rejection accounting.
Do not combine the two artifact arrays before calling the paired entry point.

For the trusted 12–20 company cohort, freeze one reviewed packet per company,
record its hash in a new case, and have two humans label the claims, management
rows, source validity, conflict triggers, and any verdict/activation expectations.
Do not label from model output and do not invent investment ground truth. Store
best-tier and candidate-tier artifacts against the same packet hashes and run IDs,
then compare the paired reports on a holdout cohort before changing routing.
Keep the synthetic fixture separate and do not treat it as benchmark evidence.
