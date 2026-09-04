-- migrate:up

ALTER TABLE public.financials
    ADD COLUMN IF NOT EXISTS investing_cash_flow numeric(15, 2),
    ADD COLUMN IF NOT EXISTS financing_cash_flow numeric(15, 2),
    ADD COLUMN IF NOT EXISTS report_date date,
    ADD COLUMN IF NOT EXISTS broken_fiscal_year boolean;

-- Promote values already retained in Börsdata payloads before new writes use
-- the typed columns.
UPDATE public.financials
SET cash = COALESCE(
        cash,
        NULLIF(raw_payload ->> 'cash_And_Equivalents', '')::numeric
    ),
    eps = COALESCE(
        eps,
        NULLIF(raw_payload ->> 'earnings_Per_Share', '')::numeric
    ),
    dividend_per_share = COALESCE(
        dividend_per_share,
        NULLIF(raw_payload ->> 'dividend', '')::numeric
    ),
    investing_cash_flow = COALESCE(
        investing_cash_flow,
        NULLIF(raw_payload ->> 'cash_Flow_From_Investing_Activities', '')::numeric
    ),
    financing_cash_flow = COALESCE(
        financing_cash_flow,
        NULLIF(raw_payload ->> 'cash_Flow_From_Financing_Activities', '')::numeric
    ),
    report_date = COALESCE(
        report_date,
        NULLIF(split_part(raw_payload ->> 'report_Date', 'T', 1), '')::date
    ),
    broken_fiscal_year = COALESCE(
        broken_fiscal_year,
        NULLIF(raw_payload ->> 'broken_Fiscal_Year', '')::boolean
    )
WHERE raw_payload IS NOT NULL;

-- migrate:down

ALTER TABLE public.financials
    DROP COLUMN IF EXISTS broken_fiscal_year,
    DROP COLUMN IF EXISTS report_date,
    DROP COLUMN IF EXISTS financing_cash_flow,
    DROP COLUMN IF EXISTS investing_cash_flow;
