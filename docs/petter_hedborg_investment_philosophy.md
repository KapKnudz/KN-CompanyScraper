# Petter Hedborg's investment philosophy

## Purpose and interpretation

This document translates recurring ideas in eight podcast transcripts into a usable foundation for a stock-analysis agent. It is a synthesis, not a verbatim manifesto written by Hedborg.

Two layers are kept separate:

- **Source-backed philosophy** describes principles Hedborg repeatedly states or illustrates.
- **Agent implementation** turns those principles into explicit rules, calculations, and output fields. Exact scores and thresholds in this layer are design choices, not claims made by Hedborg.

Hedborg's strategy has changed as his portfolio has grown. His earlier approach combined a few long cases with shorter case trades in illiquid Nordic small caps. His newer approach is more long-term and constrained by liquidity. For an agent intended to find opportunities for a private investor, the most coherent target is the earlier/smaller-capital variant: maintain deep familiarity with roughly 50–100 Nordic small caps, then activate a concentrated 2–3 year case when a favorable setup appears. [S2][S6][S8]

## The philosophy in one paragraph

Stay within a narrow circle of competence, preferably Sweden and the Nordics, and know a manageable universe of companies unusually well. Normally require an already profitable business with a scalable and understandable model, entrepreneurial leadership, and evidence that management does what it says. The ideal case combines three return engines over roughly two to three years: organic revenue growth, operating-margin expansion toward a defensible peak margin, and a larger investor audience willing to pay a higher multiple. Model this simply rather than precisely. Fundamental performance is the main analysis; ownership, insider, liquidity, and fund-flow data are parallel tools for judging signal, timing, and possible multiple expansion. Define the thesis, horizon, expected events, valuation, and disconfirming evidence before investing. Cut a broken case, but let a fundamentally improving winner run. [S1][S3][S4][S6][S8]

## 1. Start with an investment case, not merely a good company

Hedborg distinguishes the company from the case. A wonderful company can lack an attractive case at today's price and over the chosen horizon; an ordinary company can temporarily offer an attractive case. The analysis must therefore answer both:

1. Is this a business worth understanding and possibly owning?
2. What specifically should change, by when, and how does that create a favorable return from today's price?

Every candidate must have an explicit horizon. A thesis about one quarterly report should not be defended with a three-year story after the event disappoints. Conversely, a genuine multi-year case should not be abandoned merely because of ordinary short-term volatility. [S1][S6][S8]

The agent should express the case in one falsifiable sentence:

> Over **[horizon]**, **[revenue driver]** should lift sales from **[A]** to **[B]**, while **[scale/economics]** moves EBIT margin from **[C]** toward **[D]**; at **[defensible multiple]**, this implies **[return]**, and the thesis fails if **[specific evidence]** occurs.

Avoid theses framed as “this should happen.” Hedborg explicitly contrasts what *ought* to happen with what is actually likely to happen. The agent must identify the mechanism and evidence that make the forecast probable.

## 2. Work within a narrow, local circle of competence

Hedborg invests almost exclusively in the Nordics, often Sweden. His advantage is not that national borders magically contain better companies; it is that local reporting, business culture, regulation, news flow, and access to management are easier for him to understand. He repeatedly argues that investors do not need to capture every good case and should restrict themselves to case types in which they can plausibly have an edge. [S2][S6]

Recommended working universe for this project:

- Swedish listed companies first; other Nordic companies second.
- Indicative market capitalization of SEK 300 million–10 billion, based on the user's target universe. This is a search boundary, not a Hedborg doctrine.
- Prefer less-followed companies where detailed work can matter.
- Treat liquidity as more important than market capitalization for tradability and institutional eligibility.
- Normally require positive operating profit or a demonstrated history of profitability.
- Exclude businesses whose result is dominated by a macro variable the agent cannot forecast with an edge, such as a commodity price, electricity price, interest rate, or broad construction cycle.
- Reject cases the agent cannot explain through the operating business. Do not force expertise in serial acquisition, complex roll-ups, or other models merely because others have succeeded with them.

Screening is a way to build a research queue, not a substitute for analysis. Hedborg often finds cases by reading reports, press releases, calls, and news flow; his “screen” is partly accumulated pattern recognition. [S2][S6]

## 3. Prefer profitable, scalable business models

