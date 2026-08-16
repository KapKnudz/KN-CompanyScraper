# Six-company classifier pilot — 2026-08-12

## Decision

Keep model-selected production profiles disabled.

The five classifier changes materially improved semantic behavior. The negative
controls, recurrence interpretation, separation of project dependence from
order phasing, and repeated profile direction all behaved as intended. The
pilot nevertheless fails formal validation because the model repeatedly emits
`low` commodity or financing assessments that the deterministic direct-evidence
checker rejects.

## Run setup

- Model: `deepseek/deepseek-v4-pro`
- Reasoning effort: high
- Companies: Lime Technologies, Clas Ohlson, Byggpartner, Scandic Hotels,
  BioGaia, and Norsk Titanium
- Three evidence-backed runs per company
- One evidence-withheld control per company
- Maximum 48 application-generated passages per company, round-robin selected
  across six dimensions

The initial 6,000-token run had 12 output-length failures. A targeted 10,000-token
rerun resolved most of them. A final 16,000-token batch for Scandic Hotels and
Norsk Titanium eliminated output-length failures entirely. The capacity-adjusted
assessment uses the latest complete three-run batch for each company and the
original six controls.

## Capacity-adjusted result

- Strict validation: **11/18 normal runs (61.1%)**
- Negative controls: **6/6 (100%)**
- Companies with at least two valid normal runs: **4/6**
- Pairwise profile agreement among valid comparable runs: **100%**
- Companies with three valid, unanimous profiles: **3/6**
- Normalization warnings on valid runs: **4**
- Output-length failures at the final selected capacities: **0**
- Remaining failures: **7**, all `low assessment lacks direct evidence`

| Company | Valid runs | Profiles | Assessment |
|---|---:|---|---|
| Lime Technologies | 3/3 | slightly / slightly / slightly | Stable; predominant recurrence plus moderate demand sensitivity |
| Clas Ohlson | 3/3 | slightly / slightly / slightly | Stable; moderate demand and input/freight exposure |
| Byggpartner | 3/3 | high-risk / high-risk / high-risk | Stable; high project dependence is the curve driver, not order phasing |
| Scandic Hotels | 0/3 | none accepted | All responses rejected on a claimed low financing assessment |
| BioGaia | 2/3 | unclassified / unclassified | Order phasing was high but correctly did not select a curve; one low-demand claim was rejected |
| Norsk Titanium | 0/3 | none accepted | All responses rejected on a claimed low commodity/financing assessment |

## What passed

All six evidence-withheld controls classified every dimension as unclassified,
cited no passages, and produced an unclassified profile.

Revenue recurrence used the new amount-based scale. Lime was `predominant` in
all three accepted runs. Byggpartner varied between `none_or_limited` and
`meaningful`, but recurrence did not override its consistently high project
dependence.

Project dependence and order phasing remained separate. Byggpartner's high-risk
profile was driven by project dependence. BioGaia's high order phasing produced
an unclassified profile rather than selecting a high-risk curve.

Every accepted non-unclassified dimension had passage evidence. Indirect low
signals were not accepted. The harmless response normalizations worked and were
recorded as warnings rather than invalidating otherwise usable responses.

## Remaining blocker

The low-evidence boundary is conservative but currently operates as a narrow
phrase whitelist over cited passage text. This caused whole responses to be
discarded even when their other dimensions were useful:

- Scandic cited net liabilities of 0.2x EBITDA as evidence of low financing
  exposure. The checker does not recognize that formulation.
- Norsk Titanium cited substantially lower raw-material and energy use as
  evidence of low commodity exposure. This is explicit process-efficiency
  evidence, but it does not necessarily establish low sensitivity to commodity
  prices at the company level.
- BioGaia made one unsupported low-demand claim, which was correctly rejected.

Scandic consistently found economic demand sensitivity (moderate, high,
moderate), and Norsk Titanium consistently found economic/project sensitivity,
but those signals were lost because one rejected low dimension invalidates the
entire response.

## Boundary change

Unsupported `low` dimensions now become `unclassified` with a warning while
independently valid dimensions are retained. The semantic direct-evidence
requirement remains unchanged; the phrase whitelist was not broadened merely to
make this sample pass. The post-pilot replay below measures the result.

Raw outputs:

- `cyclicality-evaluation-2026-08-12-improved.json` — initial 6,000-token run and controls
- `cyclicality-evaluation-2026-08-12-improved-10k-rerun.json` — targeted five-company retry
- `cyclicality-evaluation-2026-08-12-improved-16k-final.json` — final capacity check

## Post-pilot boundary replay

After changing unsupported `low` assessments to `unclassified` warnings instead
of rejecting the whole response, the saved responses were replayed locally with
no new model calls:

- Strict validation: **18/18 (100%)**
- Pairwise profile agreement: **77.8%**
- Three-run unanimous companies: **4/6**
- Lime, Clas Ohlson, Byggpartner, and BioGaia: **100% agreement**
- Scandic Hotels and Norsk Titanium: **33.3% pairwise agreement each**

This confirms that response validity is fixed but curve severity is not. Scandic
flips `slightly / high-risk / slightly`; Norsk Titanium flips `slightly /
high-risk / high-risk`. Both cases arise from `moderate` versus `high` judgments,
not passage grounding.

The recommended simpler production design is asymmetric:

1. Keep the slightly-cyclical curve as the default.
2. Let the classifier escalate only on explicit evidence of a *material* risk;
   use `material` or `unclassified`, not `low/moderate/high`.
3. Keep order phasing diagnostic-only.
4. Do not let the model select the lower noncyclical-recurring curve. That should
   require deterministic quantitative recurrence evidence plus an explicit
   policy decision.

This reduces the model's job from estimating an unstable severity scale to
answering whether supplied evidence crosses one conservative escalation threshold.
