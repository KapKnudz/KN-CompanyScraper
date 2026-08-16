# Asymmetric cyclicality classifier pilot — 2026-08-12

## Decision

Classifier policy 2.1.0 is suitable for shadow-mode decision support, but not
yet for automatic valuation-curve selection. Keep model-selected production
profiles disabled.

The classifier now performs well as a conservative evidence assessor. It does
not meet the pre-agreed 90% repeated-run agreement threshold, and the six-company
sample is too small to establish out-of-sample reliability.

## Policy 2.1.0

- Revenue recurrence: `none_or_limited`, `meaningful`, `predominant`, or
  `unclassified`.
- Economic demand sensitivity, customer concentration, project dependence, and
  commodity/financing exposure: `material` or `unclassified`.
- Order phasing: `meaningful` or `unclassified`; diagnostic-only.
- Slightly cyclical is the deterministic baseline.
- Any passage-grounded material curve-risk dimension escalates to
  cyclical-or-other-risk.
- The classifier cannot select the favorable noncyclical-recurring curve.

Material requires realized significant revenue, profit, or cash-flow damage;
an explicit significant/material exposure; or a project-based business with
large projects relative to operations. Postponed decisions, generic risk-factor
language, ordinary business exposure, and isolated contracts without company
scale do not qualify.

## Final confirmation

The final result combines the policy-2.1.0 threshold check for Lime Technologies
and Norsk Titanium with the policy-2.1.0 confirmation for the other four
companies. The finalized policy also received six fresh evidence-withheld
controls.

- Evidence-backed validation: **18/18 (100%)**
- Evidence-withheld controls: **6/6 (100%)**
- Pairwise profile agreement: **16/18 pairs (88.9%)**
- Three-run unanimous companies: **5/6 (83.3%)**
- Output-length failures: **0** at a 16,000-token ceiling

| Company | Three profiles | Assessment |
|---|---|---|
| Lime Technologies | baseline / baseline / baseline | Predominant recurrence; sales-cycle timing is meaningful but not material demand damage |
| Clas Ohlson | baseline / baseline / baseline | Seasonality is diagnostic; no material curve-risk evidence |
| Byggpartner | high-risk / high-risk / high-risk | Material economic sensitivity and project dependence |
| Scandic Hotels | baseline / baseline / high-risk | Regional demand/profit impact remains borderline at company level |
| BioGaia | baseline / baseline / baseline | Meaningful order phasing correctly cannot escalate the curve |
| Norsk Titanium | baseline / baseline / baseline | Projects are identified, but company-relative materiality is unavailable |

## Assessment

The new asymmetric scale is materially simpler and more reliable than the old
low/moderate/high scale. It removed the recurring moderate-versus-high flips,
prevented mild sales-cycle evidence from over-escalating Lime, and prevented an
unscaled contract value from over-escalating Norsk Titanium.

Scandic exposes the remaining limitation: passages can describe a real regional
profitability impact without establishing its importance to the consolidated
company. Rewording the prompt further is unlikely to solve missing scale.

## Three-run lifetime consensus

Consensus policy 1.0.0 now turns the three independent assessments into one
auditable lifetime decision:

- Three valid runs are required; otherwise the decision is `incomplete`.
- High-risk requires `material` in the same curve-driving dimension in at least
  two runs.
- Different one-off material dimensions cannot be combined into an escalation.
- A non-unanimous decision is flagged for review.
- Supporting evidence is retained only from runs voting for the consensus
  escalation; all raw runs remain stored in the evaluation report.

Applied to the policy-2.1.0 confirmation:

| Company | Consensus | Strength | Review |
|---|---|---|---|
| Lime Technologies | baseline | unanimous | no |
| Clas Ohlson | baseline | unanimous | no |
| Byggpartner | high-risk, project dependence | unanimous | no |
| Scandic Hotels | baseline | 2–1 majority | yes |
| BioGaia | baseline | unanimous | no |
| Norsk Titanium | baseline | unanimous | no |

This consensus layer is appropriate for the intended low-frequency workflow,
where three calls are made once per stable company business model. A major
acquisition, divestment, or revenue-model change should invalidate the stored
classification.

## Deferred fallback architecture

Stop asking the model to make the final materiality decision. Use it only to
extract passage-grounded facts into a narrow schema:

- recurring revenue amount or percentage;
- realized revenue/profit/cash-flow impact and period;
- customer or project value/share and currency;
- explicit management description of sensitivity;
- financing leverage, interest exposure, or commodity exposure;
- order timing observations, retained as diagnostic-only.

Then choose the curve deterministically using:

1. a validated Börsdata branch/industry prior for clearly cyclical business
   models;
2. company-scale financial denominators from stored annual reports;
3. explicit numeric escalation thresholds; and
4. a baseline fallback whenever required scale is missing.

This is simpler to audit than another model severity label. It also makes clear
which missing datum prevented escalation. The favorable noncyclical-recurring
curve should remain separately gated by deterministic recurrence and resilience
evidence.

## Verification and artifacts

- Local tests: **372 passed**; the 10 live Börsdata tests were excluded.
- Initial asymmetric pilot: `cyclicality-evaluation-2026-08-12-asymmetric.json`
- Policy-2.1.0 Lime/NTI check:
  `cyclicality-evaluation-2026-08-12-asymmetric-threshold-check.json`
- Policy-2.1.0 four-company confirmation:
  `cyclicality-evaluation-2026-08-12-asymmetric-confirmation.json`
- Policy-2.1.0 controls:
  `cyclicality-evaluation-2026-08-12-asymmetric-controls.json`