The simplest risk-reduction rule Hedborg repeats is to invest only in profitable companies. He sometimes makes exceptions, but demands more knowledge, uses a shorter leash, and prefers a previously profitable company experiencing a temporary loss over a company that has never proven profitability. If the expected recovery does not appear in the next few quarters, he treats that as possible evidence of a structural defect. [S6][S8]

The agent should favor:

- An understandable path from product or service to profitable revenue.
- Organic growth that can persist without heroic capital requirements.
- High gross margin or otherwise demonstrable incremental economics.
- Fixed or semi-fixed operating costs that can decline as a share of revenue.
- Recurring revenue or recurring elements in a traditional business model, while recognizing that subscriptions can churn and that recurring declines can also persist.
- Products that are embedded, approved, or difficult to replace; examples include selected medtech and niche industrial models.
- Respect for customers and strong customer service. Hedborg regards disregard for customers as evidence of bad organizational DNA.

The agent should not infer scalability merely from an industry label such as SaaS. It must explain the sales channel, distributor economics, cost of goods, required operating expenses, capital intensity, and what additional revenue costs to deliver.

## 4. Seek the three-stage return engine

Hedborg's ideal 2–3 year case combines:

1. **Top-line growth:** the company sells more, preferably through credible organic drivers.
2. **Margin expansion:** EBIT margin moves from a depressed or immature level toward a defensible peak or steady-state margin.
3. **Multiple expansion:** improved size, quality, liquidity, investor relevance, or ownership flows make more investors willing or able to own the share.

The first two engines create earnings growth. The third can amplify the return, but is less controllable and should not rescue a weak fundamental case. Long-run share performance ultimately follows earnings per share; flow analysis primarily affects the multiple and timing. [S3][S4][S6]

The agent should decompose expected value explicitly:

```text
Revenue_t = Revenue_0 × (1 + growth)^t
EBIT_t = Revenue_t × EBIT_margin_t
Equity_value_t = EBIT_t × target_EV_EBIT - net_debt_t
Expected_return = Equity_value_t / current_equity_value - 1
```

Where the data supports it, also calculate per-share value to expose dilution.

The report must show how much expected return comes from:

- revenue growth;
- margin change;
- balance-sheet or share-count change; and
- multiple change.

A case that only works through multiple expansion should be flagged as fragile.

## 5. Gross-margin/EBIT-margin spread is a clue, not a conclusion

One of Hedborg's most repeated heuristics is to look for a high gross margin combined with a much lower EBIT margin. A company with, for example, a 65% gross margin and a 5–8% operating margin may have room for substantial operating leverage if operating costs do not need to rise proportionally with sales. [S1][S4][S6]

The key variable is not today's margin level but the gap between today's EBIT margin and a defensible peak margin:

```text
gross_to_ebit_spread = gross_margin - EBIT_margin
margin_runway = defensible_peak_EBIT_margin - current_EBIT_margin
```

Large spreads are candidates for investigation, not automatic buys. The agent must determine why the spread exists:

- Is the company deliberately investing through the income statement?
- Are sales and support costs fixed, semi-fixed, or permanently variable?
- Does it sell directly or through distributors?
- Is the addressable market large enough to absorb the required growth?
- Has the company or a close analogue previously demonstrated the proposed margin?
- Does ten years of stable 8–11% margins contradict an assumed jump to 20%?

That last question is essential. Hedborg warns against changing a spreadsheet cell from 10% to 20% when the organization's history and operating tempo do not support it. Peak margin must be inferred from business mechanics and company DNA, not selected to make valuation attractive. [S5]

## 6. Use a simple, scenario-based model

Hedborg consistently describes a deliberately simple spreadsheet: roughly two or three historical years and two or three forecast years, centered on revenue, gross margin, operating costs as a share of sales, EBIT, and valuation. Exact quarterly precision does not improve a multi-year decision; being in the right range matters more. [S1][S4][S6]

Minimum model:

- Revenue history and forecast.
- Organic growth where disclosed.
- Gross margin history and forecast.
- EBIT and EBIT margin history and forecast.
- Operating expenses as a share of revenue where useful.
- Net debt/cash and expected cash conversion.
- Share count and plausible dilution.
- Current and target EV/EBIT; optionally P/E or another model appropriate to the business.
- Historical five-year valuation range as one anchor, not an entitlement.
- Bear, base, and bull scenarios.

