-- migrate:up

-- Columns already used by ScrapeRunRepository but missing from migration history.
ALTER TABLE public.scrape_runs
ADD COLUMN IF NOT EXISTS error_message text,
ADD COLUMN IF NOT EXISTS companies_found integer DEFAULT 0,
ADD COLUMN IF NOT EXISTS news_added integer DEFAULT 0;

-- Store the complete set of report inputs used by the financial analysis while
-- retaining the original Börsdata payload for audit/debugging.
ALTER TABLE public.financials
ADD COLUMN IF NOT EXISTS operating_profit numeric(15, 2),
ADD COLUMN IF NOT EXISTS ebitda numeric(15, 2),
ADD COLUMN IF NOT EXISTS total_assets numeric(15, 2),
ADD COLUMN IF NOT EXISTS report_year integer,
ADD COLUMN IF NOT EXISTS report_period integer,
ADD COLUMN IF NOT EXISTS currency character varying(3),
ADD COLUMN IF NOT EXISTS raw_payload jsonb,
ADD COLUMN IF NOT EXISTS fetched_at timestamp with time zone DEFAULT now();

CREATE TABLE public.kpi_snapshots (
    company_id integer NOT NULL REFERENCES public.companies(id) ON DELETE CASCADE,
    kpi_id integer NOT NULL,
    value numeric,
    fetched_at timestamp with time zone NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, kpi_id)
);

CREATE TABLE public.kpi_history (
    company_id integer NOT NULL REFERENCES public.companies(id) ON DELETE CASCADE,
    kpi_id integer NOT NULL,
    period_type character varying(20) NOT NULL,
    price_type character varying(20) NOT NULL,
    year integer NOT NULL,
    value numeric NOT NULL,
    fetched_at timestamp with time zone NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, kpi_id, period_type, price_type, year)
);

CREATE INDEX idx_kpi_history_company_id ON public.kpi_history (company_id);

-- migrate:down

DROP TABLE IF EXISTS public.kpi_history;
DROP TABLE IF EXISTS public.kpi_snapshots;

ALTER TABLE public.financials
DROP COLUMN IF EXISTS fetched_at,
DROP COLUMN IF EXISTS raw_payload,
DROP COLUMN IF EXISTS currency,
DROP COLUMN IF EXISTS report_period,
DROP COLUMN IF EXISTS report_year,
DROP COLUMN IF EXISTS total_assets,
DROP COLUMN IF EXISTS ebitda,
DROP COLUMN IF EXISTS operating_profit;

ALTER TABLE public.scrape_runs
DROP COLUMN IF EXISTS news_added,
DROP COLUMN IF EXISTS companies_found,
DROP COLUMN IF EXISTS error_message;
