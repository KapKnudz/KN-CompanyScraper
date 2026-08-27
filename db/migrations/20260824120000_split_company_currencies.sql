-- migrate:up
ALTER TABLE public.companies
    ADD COLUMN IF NOT EXISTS stock_price_currency character varying(3),
    ADD COLUMN IF NOT EXISTS report_currency character varying(3);

UPDATE public.companies
SET stock_price_currency = COALESCE(stock_price_currency, currency),
    report_currency = COALESCE(report_currency, currency)
WHERE currency IS NOT NULL;

-- migrate:down
ALTER TABLE public.companies
    DROP COLUMN IF EXISTS stock_price_currency,
    DROP COLUMN IF EXISTS report_currency;
