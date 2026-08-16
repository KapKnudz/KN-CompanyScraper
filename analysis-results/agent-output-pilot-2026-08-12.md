# Paid agent-output pilot — 2026-08-12

## Scope

- Provider: DeepSeek
- Model: `deepseek-v4-pro`
- Prompt policy reviewed: `nordic-case-investing-policy` v1.14.0
- Baseline: Clas Ohlson, deterministic rank 6
- Higher-risk case: Byggpartner, deterministic rank 10
- Evidence per company: four extracted report PDFs and eight recent company releases, plus deterministic financial, valuation, reverse-DCF, cyclicality-consensus, and insider inputs

## Results

| Company | Verdict | Confidence | Risk profile | Reverse-DCF assessment | Persistence |
|---|---|---|---|---|---|
| Clas Ohlson | reject | medium | slightly cyclical | unsupported | Rejected by the local boundary because aggregate operating history was missing from the citation whitelist |
| Byggpartner | watch | medium | cyclical or other material risk | demanding | Accepted as analysis ID 5 with no validation warnings |

Clas Ohlson was rejected because the current price implied margins above both
its operating history and management's approximately 12% target, or growth above
the bounded reverse-DCF range. Byggpartner remained a watch because its record
order backlog and possible segment-margin recovery provide a credible mechanism,
but the current price still requires margins near or above historical peaks or
sustained growth materially above its history.

The different verdicts are defensible. The model did not mechanically turn the
higher business-risk classification into the worse investment verdict. It kept
business risk, operating evidence, and price-implied expectations separate.

## Validation

- Both outputs used the persisted cyclicality consensus and the matching
  deterministic risk-adjusted reverse-DCF curve.
- Neither output created forward fair values, expected-return arithmetic, or a
  scalar reverse-DCF score.
- Both anchored revenue and margin claims to supplied operating history and
  company disclosures.
- Byggpartner cited the high-risk project dependence directly and surfaced
  backlog conversion, segment margins, dilution, CEO succession, and project
  execution as break conditions.
- Byggpartner passed `agent-boundary-v11` with zero warnings.

## Pilot incident and fix

The Clas Ohlson output cited the supplied aggregate source
`full_results.reverse_dcf.operating_history`. The boundary only whitelisted its
leaf values, so the otherwise valid response was not persisted. The boundary now
maps that aggregate source to
`deterministic:reverse_dcf:operating_history`, with a regression test.

The retained Clas Ohlson retry used 49,358 prompt tokens, 12,036 completion
tokens, and 61,394 total tokens; 49,280 prompt tokens were cache hits. The first
detached Clas Ohlson request may also have been billed, but its response metadata
was not retained. The accepted Byggpartner request used 56,115 prompt tokens,
13,070 completion tokens, and 69,185 total tokens.

## Decision

The pilot passes the qualitative behavior gate. The legacy scalar reverse-DCF
scorer and its ranking, CLI, serialization, and backtest plumbing were retired.
Reverse DCF remains available only as deterministic expectation curves and
qualitative agent evidence.
