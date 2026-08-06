# Stock-analysis workflow

Follow the steps in order. If a core step cannot be completed, preserve the missing information and lower confidence rather than filling gaps with assumptions.

## 1. Audit the supplied evidence

- Identify the reporting period and freshness of each metric.
- Separate raw values from derived scores and narrative flags.
- List missing data that could materially change the decision.
- Treat the existing ranking as a shortlist mechanism only.

## 2. Explain the business model

Describe the customer, problem, product or service, pricing, route to market, gross economics, operating-cost structure, reinvestment needs, and principal dependencies. State whether the business falls within the defined circle of competence.

## 3. Apply the profitability gate

Determine whether the company is currently profitable. If not, require an explicit rule exception, document prior profitability where available, identify the expected recovery period, and analyze liquidity, financing, and dilution risk.

## 4. Build the fundamental case

State the two-to-three-year revenue mechanism. Distinguish organic growth from acquisition-driven growth and price from volume where possible.

Estimate a defensible EBIT-margin path. If gross margin is available, investigate the gross-to-EBIT spread. Explain the operational change required for every material margin increase.

Do not use unsupported precision. Give ranges when the evidence only supports ranges.

## 5. Build valuation scenarios

Create bear, base, and bull scenarios using revenue, EBIT margin, net debt or cash, share count, and a defensible valuation multiple. Calculate or request calculation of implied per-share value and expected return.

Decompose the return into revenue growth, margin change, multiple change, balance-sheet change, and dilution. Flag dependence on multiple expansion.

## 6. Assess management

Evaluate founder or owner-operator alignment, ownership, capital allocation, cost consciousness, customer orientation, and execution. When historical statements are supplied, compare concrete claims with observed outcomes in a credibility ledger.

## 7. Assess ownership and timing

Analyze insider activity, ownership changes, average traded value, free float, listing venue, known supply overhangs, and plausible fund or index eligibility. Keep signal value separate from flow effects.

Use this evidence to modify confidence or timing. Do not allow it to replace the fundamental case.

## 8. Attempt to disprove the case

State the strongest contrary interpretation. Identify the evidence that would invalidate the revenue mechanism, peak margin, management assessment, financing assumptions, or valuation.

After sharp price moves, re-evaluate the evidence independently of the entry price and unrealized profit or loss.

## 9. Produce the verdict

Return the required structured result. Use decimal fractions for rates and returns, for example `0.15` for 15%. Use `null` for unavailable scalar values and list every material absence in `missing_information`.

Choose `reject`, `watch`, `latent_case`, or `activated_case`. Explain why the selected status is more appropriate than the next-more-positive status.
