-- migrate:up

ALTER TABLE public.financials
    ADD COLUMN gross_income numeric(15,2),
    ADD COLUMN operating_cash_flow numeric(15,2);

-- migrate:down

ALTER TABLE public.financials
    DROP COLUMN operating_cash_flow,
    DROP COLUMN gross_income;