The target multiple should reflect the market regime pragmatically. A high-quality company may deserve tolerance if fundamentals are stronger than the original case, but the agent must still demand a margin of safety. Approximate assumptions are acceptable only when the idea remains attractive across a reasonable range.

## 7. Management and organizational DNA matter most in smaller companies

Hedborg strongly prefers entrepreneurial leadership: a founder-CEO, an owner-operator, a founding-team executive, or an active entrepreneurial chair. He calls exceptional examples “intelligent fanatics”—leaders driven by the mission and operating tempo, not only compensation. A professional manager with little ownership can succeed, but is less naturally investable for his style. [S2][S5][S6]

The agent must evaluate management using behavior rather than charisma:

- Founder/founding-team status and tenure.
- Direct and indirect share ownership, interpreted relative to compensation, wealth, and personal history.
- Capital allocation and cost consciousness.
- Organic growth record.
- Customer treatment.
- Operating tempo and evidence of execution.
- Promises, guidance, and qualitative statements compared with subsequent outcomes.
- Changes in wording and tone across CEO letters.
- Prior roles: what happened under the same executive elsewhere?

Build a **management credibility ledger** from at least 8–12 quarters where available:

| Date | Management claim | Expected timing | Observed outcome | Result |
|---|---|---|---|---|
| YYYY-Qn | Concrete statement | Quarter/year | Evidence | Kept / delayed / missed / unverifiable |

Do not reduce this to a naive promise-hit ratio. Distinguish external shocks, cautious communicators, chronic promotional language, changed assumptions, and statements too vague to test. The objective is pattern recognition: learn how this specific management team communicates and whether subtle changes have historically predicted results. [S2][S6]

For cases longer than one year, management interaction is especially valuable. Public presentations, capital-markets days, calls, interviews, and industry podcasts are valid evidence; private access is not required.

## 8. Treat ownership and flows as a parallel analytical layer

Hedborg explicitly rejects a contest between fundamental analysis and ownership/flow analysis. Fundamental analysis should consume most of the effort. Ownership and flows help answer two separate questions: [S3]

- **Signal value:** Does the presence or action of a particular insider or investor justify further research or alter conviction?
- **Flow effect:** Is a supply or demand imbalance likely to affect execution, timing, liquidity, or the valuation multiple?

### Fund investability

Market capitalization alone is insufficient. Across the interviews, Hedborg gives rough—not universal—examples in which fund relevance begins around SEK 1–3 billion and daily turnover reaches roughly SEK 1–5 million. In one more specific formulation, he describes the combination of approximately SEK 1–1.5 billion market value and at least SEK 1 million of daily turnover as interesting. These are time-, sector-, venue-, and fund-dependent observations, not hard rules. [S3][S6]

The agent should track:

- 20-, 60-, and 120-day average daily traded value.
- Market capitalization and free float.
- Listing venue and announced venue changes.
- Existing fund, family-office, retail, founder, and strategic ownership.
- Changes in ownership over the latest quarter and year.
- Known lockups, placements, forced sellers, and overhangs.
- Peer fund ownership and likely eligible specialist funds.
- Index eligibility and plausible passive demand.

A move from an MTF such as First North to a regulated main market can create passive demand. The transcripts use illustrative estimates of several percent of share capital in some cases; the agent must calculate this case by case and label it uncertain.

The desired setup is not simply “more funds.” It is a future demand shock without a matching supply shock. A low real free float can magnify the effect, while an exiting owner, expiring lockup, or changing shareholder base can suppress the price until supply is absorbed.

### Insider activity

Insider data must never be used as a mechanical buy/sell signal. Hedborg's framework is qualitative:

- A meaningful open-market purchase is generally positive, but verify that it is not a transfer, incentive program, gift, or effectively compelled “alibi” purchase.
- Several independent insiders buying can be a strong research trigger after program-related explanations are excluded.
- Interpret size relative to the person's pay, wealth, existing holding, company size, and earlier behavior. He offers roughly SEK 1 million as a level that may begin to attract attention for a CEO in a Swedish small cap, but rejects universal amount thresholds.
- Sales have many legitimate explanations. Compare the seller's historical pattern: repeated sales without subsequent deterioration may be routine diversification.
- A historically skilled seller or an unusual sale can still be a genuine warning.
- Clean and correctly classified data is more valuable than reacting fastest to raw filings.

