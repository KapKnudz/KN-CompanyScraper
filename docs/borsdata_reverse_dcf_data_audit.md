# Börsdata data audit for reverse DCF

Audit date: 2026-08-11

## Sources inspected

- Local `borsdata-swagger.json` report, report-metadata, KPI-metadata, and KPI-history schemas.
- Live `/v1/instruments/reports/metadata` response: 37 report fields.
- Live `/v1/instruments/kpis/metadata` response: 234 KPI-history fields.
- Stored annual reports and live KPI histories for Betsson, Better Collective,
  Surgical Science, and White Pearl Technology.
- The prior 111-company portfolio snapshot: 552 usable annual company-years.

## What the report API provides

`ReportV1` provides:

- `cash_Flow_From_Operating_Activities`;
- `cash_Flow_From_Investing_Activities`;
- `cash_Flow_From_Financing_Activities`;
- `cash_Flow_For_The_Year`; and
- `free_Cash_Flow`.

It does not provide separate capex, acquisitions, disposals, depreciation,
amortization, or changes in working capital.

Across all 552 inspected stored annual observations:

`free_Cash_Flow ≈ operating cash flow + investing cash flow`

Every observation matched within 0.1%. Reported FCF therefore includes the full
investing section, not just recurring capital expenditure.

## Relevant KPI-history fields

| KPI | Metadata label | Finding |
|---:|---|---|
| 25 | Capex % | Calculated ratio; does not separate acquisition spending |
| 62 | Operating Cash Flow | Same operating-flow concept as reports |
| 63 | Free Cash Flow | Same aggregate FCF concept as reports |
| 64 | Capex | Sampled values equal aggregate investing cash flow |
| 93 | Workingcapital-% | Balance-sheet ratio, not annual change in working capital |
| 178 | Cash Flow Stability | Opaque calculated score, not auditable cash-flow components |

For every sampled year with KPI data, `KPI 63 = KPI 62 + KPI 64` within rounding.
Acquisition-heavy Better Collective years and Surgical Science's 2021 investing
outflow are included in KPI 64. The label `Capex` is therefore not sufficient
evidence that the series represents recurring capex.

## Modeling consequence

A clean FCFF bridge—`NOPAT + D&A − capex − Δworking capital`—cannot be built from
the Börsdata API alone. Treating report FCF or KPI 64 as recurring reinvestment
creates false precision and severe acquisition-cycle distortion.

Policy v7 therefore:

- uses normalized EBIT, growth, and ROIC to estimate reinvestment;
- retains reported FCF, operating cash flow, and aggregate investing cash flow
  only as confidence diagnostics;
- exposes both three- and five-year windows;
- lowers interpretation confidence for unstable or incomplete histories; and
- keeps the limitation visible to the analysis agent.

## What would improve the model further

Clean recurring FCFF requires another source with cash-flow statement line items
or company-report extraction for maintenance/growth capex, acquisitions,
disposals, D&A, and working-capital changes. Until then, those components must not
be inferred from Börsdata's aggregate investing series.
