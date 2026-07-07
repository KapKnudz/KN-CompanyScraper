-- migrate:up

-- =============================================
-- 1. Add new tables
-- =============================================

-- financials
CREATE TABLE public.financials (
    id integer NOT NULL,
    company_id integer NOT NULL,
    period_type character varying(20) NOT NULL,
    period_end date NOT NULL,
    revenue numeric(15, 2),
    ebit numeric(15, 2),
    net_income numeric(15, 2),
    ebit_margin numeric(5, 2),
    net_margin numeric(5, 2),
    debt numeric(15, 2),
    equity numeric(15, 2),
    cash numeric(15, 2),
    free_cash_flow numeric(15, 2),
    eps numeric(10, 2),
    dividend_per_share numeric(10, 2),
    shares_outstanding integer,
    created_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE public.financials_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.financials_id_seq OWNED BY public.financials.id;
ALTER TABLE ONLY public.financials ALTER COLUMN id SET DEFAULT nextval('public.financials_id_seq'::regclass);
ALTER TABLE ONLY public.financials ADD CONSTRAINT financials_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.financials ADD CONSTRAINT financials_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;
CREATE UNIQUE INDEX idx_financials_unique ON public.financials (company_id, period_type, period_end);

-- insider_transactions
CREATE TABLE public.insider_transactions (
    id integer NOT NULL,
    company_id integer NOT NULL,
    person_name character varying(255) NOT NULL,
    person_role character varying(100),
    transaction_type character varying(20) NOT NULL,
    shares integer NOT NULL,
    price_per_share numeric(10, 2),
    total_value numeric(15, 2),
    transaction_date date NOT NULL,
    reported_at timestamp with time zone DEFAULT now(),
    source character varying(255)
);

CREATE SEQUENCE public.insider_transactions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.insider_transactions_id_seq OWNED BY public.insider_transactions.id;
ALTER TABLE ONLY public.insider_transactions ALTER COLUMN id SET DEFAULT nextval('public.insider_transactions_id_seq'::regclass);
ALTER TABLE ONLY public.insider_transactions ADD CONSTRAINT insider_transactions_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.insider_transactions ADD CONSTRAINT insider_transactions_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;

-- annual_reports
CREATE TABLE public.annual_reports (
    id integer NOT NULL,
    company_id integer NOT NULL,
    year integer NOT NULL,
    report_url character varying(255) NOT NULL,
    report_text text,
    published_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE public.annual_reports_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.annual_reports_id_seq OWNED BY public.annual_reports.id;
ALTER TABLE ONLY public.annual_reports ALTER COLUMN id SET DEFAULT nextval('public.annual_reports_id_seq'::regclass);
ALTER TABLE ONLY public.annual_reports ADD CONSTRAINT annual_reports_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.annual_reports ADD CONSTRAINT annual_reports_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;
CREATE UNIQUE INDEX idx_annual_reports_unique ON public.annual_reports (company_id, year);

-- events
CREATE TABLE public.events (
    id integer NOT NULL,
    company_id integer NOT NULL,
    event_type character varying(50) NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    detected_at timestamp with time zone DEFAULT now(),
    source_type character varying(50),
    source_id integer,
    confidence numeric(3, 2) DEFAULT 1.0,
    metadata jsonb
);

CREATE SEQUENCE public.events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.events_id_seq OWNED BY public.events.id;
ALTER TABLE ONLY public.events ALTER COLUMN id SET DEFAULT nextval('public.events_id_seq'::regclass);
ALTER TABLE ONLY public.events ADD CONSTRAINT events_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.events ADD CONSTRAINT events_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;

-- valuations
CREATE TABLE public.valuations (
    id integer NOT NULL,
    company_id integer NOT NULL,
    valuation_type character varying(50) NOT NULL,
    intrinsic_value numeric(15, 2),
    bull_case numeric(15, 2),
    base_case numeric(15, 2),
    bear_case numeric(15, 2),
    fair_pe numeric(5, 2),
    expected_cagr numeric(5, 2),
    margin_of_safety numeric(5, 2),
    calculated_at timestamp with time zone DEFAULT now(),
    assumptions jsonb
);

CREATE SEQUENCE public.valuations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.valuations_id_seq OWNED BY public.valuations.id;
ALTER TABLE ONLY public.valuations ALTER COLUMN id SET DEFAULT nextval('public.valuations_id_seq'::regclass);
ALTER TABLE ONLY public.valuations ADD CONSTRAINT valuations_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.valuations ADD CONSTRAINT valuations_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;

-- analysis
CREATE TABLE public.analysis (
    id integer NOT NULL,
    company_id integer NOT NULL,
    analysis_type character varying(50) NOT NULL,
    content text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    created_by character varying(50),
    metadata jsonb
);

CREATE SEQUENCE public.analysis_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.analysis_id_seq OWNED BY public.analysis.id;
ALTER TABLE ONLY public.analysis ALTER COLUMN id SET DEFAULT nextval('public.analysis_id_seq'::regclass);
ALTER TABLE ONLY public.analysis ADD CONSTRAINT analysis_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.analysis ADD CONSTRAINT analysis_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;

-- jobs
CREATE TABLE public.jobs (
    id integer NOT NULL,
    job_type character varying(50) NOT NULL,
    status character varying(20) NOT NULL,
    company_id integer,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    result jsonb,
    error text
);

CREATE SEQUENCE public.jobs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.jobs_id_seq OWNED BY public.jobs.id;
ALTER TABLE ONLY public.jobs ALTER COLUMN id SET DEFAULT nextval('public.jobs_id_seq'::regclass);
ALTER TABLE ONLY public.jobs ADD CONSTRAINT jobs_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.jobs ADD CONSTRAINT jobs_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE SET NULL;

-- =============================================
-- 2. Modify existing tables
-- =============================================

-- companies
ALTER TABLE public.companies
ADD COLUMN isin character varying(12),
ADD COLUMN sector character varying(100),
ADD COLUMN industry character varying(100),
ADD COLUMN country character varying(50),
ADD COLUMN currency character varying(3) DEFAULT 'SEK';

-- news_releases
ALTER TABLE public.news_releases
ADD COLUMN published_at timestamp with time zone,
ADD COLUMN is_processed boolean DEFAULT FALSE;

-- scrape_runs
ALTER TABLE public.scrape_runs
ADD COLUMN job_type character varying(50);

-- company_profiles
ALTER TABLE public.company_profiles
ADD COLUMN website character varying(255),
ADD COLUMN founded_year integer,
ADD COLUMN employees integer,
ADD COLUMN headquarters character varying(255),
ADD COLUMN ceo character varying(255),
ADD COLUMN board_members text[];

-- watchlist
ALTER TABLE public.watchlist
ADD COLUMN user_id integer,
ADD COLUMN added_at timestamp with time zone DEFAULT now(),
ADD COLUMN notes text;

-- =============================================
-- 3. Add indexes for performance
-- =============================================

-- Companies
CREATE INDEX idx_companies_ticker ON public.companies (ticker);
CREATE INDEX idx_companies_isin ON public.companies (isin);
CREATE INDEX idx_companies_sector ON public.companies (sector);

-- News releases
CREATE INDEX idx_news_releases_company_id ON public.news_releases (company_id);
CREATE INDEX idx_news_releases_published_at ON public.news_releases (published_at);
CREATE INDEX idx_news_releases_is_processed ON public.news_releases (is_processed) WHERE is_processed = FALSE;

-- Scrape runs
CREATE INDEX idx_scrape_runs_status ON public.scrape_runs (status);
CREATE INDEX idx_scrape_runs_started_at ON public.scrape_runs (started_at);

-- Foreign key indexes (for new tables)
CREATE INDEX idx_financials_company_id ON public.financials (company_id);
CREATE INDEX idx_insider_transactions_company_id ON public.insider_transactions (company_id);
CREATE INDEX idx_annual_reports_company_id ON public.annual_reports (company_id);
CREATE INDEX idx_events_company_id ON public.events (company_id);
CREATE INDEX idx_valuations_company_id ON public.valuations (company_id);
CREATE INDEX idx_analysis_company_id ON public.analysis (company_id);
CREATE INDEX idx_jobs_company_id ON public.jobs (company_id);

-- Watchlist
CREATE INDEX idx_watchlist_user_id ON public.watchlist (user_id);

-- migrate:down

-- Drop indexes first to avoid dependency issues
DROP INDEX IF EXISTS idx_watchlist_user_id;
DROP INDEX IF EXISTS idx_jobs_company_id;
DROP INDEX IF EXISTS idx_analysis_company_id;
DROP INDEX IF EXISTS idx_valuations_company_id;
DROP INDEX IF EXISTS idx_events_company_id;
DROP INDEX IF EXISTS idx_annual_reports_company_id;
DROP INDEX IF EXISTS idx_insider_transactions_company_id;
DROP INDEX IF EXISTS idx_financials_company_id;
DROP INDEX IF EXISTS idx_scrape_runs_started_at;
DROP INDEX IF EXISTS idx_scrape_runs_status;
DROP INDEX IF EXISTS idx_news_releases_is_processed;
DROP INDEX IF EXISTS idx_news_releases_published_at;
DROP INDEX IF EXISTS idx_news_releases_company_id;
DROP INDEX IF EXISTS idx_companies_sector;
DROP INDEX IF EXISTS idx_companies_isin;
DROP INDEX IF EXISTS idx_companies_ticker;

-- Drop new columns from existing tables
ALTER TABLE public.watchlist
DROP COLUMN IF EXISTS user_id,
DROP COLUMN IF EXISTS added_at,
DROP COLUMN IF EXISTS notes;

ALTER TABLE public.company_profiles
DROP COLUMN IF EXISTS website,
DROP COLUMN IF EXISTS founded_year,
DROP COLUMN IF EXISTS employees,
DROP COLUMN IF EXISTS headquarters,
DROP COLUMN IF EXISTS ceo,
DROP COLUMN IF EXISTS board_members;

ALTER TABLE public.scrape_runs
DROP COLUMN IF EXISTS job_type;

ALTER TABLE public.news_releases
DROP COLUMN IF EXISTS published_at,
DROP COLUMN IF EXISTS is_processed;

ALTER TABLE public.companies
DROP COLUMN IF EXISTS isin,
DROP COLUMN IF EXISTS sector,
DROP COLUMN IF EXISTS industry,
DROP COLUMN IF EXISTS country,
DROP COLUMN IF EXISTS currency;

-- Drop new tables
DROP TABLE IF EXISTS public.jobs;
DROP TABLE IF EXISTS public.analysis;
DROP TABLE IF EXISTS public.valuations;
DROP TABLE IF EXISTS public.events;
DROP TABLE IF EXISTS public.annual_reports;
DROP TABLE IF EXISTS public.insider_transactions;
DROP TABLE IF EXISTS public.financials;