Insider and owner actions should modify research priority, timing, or confidence. They should not override a weak business case. [S3][S8]

## 9. Maintain latent cases and wait for activation

Hedborg's speed comes from preparation, not instant analysis. He advocates following many companies closely enough that a new report, contract, price decline, management change, or ownership event can activate an already understood latent case. Without that baseline knowledge, the investor is as slow as everyone else. [S4][S6]

For each watchlist company, maintain:

- A stable business-model summary.
- Normal and peak-margin hypotheses.
- At least 8–12 quarters of financial and management history; use more where available.
- Historical valuation and price response to reports.
- Current owner structure and liquidity.
- A list of possible activation triggers.
- A “what would make this interesting?” price or event.

Common triggers include:

- Easy or misunderstood comparison periods.
- A major contract, approval, market entry, or product launch.
- Evidence that revenue growth is crossing fixed-cost scale.
- A temporary loss caused by timing rather than impaired economics.
- A new CEO with a relevant execution history.
- A listing change or rising liquidity that expands the eligible investor set.
- A known seller completing an exit.
- Independent insider purchases.
- A severe price decline while the long-term thesis remains intact.

The agent should compare current prices with closing prices before and after relevant events. Price reaction is evidence of market expectations, not evidence that the thesis is true.

## 10. Portfolio and risk rules

Hedborg's historical portfolio was highly concentrated, often around five holdings. He suggests 5–10 holdings as a workable concentrated range for a skilled, active private investor, while acknowledging that longer holding periods and larger capital may justify more diversification. [S4][S6][S8]

Source-backed principles:

- Never use portfolio leverage for stock picking.
- Do not initiate more than roughly 30% of portfolio cost in one holding; normal high-conviction initial weights were often materially lower.
- Allow a successful holding to become larger instead of mechanically trimming every winner.
- Accept cash when no qualifying case exists.
- Know concentrated holdings with an ambition approaching that of an operator.
- Cut positions when the thesis breaks; do not sell merely to crystallize a gain.
- A valuation materially above the justified range can be a sell reason, but valuation is a band rather than a one-krona tripwire.
- Use a shorter leash for currently loss-making companies.

Portfolio sizing should remain outside the first version of the analysis agent unless the agent has complete portfolio, liquidity, risk, and tax context. It can output a **conviction and liquidity classification**, but should not recommend a position percentage from company data alone.

## 11. Sell and invalidate explicitly

Every recommendation must include sell conditions at inception:

1. **Thesis break:** the causal mechanism fails, not merely the share price.
2. **Execution failure:** promised or required milestones repeatedly do not occur.
3. **Peak-margin invalidation:** unit economics, cost structure, or organizational history no longer supports the assumed margin.
4. **Balance-sheet/dilution break:** financing needs destroy per-share upside.
5. **Management break:** credibility, customer behavior, capital allocation, or ownership alignment deteriorates.
6. **Valuation overshoot:** price moves materially beyond a reasonable bull-case value without a corresponding improvement in fundamentals.
7. **Better evidence:** a new fact makes the original probability distribution wrong.

Do not use a stop-loss percentage as a substitute for analysis. Hedborg has sold individual cases at large losses; the relevant error is holding after the thesis has failed, not the fact that a price is below cost. At the same time, price can alter perception even for experienced investors, so the agent must re-run the evidence independently after sharp moves. [S6][S8]

## 12. Proposed agent decision process

### Stage A: hard gates

A candidate normally fails before scoring if:

- it is outside the selected home-market universe;
- the business model cannot be explained;
- it is unprofitable without a documented prior profit record and near-term recovery evidence;
- the result is dominated by an unforecastable macro variable;
- data is insufficient to form a falsifiable 2–3 year case; or
- expected return requires unsupported peak margins or multiple expansion.

Exceptions are allowed only when explicitly justified and tagged **rule exception**.

### Stage B: evidence score (agent design, not Hedborg's formula)

