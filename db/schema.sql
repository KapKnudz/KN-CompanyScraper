\restrict dbmate

-- Dumped from database version 18.4
-- Dumped by pg_dump version 18.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: scrape_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.scrape_status AS ENUM (
    'running',
    'success',
    'failed',
    'partial'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: analysis; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analysis (
    id integer NOT NULL,
    company_id integer NOT NULL,
    analysis_type character varying(50) NOT NULL,
    content text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    created_by character varying(50),
    metadata jsonb
);


--
-- Name: analysis_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.analysis_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: analysis_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.analysis_id_seq OWNED BY public.analysis.id;


--
-- Name: annual_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.annual_reports (
    id integer NOT NULL,
    company_id integer NOT NULL,
    year integer NOT NULL,
    report_url character varying(255) NOT NULL,
    report_text text,
    published_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: annual_reports_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.annual_reports_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: annual_reports_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.annual_reports_id_seq OWNED BY public.annual_reports.id;


--
-- Name: companies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.companies (
    id integer NOT NULL,
    name text NOT NULL,
    ticker character varying(20),
    borsdata_id integer,
    last_updated timestamp with time zone DEFAULT now(),
    mfn_slug text,
    isin character varying(12),
    sector character varying(100),
    industry character varying(100),
    country character varying(50),
    currency character varying(3) DEFAULT 'SEK'::character varying,
    sector_id integer,
    branch_id integer
);


--
-- Name: companies_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.companies_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: companies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.companies_id_seq OWNED BY public.companies.id;


--
-- Name: company_cyclicality_consensus; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.company_cyclicality_consensus (
    company_id integer NOT NULL,
    classifier_policy_version text CONSTRAINT company_cyclicality_consensu_classifier_policy_version_not_null NOT NULL,
    consensus_policy_version text NOT NULL,
    consensus jsonb NOT NULL,
    classified_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: company_facts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.company_facts (
    id bigint NOT NULL,
    company_id integer NOT NULL,
    thesis_revision_id bigint NOT NULL,
    heading text NOT NULL,
    statement text NOT NULL,
    evidence_kind text NOT NULL,
    source_ids text[] NOT NULL,
    source_date date,
    reporting_period text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT company_facts_evidence_kind_check CHECK ((evidence_kind = ANY (ARRAY['fact'::text, 'management_claim'::text, 'analyst_inference'::text]))),
    CONSTRAINT company_facts_heading_check CHECK ((heading = ANY (ARRAY['business_model'::text, 'revenue_drivers'::text, 'margins_and_operating_leverage'::text, 'balance_sheet_and_capital_allocation'::text, 'management_and_execution'::text, 'ownership_and_insiders'::text, 'valuation_expectations'::text, 'risks_and_disconfirming_evidence'::text]))),
    CONSTRAINT company_facts_source_ids_check CHECK ((cardinality(source_ids) > 0)),
    CONSTRAINT company_facts_statement_check CHECK ((length(TRIM(BOTH FROM statement)) > 0))
);


--
-- Name: company_facts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.company_facts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: company_facts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.company_facts_id_seq OWNED BY public.company_facts.id;


--
-- Name: company_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.company_profiles (
    company_id integer NOT NULL,
    description text,
    business_model text,
    competitive_advantages text,
    management jsonb,
    updated_at timestamp with time zone DEFAULT now(),
    website character varying(255),
    founded_year integer,
    employees integer,
    headquarters character varying(255),
    ceo character varying(255),
    board_members text[]
);


--
-- Name: company_thesis_revisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.company_thesis_revisions (
    id bigint NOT NULL,
    company_id integer NOT NULL,
    revision integer NOT NULL,
    previous_revision_id bigint,
    source_analysis_id integer NOT NULL,
    change_type text NOT NULL,
    evidence_as_of date,
    confidence text NOT NULL,
    confidence_limitations text[] DEFAULT '{}'::text[] NOT NULL,
    content jsonb NOT NULL,
    created_by text NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT company_thesis_revisions_change_type_check CHECK ((change_type = ANY (ARRAY['initial'::text, 'full_reassessment'::text, 'incremental_update'::text]))),
    CONSTRAINT company_thesis_revisions_confidence_check CHECK ((confidence = ANY (ARRAY['low'::text, 'medium'::text, 'high'::text]))),
    CONSTRAINT company_thesis_revisions_revision_check CHECK ((revision > 0))
);


--
-- Name: company_thesis_revisions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.company_thesis_revisions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: company_thesis_revisions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.company_thesis_revisions_id_seq OWNED BY public.company_thesis_revisions.id;


--
-- Name: events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.events (
    id integer NOT NULL,
    company_id integer NOT NULL,
    event_type character varying(50) NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    detected_at timestamp with time zone DEFAULT now(),
    source_type character varying(50),
    source_id integer,
    confidence numeric(3,2) DEFAULT 1.0,
    metadata jsonb
);


--
-- Name: events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.events_id_seq OWNED BY public.events.id;


--
-- Name: financials; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.financials (
    id integer NOT NULL,
    company_id integer NOT NULL,
    period_type character varying(20) NOT NULL,
    period_end date NOT NULL,
    revenue numeric(15,2),
    ebit numeric(15,2),
    net_income numeric(15,2),
    ebit_margin numeric(5,2),
    net_margin numeric(5,2),
    debt numeric(15,2),
    equity numeric(15,2),
    cash numeric(15,2),
    free_cash_flow numeric(15,2),
    eps numeric(10,2),
    dividend_per_share numeric(10,2),
    shares_outstanding integer,
    created_at timestamp with time zone DEFAULT now(),
    operating_profit numeric(15,2),
    ebitda numeric(15,2),
    total_assets numeric(15,2),
    report_year integer,
    report_period integer,
    currency character varying(3),
    raw_payload jsonb,
    fetched_at timestamp with time zone DEFAULT now(),
    gross_income numeric(15,2),
    operating_cash_flow numeric(15,2)
);


--
-- Name: financials_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.financials_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: financials_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.financials_id_seq OWNED BY public.financials.id;


--
-- Name: insider_transactions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.insider_transactions (
    id integer NOT NULL,
    company_id integer NOT NULL,
    person_name character varying(255) NOT NULL,
    person_role character varying(100),
    transaction_type character varying(20) NOT NULL,
    shares bigint NOT NULL,
    price_per_share numeric(10,2),
    total_value numeric(15,2),
    transaction_date date NOT NULL,
    reported_at timestamp with time zone DEFAULT now(),
    source character varying(255),
    currency character varying(3)
);


--
-- Name: insider_transactions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.insider_transactions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: insider_transactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.insider_transactions_id_seq OWNED BY public.insider_transactions.id;


--
-- Name: jobs; Type: TABLE; Schema: public; Owner: -
--

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


--
-- Name: jobs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.jobs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: jobs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.jobs_id_seq OWNED BY public.jobs.id;


--
-- Name: kpi_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kpi_history (
    company_id integer NOT NULL,
    kpi_id integer NOT NULL,
    period_type character varying(20) NOT NULL,
    price_type character varying(20) NOT NULL,
    year integer NOT NULL,
    value numeric NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL,
    report_period integer
);


--
-- Name: kpi_snapshot_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kpi_snapshot_history (
    company_id integer NOT NULL,
    kpi_id integer NOT NULL,
    observation_date date DEFAULT CURRENT_DATE NOT NULL,
    value numeric,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: kpi_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kpi_snapshots (
    company_id integer NOT NULL,
    kpi_id integer NOT NULL,
    value numeric,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: news_releases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.news_releases (
    id integer NOT NULL,
    company_id integer,
    slug text NOT NULL,
    url text NOT NULL,
    title text,
    body text,
    scraped_at timestamp with time zone DEFAULT now(),
    published_at timestamp with time zone,
    is_processed boolean DEFAULT false
);


--
-- Name: news_releases_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.news_releases_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: news_releases_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.news_releases_id_seq OWNED BY public.news_releases.id;


--
-- Name: portfolio_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.portfolio_runs (
    id bigint NOT NULL,
    as_of date NOT NULL,
    target_size integer NOT NULL,
    status text NOT NULL,
    content jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT portfolio_runs_status_check CHECK ((status = ANY (ARRAY['ready'::text, 'not_ready'::text]))),
    CONSTRAINT portfolio_runs_target_size_check CHECK ((target_size > 0))
);


--
-- Name: portfolio_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.portfolio_runs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: portfolio_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.portfolio_runs_id_seq OWNED BY public.portfolio_runs.id;


--
-- Name: ranking_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ranking_runs (
    id integer NOT NULL,
    run_at timestamp with time zone DEFAULT now(),
    model_version text NOT NULL,
    company_count integer NOT NULL,
    eligible_count integer NOT NULL,
    scores jsonb NOT NULL,
    inputs_summary jsonb
);


--
-- Name: ranking_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ranking_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ranking_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ranking_runs_id_seq OWNED BY public.ranking_runs.id;


--
-- Name: research_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.research_documents (
    id integer NOT NULL,
    company_id integer NOT NULL,
    document_type text NOT NULL,
    title text NOT NULL,
    url text NOT NULL,
    published_at timestamp with time zone,
    document_text text NOT NULL,
    source_release_url text,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: research_documents_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.research_documents_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: research_documents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.research_documents_id_seq OWNED BY public.research_documents.id;


--
-- Name: schema_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schema_migrations (
    version character varying NOT NULL
);


--
-- Name: scrape_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scrape_runs (
    id integer NOT NULL,
    started_at timestamp with time zone DEFAULT now(),
    finished_at timestamp with time zone,
    status public.scrape_status DEFAULT 'running'::public.scrape_status NOT NULL,
    errors jsonb,
    error_message text,
    companies_found integer DEFAULT 0,
    news_added integer DEFAULT 0,
    job_type character varying(50)
);


--
-- Name: scrape_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.scrape_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: scrape_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.scrape_runs_id_seq OWNED BY public.scrape_runs.id;


--
-- Name: stock_prices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stock_prices (
    company_id integer NOT NULL,
    price_date date NOT NULL,
    close numeric(18,6) NOT NULL,
    currency character varying(3),
    fetched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: valuations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.valuations (
    id integer NOT NULL,
    company_id integer NOT NULL,
    valuation_type character varying(50) NOT NULL,
    intrinsic_value numeric(15,2),
    bull_case numeric(15,2),
    base_case numeric(15,2),
    bear_case numeric(15,2),
    fair_pe numeric(5,2),
    expected_cagr numeric(5,2),
    margin_of_safety numeric(5,2),
    calculated_at timestamp with time zone DEFAULT now(),
    assumptions jsonb,
    calculated_date date
);


--
-- Name: valuations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.valuations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: valuations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.valuations_id_seq OWNED BY public.valuations.id;


--
-- Name: watchlist; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.watchlist (
    company_id integer NOT NULL,
    active boolean DEFAULT true,
    user_id integer,
    added_at timestamp with time zone DEFAULT now(),
    notes text
);


--
-- Name: analysis id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis ALTER COLUMN id SET DEFAULT nextval('public.analysis_id_seq'::regclass);


--
-- Name: annual_reports id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.annual_reports ALTER COLUMN id SET DEFAULT nextval('public.annual_reports_id_seq'::regclass);


--
-- Name: companies id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies ALTER COLUMN id SET DEFAULT nextval('public.companies_id_seq'::regclass);


--
-- Name: company_facts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_facts ALTER COLUMN id SET DEFAULT nextval('public.company_facts_id_seq'::regclass);


--
-- Name: company_thesis_revisions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_thesis_revisions ALTER COLUMN id SET DEFAULT nextval('public.company_thesis_revisions_id_seq'::regclass);


--
-- Name: events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events ALTER COLUMN id SET DEFAULT nextval('public.events_id_seq'::regclass);


--
-- Name: financials id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.financials ALTER COLUMN id SET DEFAULT nextval('public.financials_id_seq'::regclass);


--
-- Name: insider_transactions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insider_transactions ALTER COLUMN id SET DEFAULT nextval('public.insider_transactions_id_seq'::regclass);


--
-- Name: jobs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs ALTER COLUMN id SET DEFAULT nextval('public.jobs_id_seq'::regclass);


--
-- Name: news_releases id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.news_releases ALTER COLUMN id SET DEFAULT nextval('public.news_releases_id_seq'::regclass);


--
-- Name: portfolio_runs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.portfolio_runs ALTER COLUMN id SET DEFAULT nextval('public.portfolio_runs_id_seq'::regclass);


--
-- Name: ranking_runs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ranking_runs ALTER COLUMN id SET DEFAULT nextval('public.ranking_runs_id_seq'::regclass);


--
-- Name: research_documents id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.research_documents ALTER COLUMN id SET DEFAULT nextval('public.research_documents_id_seq'::regclass);


--
-- Name: scrape_runs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scrape_runs ALTER COLUMN id SET DEFAULT nextval('public.scrape_runs_id_seq'::regclass);


--
-- Name: valuations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.valuations ALTER COLUMN id SET DEFAULT nextval('public.valuations_id_seq'::regclass);


--
-- Name: analysis analysis_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis
    ADD CONSTRAINT analysis_pkey PRIMARY KEY (id);


--
-- Name: annual_reports annual_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.annual_reports
    ADD CONSTRAINT annual_reports_pkey PRIMARY KEY (id);


--
-- Name: companies companies_borsdata_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT companies_borsdata_id_key UNIQUE (borsdata_id);


--
-- Name: companies companies_mfn_slug_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT companies_mfn_slug_key UNIQUE (mfn_slug);


--
-- Name: companies companies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT companies_pkey PRIMARY KEY (id);


--
-- Name: companies companies_ticker_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT companies_ticker_key UNIQUE (ticker);


--
-- Name: company_cyclicality_consensus company_cyclicality_consensus_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_cyclicality_consensus
    ADD CONSTRAINT company_cyclicality_consensus_pkey PRIMARY KEY (company_id);


--
-- Name: company_facts company_facts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_facts
    ADD CONSTRAINT company_facts_pkey PRIMARY KEY (id);


--
-- Name: company_facts company_facts_thesis_revision_id_heading_statement_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_facts
    ADD CONSTRAINT company_facts_thesis_revision_id_heading_statement_key UNIQUE (thesis_revision_id, heading, statement);


--
-- Name: company_profiles company_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_profiles
    ADD CONSTRAINT company_profiles_pkey PRIMARY KEY (company_id);


--
-- Name: company_thesis_revisions company_thesis_revisions_company_id_revision_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_thesis_revisions
    ADD CONSTRAINT company_thesis_revisions_company_id_revision_key UNIQUE (company_id, revision);


--
-- Name: company_thesis_revisions company_thesis_revisions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_thesis_revisions
    ADD CONSTRAINT company_thesis_revisions_pkey PRIMARY KEY (id);


--
-- Name: company_thesis_revisions company_thesis_revisions_source_analysis_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_thesis_revisions
    ADD CONSTRAINT company_thesis_revisions_source_analysis_id_key UNIQUE (source_analysis_id);


--
-- Name: events events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_pkey PRIMARY KEY (id);


--
-- Name: financials financials_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.financials
    ADD CONSTRAINT financials_pkey PRIMARY KEY (id);


--
-- Name: insider_transactions insider_transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insider_transactions
    ADD CONSTRAINT insider_transactions_pkey PRIMARY KEY (id);


--
-- Name: jobs jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_pkey PRIMARY KEY (id);


--
-- Name: kpi_history kpi_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kpi_history
    ADD CONSTRAINT kpi_history_pkey PRIMARY KEY (company_id, kpi_id, period_type, price_type, year);


--
-- Name: kpi_snapshot_history kpi_snapshot_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kpi_snapshot_history
    ADD CONSTRAINT kpi_snapshot_history_pkey PRIMARY KEY (company_id, kpi_id, observation_date);


--
-- Name: kpi_snapshots kpi_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kpi_snapshots
    ADD CONSTRAINT kpi_snapshots_pkey PRIMARY KEY (company_id, kpi_id);


--
-- Name: news_releases news_releases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.news_releases
    ADD CONSTRAINT news_releases_pkey PRIMARY KEY (id);


--
-- Name: news_releases news_releases_url_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.news_releases
    ADD CONSTRAINT news_releases_url_key UNIQUE (url);


--
-- Name: portfolio_runs portfolio_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.portfolio_runs
    ADD CONSTRAINT portfolio_runs_pkey PRIMARY KEY (id);


--
-- Name: ranking_runs ranking_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ranking_runs
    ADD CONSTRAINT ranking_runs_pkey PRIMARY KEY (id);


--
-- Name: research_documents research_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.research_documents
    ADD CONSTRAINT research_documents_pkey PRIMARY KEY (id);


--
-- Name: research_documents research_documents_url_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.research_documents
    ADD CONSTRAINT research_documents_url_key UNIQUE (url);


--
-- Name: schema_migrations schema_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (version);


--
-- Name: scrape_runs scrape_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scrape_runs
    ADD CONSTRAINT scrape_runs_pkey PRIMARY KEY (id);


--
-- Name: stock_prices stock_prices_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stock_prices
    ADD CONSTRAINT stock_prices_pkey PRIMARY KEY (company_id, price_date);


--
-- Name: valuations valuations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.valuations
    ADD CONSTRAINT valuations_pkey PRIMARY KEY (id);


--
-- Name: watchlist watchlist_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.watchlist
    ADD CONSTRAINT watchlist_pkey PRIMARY KEY (company_id);


--
-- Name: idx_analysis_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_analysis_company_id ON public.analysis USING btree (company_id);


--
-- Name: idx_annual_reports_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_annual_reports_company_id ON public.annual_reports USING btree (company_id);


--
-- Name: idx_annual_reports_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_annual_reports_unique ON public.annual_reports USING btree (company_id, year);


--
-- Name: idx_companies_isin; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_companies_isin ON public.companies USING btree (isin);


--
-- Name: idx_companies_sector; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_companies_sector ON public.companies USING btree (sector);


--
-- Name: idx_companies_ticker; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_companies_ticker ON public.companies USING btree (ticker);


--
-- Name: idx_company_facts_company_heading; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_company_facts_company_heading ON public.company_facts USING btree (company_id, heading, thesis_revision_id DESC);


--
-- Name: idx_company_thesis_revisions_latest; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_company_thesis_revisions_latest ON public.company_thesis_revisions USING btree (company_id, revision DESC);


--
-- Name: idx_events_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_events_company_id ON public.events USING btree (company_id);


--
-- Name: idx_financials_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_financials_company_id ON public.financials USING btree (company_id);


--
-- Name: idx_financials_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_financials_unique ON public.financials USING btree (company_id, period_type, period_end);


--
-- Name: idx_insider_transactions_borsdata_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_insider_transactions_borsdata_unique ON public.insider_transactions USING btree (company_id, person_name, transaction_type, shares, price_per_share, transaction_date, reported_at);


--
-- Name: idx_insider_transactions_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_insider_transactions_company_id ON public.insider_transactions USING btree (company_id);


--
-- Name: idx_jobs_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_jobs_company_id ON public.jobs USING btree (company_id);


--
-- Name: idx_kpi_history_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_kpi_history_company_id ON public.kpi_history USING btree (company_id);


--
-- Name: idx_news_releases_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_news_releases_company_id ON public.news_releases USING btree (company_id);


--
-- Name: idx_news_releases_is_processed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_news_releases_is_processed ON public.news_releases USING btree (is_processed) WHERE (is_processed = false);


--
-- Name: idx_news_releases_published_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_news_releases_published_at ON public.news_releases USING btree (published_at);


--
-- Name: idx_news_releases_slug; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_news_releases_slug ON public.news_releases USING btree (slug);


--
-- Name: idx_portfolio_runs_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_portfolio_runs_created_at ON public.portfolio_runs USING btree (created_at DESC);


--
-- Name: idx_research_documents_company_published; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_research_documents_company_published ON public.research_documents USING btree (company_id, published_at DESC);


--
-- Name: idx_scrape_runs_started_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_scrape_runs_started_at ON public.scrape_runs USING btree (started_at);


--
-- Name: idx_scrape_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_scrape_runs_status ON public.scrape_runs USING btree (status);


--
-- Name: idx_stock_prices_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stock_prices_company_id ON public.stock_prices USING btree (company_id);


--
-- Name: idx_valuations_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_valuations_company_id ON public.valuations USING btree (company_id);


--
-- Name: idx_valuations_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_valuations_unique ON public.valuations USING btree (company_id, valuation_type, calculated_date);


--
-- Name: idx_watchlist_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_watchlist_user_id ON public.watchlist USING btree (user_id);


--
-- Name: analysis analysis_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis
    ADD CONSTRAINT analysis_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: annual_reports annual_reports_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.annual_reports
    ADD CONSTRAINT annual_reports_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: company_cyclicality_consensus company_cyclicality_consensus_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_cyclicality_consensus
    ADD CONSTRAINT company_cyclicality_consensus_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: company_facts company_facts_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_facts
    ADD CONSTRAINT company_facts_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: company_facts company_facts_thesis_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_facts
    ADD CONSTRAINT company_facts_thesis_revision_id_fkey FOREIGN KEY (thesis_revision_id) REFERENCES public.company_thesis_revisions(id) ON DELETE CASCADE;


--
-- Name: company_profiles company_profiles_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_profiles
    ADD CONSTRAINT company_profiles_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: company_thesis_revisions company_thesis_revisions_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_thesis_revisions
    ADD CONSTRAINT company_thesis_revisions_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: company_thesis_revisions company_thesis_revisions_previous_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_thesis_revisions
    ADD CONSTRAINT company_thesis_revisions_previous_revision_id_fkey FOREIGN KEY (previous_revision_id) REFERENCES public.company_thesis_revisions(id);


--
-- Name: company_thesis_revisions company_thesis_revisions_source_analysis_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_thesis_revisions
    ADD CONSTRAINT company_thesis_revisions_source_analysis_id_fkey FOREIGN KEY (source_analysis_id) REFERENCES public.analysis(id);


--
-- Name: events events_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: financials financials_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.financials
    ADD CONSTRAINT financials_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: insider_transactions insider_transactions_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insider_transactions
    ADD CONSTRAINT insider_transactions_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: jobs jobs_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE SET NULL;


--
-- Name: kpi_history kpi_history_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kpi_history
    ADD CONSTRAINT kpi_history_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: kpi_snapshot_history kpi_snapshot_history_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kpi_snapshot_history
    ADD CONSTRAINT kpi_snapshot_history_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: kpi_snapshots kpi_snapshots_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kpi_snapshots
    ADD CONSTRAINT kpi_snapshots_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: news_releases news_releases_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.news_releases
    ADD CONSTRAINT news_releases_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: research_documents research_documents_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.research_documents
    ADD CONSTRAINT research_documents_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: stock_prices stock_prices_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stock_prices
    ADD CONSTRAINT stock_prices_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: valuations valuations_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.valuations
    ADD CONSTRAINT valuations_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: watchlist watchlist_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.watchlist
    ADD CONSTRAINT watchlist_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict dbmate


--
-- Dbmate schema migrations
--

INSERT INTO public.schema_migrations (version) VALUES
    ('20260702163712'),
    ('20260704145835'),
    ('20260706154541'),
    ('20260707145744'),
    ('20260805120000'),
    ('20260805123000'),
    ('20260806120000'),
    ('20260806143500'),
    ('20260807120000'),
    ('20260807143000'),
    ('20260808120000'),
    ('20260808143000'),
    ('20260809120000'),
    ('20260809143000'),
    ('20260812120000'),
    ('20260812130000'),
    ('20260812140000'),
    ('20260816120000'),
    ('20260816123000');
