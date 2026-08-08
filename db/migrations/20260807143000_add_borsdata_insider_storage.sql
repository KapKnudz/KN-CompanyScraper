-- migrate:up

ALTER TABLE public.insider_transactions
ALTER COLUMN shares TYPE bigint,
ADD COLUMN currency character varying(3);

CREATE UNIQUE INDEX idx_insider_transactions_borsdata_unique
ON public.insider_transactions (
    company_id,
    person_name,
    transaction_type,
    shares,
    price_per_share,
    transaction_date,
    reported_at
);

-- migrate:down

DROP INDEX IF EXISTS public.idx_insider_transactions_borsdata_unique;

ALTER TABLE public.insider_transactions
DROP COLUMN currency,
ALTER COLUMN shares TYPE integer;
