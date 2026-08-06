-- migrate:up

CREATE TABLE public.stock_prices (
    company_id integer NOT NULL REFERENCES public.companies(id) ON DELETE CASCADE,
    price_date date NOT NULL,
    close numeric(18, 6) NOT NULL,
    currency character varying(3),
    fetched_at timestamp with time zone NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, price_date)
);

CREATE INDEX idx_stock_prices_company_id ON public.stock_prices (company_id);

-- migrate:down

DROP TABLE IF EXISTS public.stock_prices;