| Dimension | Weight | Core question |
|---|---:|---|
| Business model and scalability | 20 | Is profitable growth mechanically understandable? |
| Revenue growth evidence | 15 | Is there a credible, company-specific path to organic growth? |
| Margin-expansion evidence | 20 | Is peak margin defensible from economics and history? |
| Management and organizational DNA | 15 | Are leadership, ownership, communication, and execution aligned? |
| Valuation and margin of safety | 15 | Does the case work across reasonable assumptions? |
| Ownership, liquidity, and flows | 10 | Is there a favorable or improving supply/demand setup? |
| Evidence quality and falsifiability | 5 | Are claims sourced, testable, and contradicted where appropriate? |

Suggested interpretation:

- **80–100:** deep-dive/activation candidate, subject to human review.
- **65–79:** latent case; monitor explicit triggers.
- **50–64:** watch only; material evidence missing.
- **Below 50:** reject or archive.

No high total score may override a hard-gate failure without a visible exception. Report both the score and its uncertainty; missing data is not neutral evidence.

### Stage C: required output

1. One-sentence case and horizon.
2. Why now / activation trigger.
3. Business model and circle-of-competence assessment.
4. Historical and forecast table for revenue, gross margin, EBIT margin, EBIT, net debt, and share count.
5. Peak-margin bridge with operational justification.
6. Bear/base/bull valuation and return decomposition.
7. Management credibility ledger.
8. Ownership, insider, liquidity, and flow analysis.
9. Strongest confirming evidence.
10. Strongest disconfirming evidence.
11. Thesis-break and sell conditions.
12. Verdict: reject, watch, latent case, or activated case.
13. Confidence level and missing data.

## 13. Anti-patterns the agent must flag

- “Great company” with no price- and time-specific case.
- A thesis whose horizon changes after disappointing evidence.
- Peak margin selected by analogy without validating cost structure and company history.
- Revenue growth that depends mainly on acquisitions when acquisition skill is not analyzed.
- Multiple expansion treated as guaranteed.
- Market capitalization used as a proxy for fund eligibility without liquidity and free float.
- Insider purchases or famous investors copied without qualitative analysis.
- Management judged from a single interview rather than a record of claims and outcomes.
- Macro forecasts masquerading as company analysis.
- False precision in long-range spreadsheets.
- FOMO after price appreciation or refusal to sell because a loss is unrealized.
- Owning a company outside the agent's competence merely because another investor has an edge there.

## 14. Source map

The transcripts are machine-generated and can contain transcription errors. Source-backed claims above therefore rely on recurring ideas across episodes rather than isolated wording.

- **[S1]** *#115 Petter Hedborg – How To Excel In Investing, Scaling Modular Finance, And His Passion For Stocks And Sport Fishing* — <https://open.spotify.com/episode/02aaWKR0Ns1oviD10vtmbI>
- **[S2]** *116. Affärsmodeller, investeringar och framgångsrikt företagande med Petter Hedborg* — <https://open.spotify.com/episode/6fnnzf6kpcNMieneurnaCo>
- **[S3]** *#57 – Nästan allt du behöver veta om insynshandel med Modular Finance vd Petter Hedborg* — <https://open.spotify.com/episode/6p7g0nmDhsnbS4A68CANN8>
- **[S4]** *“Depån är inte pengar, det är poäng” – Petter Hedborg – Sparpodden 407* — <https://open.spotify.com/episode/1luLty202lKqYPUtb0l6Ov>
- **[S5]** *SpaceX IPO, och varför börsen behöver “intelligent fanatics” – med Petter Hedborg* — <https://open.spotify.com/episode/6GkfONNgJEWUW8MqfmKcPQ>
- **[S6]** *#69 Petter Hedborg: Case-trading och mönsterigenkänning* — <https://open.spotify.com/episode/1jJji64HY7t5FdCNl1Z7n8>
- **[S7]** *#1 Petter Hedborg* — <https://open.spotify.com/episode/1d7kzNWZAyEkphxohB5Qjb>
- **[S8]** *18. 150 000% på 20 år med Petter Hedborg* — <https://open.spotify.com/episode/6CGShTe3rcVFH9cTmjfwUW>

## Final design principle

The agent's edge should come from accumulated company-specific context, disciplined simplicity, and explicit falsifiability—not from producing more data. Its job is to know a limited universe well enough to recognize when a company-specific inflection, an attractive valuation, and a favorable ownership setup align.
