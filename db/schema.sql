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
-- Name: agent_cohort_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_cohort_snapshots (
    id bigint NOT NULL,
    snapshot_month date NOT NULL,
    deterministic_run_id integer NOT NULL,
    policy_version text NOT NULL,
    target_size integer NOT NULL,
    grace_months integer NOT NULL,
    eligible_universe_company_ids jsonb NOT NULL,
    top_company_ids jsonb NOT NULL,
    members jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT agent_cohort_snapshots_eligible_universe_company_ids_check CHECK ((jsonb_typeof(eligible_universe_company_ids) = 'array'::text)),
    CONSTRAINT agent_cohort_snapshots_grace_months_check CHECK ((grace_months > 0)),
    CONSTRAINT agent_cohort_snapshots_members_check CHECK ((jsonb_typeof(members) = 'array'::text)),
    CONSTRAINT agent_cohort_snapshots_target_size_check CHECK ((target_size > 0)),
    CONSTRAINT agent_cohort_snapshots_top_company_ids_check CHECK ((jsonb_typeof(top_company_ids) = 'array'::text))
);


--
-- Name: agent_cohort_snapshots_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agent_cohort_snapshots_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: agent_cohort_snapshots_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agent_cohort_snapshots_id_seq OWNED BY public.agent_cohort_snapshots.id;


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
-- Name: benchmark_prices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.benchmark_prices (
    series_code text NOT NULL,
    price_date date NOT NULL,
    close numeric(18,6) NOT NULL,
    return_basis text NOT NULL,
    source text NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT benchmark_prices_close_check CHECK ((close > (0)::numeric)),
    CONSTRAINT benchmark_prices_return_basis_check CHECK ((return_basis = ANY (ARRAY['price_return'::text, 'gross_total_return'::text, 'net_total_return'::text])))
);


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
-- Name: company_dividends; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.company_dividends (
    id bigint NOT NULL,
    company_id integer NOT NULL,
    ex_date date NOT NULL,
    amount numeric(18,6) NOT NULL,
    currency character varying(3) NOT NULL,
    dividend_type integer NOT NULL,
    distribution_frequency text,
    source text NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT company_dividends_amount_check CHECK ((amount > (0)::numeric))
);


--
-- Name: company_dividends_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.company_dividends_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: company_dividends_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.company_dividends_id_seq OWNED BY public.company_dividends.id;


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
-- Name: comparative_agent_reviews; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.comparative_agent_reviews (
    id bigint NOT NULL,
    ranking_run_id integer NOT NULL,
    status text NOT NULL,
    raw_response text NOT NULL,
    content jsonb,
    final_scores jsonb,
    created_by text NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    validation_error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    validated_at timestamp with time zone,
    CONSTRAINT comparative_agent_reviews_content_check CHECK (((content IS NULL) OR (jsonb_typeof(content) = 'object'::text))),
    CONSTRAINT comparative_agent_reviews_final_scores_check CHECK (((final_scores IS NULL) OR (jsonb_typeof(final_scores) = 'array'::text))),
    CONSTRAINT comparative_agent_reviews_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'accepted'::text, 'rejected'::text])))
);


--
-- Name: comparative_agent_reviews_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.comparative_agent_reviews_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: comparative_agent_reviews_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.comparative_agent_reviews_id_seq OWNED BY public.comparative_agent_reviews.id;


--
-- Name: dividend_data_coverage; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dividend_data_coverage (
    company_id integer NOT NULL,
    covered_from date NOT NULL,
    covered_through date NOT NULL,
    source text NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT dividend_data_coverage_check CHECK ((covered_from <= covered_through))
);


--
-- Name: dividend_event_reviews; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dividend_event_reviews (
    company_id integer NOT NULL,
    ex_date date NOT NULL,
    amount numeric(18,6) NOT NULL,
    currency character varying(3) NOT NULL,
    dividend_type integer NOT NULL,
    source text NOT NULL,
    status text NOT NULL,
    reason text NOT NULL,
    evidence_url text,
    reviewed_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT dividend_event_reviews_amount_check CHECK ((amount > (0)::numeric)),
    CONSTRAINT dividend_event_reviews_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'approved'::text, 'excluded'::text])))
);


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
-- Name: ranking_challenger_performance_evaluations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ranking_challenger_performance_evaluations (
    id bigint NOT NULL,
    challenger_snapshot_id bigint CONSTRAINT ranking_challenger_performance__challenger_snapshot_id_not_null NOT NULL,
    horizon_months integer CONSTRAINT ranking_challenger_performance_evaluati_horizon_months_not_null NOT NULL,
    target_date date NOT NULL,
    status text NOT NULL,
    policy_version text CONSTRAINT ranking_challenger_performance_evaluati_policy_version_not_null NOT NULL,
    result jsonb NOT NULL,
    evaluated_at timestamp with time zone DEFAULT now() CONSTRAINT ranking_challenger_performance_evaluation_evaluated_at_not_null NOT NULL,
    CONSTRAINT ranking_challenger_performance_evaluations_horizon_months_check CHECK ((horizon_months > 0)),
    CONSTRAINT ranking_challenger_performance_evaluations_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'complete'::text])))
);


--
-- Name: ranking_challenger_performance_evaluations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ranking_challenger_performance_evaluations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ranking_challenger_performance_evaluations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ranking_challenger_performance_evaluations_id_seq OWNED BY public.ranking_challenger_performance_evaluations.id;


--
-- Name: ranking_challenger_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ranking_challenger_snapshots (
    id bigint NOT NULL,
    snapshot_month date NOT NULL,
    source_ranking_run_id integer NOT NULL,
    source_as_of date NOT NULL,
    policy_version text NOT NULL,
    status text NOT NULL,
    company_count integer NOT NULL,
    eligible_count integer NOT NULL,
    affected_company_count integer NOT NULL,
    scores jsonb NOT NULL,
    production_top_company_ids jsonb CONSTRAINT ranking_challenger_snapshot_production_top_company_ids_not_null NOT NULL,
    challenger_top_company_ids jsonb CONSTRAINT ranking_challenger_snapshot_challenger_top_company_ids_not_null NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ranking_challenger_snapshots_affected_company_count_check CHECK ((affected_company_count >= 0)),
    CONSTRAINT ranking_challenger_snapshots_company_count_check CHECK ((company_count > 0)),
    CONSTRAINT ranking_challenger_snapshots_eligible_count_check CHECK ((eligible_count >= 0)),
    CONSTRAINT ranking_challenger_snapshots_status_check CHECK ((status = 'evaluation_only'::text))
);


--
-- Name: ranking_challenger_snapshots_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ranking_challenger_snapshots_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ranking_challenger_snapshots_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ranking_challenger_snapshots_id_seq OWNED BY public.ranking_challenger_snapshots.id;


--
-- Name: ranking_performance_evaluations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ranking_performance_evaluations (
    id bigint NOT NULL,
    ranking_run_id integer NOT NULL,
    horizon_months integer NOT NULL,
    target_date date NOT NULL,
    status text NOT NULL,
    policy_version text NOT NULL,
    result jsonb NOT NULL,
    evaluated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ranking_performance_evaluations_horizon_months_check CHECK ((horizon_months > 0)),
    CONSTRAINT ranking_performance_evaluations_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'complete'::text, 'insufficient_membership'::text])))
);


--
-- Name: ranking_performance_evaluations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ranking_performance_evaluations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ranking_performance_evaluations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ranking_performance_evaluations_id_seq OWNED BY public.ranking_performance_evaluations.id;


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
    inputs_summary jsonb,
    snapshot_month date
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
-- Name: thesis_challenges; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.thesis_challenges (
    id bigint NOT NULL,
    company_id integer NOT NULL,
    thesis_revision_id bigint NOT NULL,
    question text NOT NULL,
    challenged_claim text NOT NULL,
    origin text NOT NULL,
    severity text NOT NULL,
    verdict text NOT NULL,
    status text NOT NULL,
    content jsonb NOT NULL,
    created_by text NOT NULL,
    resolution_note text,
    resolved_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    response_raw_analysis_id bigint,
    response_analysis_id bigint,
    response_thesis_revision_id bigint,
    CONSTRAINT thesis_challenges_challenged_claim_check CHECK ((length(TRIM(BOTH FROM challenged_claim)) > 0)),
    CONSTRAINT thesis_challenges_origin_check CHECK ((origin = ANY (ARRAY['human'::text, 'automatic_critic'::text, 'comparative_agent'::text]))),
    CONSTRAINT thesis_challenges_question_check CHECK ((length(TRIM(BOTH FROM question)) > 0)),
    CONSTRAINT thesis_challenges_severity_check CHECK ((severity = ANY (ARRAY['low'::text, 'medium'::text, 'high'::text]))),
    CONSTRAINT thesis_challenges_status_check CHECK ((status = ANY (ARRAY['open'::text, 'upheld'::text, 'revised'::text, 'rejected'::text]))),
    CONSTRAINT thesis_challenges_verdict_check CHECK ((verdict = ANY (ARRAY['survives'::text, 'revision_required'::text, 'insufficient_evidence'::text, 'reject'::text])))
);


--
-- Name: thesis_challenges_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.thesis_challenges_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: thesis_challenges_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.thesis_challenges_id_seq OWNED BY public.thesis_challenges.id;


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
-- Name: agent_cohort_snapshots id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_cohort_snapshots ALTER COLUMN id SET DEFAULT nextval('public.agent_cohort_snapshots_id_seq'::regclass);


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
-- Name: company_dividends id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_dividends ALTER COLUMN id SET DEFAULT nextval('public.company_dividends_id_seq'::regclass);


--
-- Name: company_facts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_facts ALTER COLUMN id SET DEFAULT nextval('public.company_facts_id_seq'::regclass);


--
-- Name: company_thesis_revisions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_thesis_revisions ALTER COLUMN id SET DEFAULT nextval('public.company_thesis_revisions_id_seq'::regclass);


--
-- Name: comparative_agent_reviews id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.comparative_agent_reviews ALTER COLUMN id SET DEFAULT nextval('public.comparative_agent_reviews_id_seq'::regclass);


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
-- Name: ranking_challenger_performance_evaluations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ranking_challenger_performance_evaluations ALTER COLUMN id SET DEFAULT nextval('public.ranking_challenger_performance_evaluations_id_seq'::regclass);


--
-- Name: ranking_challenger_snapshots id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ranking_challenger_snapshots ALTER COLUMN id SET DEFAULT nextval('public.ranking_challenger_snapshots_id_seq'::regclass);


--
-- Name: ranking_performance_evaluations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ranking_performance_evaluations ALTER COLUMN id SET DEFAULT nextval('public.ranking_performance_evaluations_id_seq'::regclass);


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
-- Name: thesis_challenges id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.thesis_challenges ALTER COLUMN id SET DEFAULT nextval('public.thesis_challenges_id_seq'::regclass);


--
-- Name: valuations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.valuations ALTER COLUMN id SET DEFAULT nextval('public.valuations_id_seq'::regclass);


--
-- Name: agent_cohort_snapshots agent_cohort_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_cohort_snapshots
    ADD CONSTRAINT agent_cohort_snapshots_pkey PRIMARY KEY (id);


--
-- Name: agent_cohort_snapshots agent_cohort_snapshots_snapshot_month_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_cohort_snapshots
    ADD CONSTRAINT agent_cohort_snapshots_snapshot_month_key UNIQUE (snapshot_month);


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
-- Name: benchmark_prices benchmark_prices_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.benchmark_prices
    ADD CONSTRAINT benchmark_prices_pkey PRIMARY KEY (series_code, price_date);


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
-- Name: company_dividends company_dividends_company_id_ex_date_dividend_type_amount_c_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_dividends
    ADD CONSTRAINT company_dividends_company_id_ex_date_dividend_type_amount_c_key UNIQUE (company_id, ex_date, dividend_type, amount, currency, source);


--
-- Name: company_dividends company_dividends_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_dividends
    ADD CONSTRAINT company_dividends_pkey PRIMARY KEY (id);


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
-- Name: comparative_agent_reviews comparative_agent_reviews_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.comparative_agent_reviews
    ADD CONSTRAINT comparative_agent_reviews_pkey PRIMARY KEY (id);


--
-- Name: comparative_agent_reviews comparative_agent_reviews_ranking_run_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.comparative_agent_reviews
    ADD CONSTRAINT comparative_agent_reviews_ranking_run_id_key UNIQUE (ranking_run_id);


--
-- Name: dividend_data_coverage dividend_data_coverage_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dividend_data_coverage
    ADD CONSTRAINT dividend_data_coverage_pkey PRIMARY KEY (company_id);


--
-- Name: dividend_event_reviews dividend_event_reviews_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dividend_event_reviews
    ADD CONSTRAINT dividend_event_reviews_pkey PRIMARY KEY (company_id, ex_date, amount, currency, dividend_type, source);


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
-- Name: ranking_challenger_performance_evaluations ranking_challenger_performanc_challenger_snapshot_id_horizo_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ranking_challenger_performance_evaluations
    ADD CONSTRAINT ranking_challenger_performanc_challenger_snapshot_id_horizo_key UNIQUE (challenger_snapshot_id, horizon_months, policy_version);


--
-- Name: ranking_challenger_performance_evaluations ranking_challenger_performance_evaluations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ranking_challenger_performance_evaluations
    ADD CONSTRAINT ranking_challenger_performance_evaluations_pkey PRIMARY KEY (id);


--
-- Name: ranking_challenger_snapshots ranking_challenger_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ranking_challenger_snapshots
    ADD CONSTRAINT ranking_challenger_snapshots_pkey PRIMARY KEY (id);


--
-- Name: ranking_challenger_snapshots ranking_challenger_snapshots_snapshot_month_policy_version_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ranking_challenger_snapshots
    ADD CONSTRAINT ranking_challenger_snapshots_snapshot_month_policy_version_key UNIQUE (snapshot_month, policy_version);


--
-- Name: ranking_performance_evaluations ranking_performance_evaluatio_ranking_run_id_horizon_months_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ranking_performance_evaluations
    ADD CONSTRAINT ranking_performance_evaluatio_ranking_run_id_horizon_months_key UNIQUE (ranking_run_id, horizon_months);


--
-- Name: ranking_performance_evaluations ranking_performance_evaluations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ranking_performance_evaluations
    ADD CONSTRAINT ranking_performance_evaluations_pkey PRIMARY KEY (id);


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
-- Name: thesis_challenges thesis_challenges_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.thesis_challenges
    ADD CONSTRAINT thesis_challenges_pkey PRIMARY KEY (id);


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
-- Name: idx_company_dividends_company_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_company_dividends_company_date ON public.company_dividends USING btree (company_id, ex_date);


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
-- Name: idx_ranking_challenger_performance_status_target; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ranking_challenger_performance_status_target ON public.ranking_challenger_performance_evaluations USING btree (status, target_date);


--
-- Name: idx_ranking_challenger_source_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ranking_challenger_source_run ON public.ranking_challenger_snapshots USING btree (source_ranking_run_id);


--
-- Name: idx_ranking_performance_status_target; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ranking_performance_status_target ON public.ranking_performance_evaluations USING btree (status, target_date);


--
-- Name: idx_ranking_runs_monthly_model; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_ranking_runs_monthly_model ON public.ranking_runs USING btree (snapshot_month) WHERE (snapshot_month IS NOT NULL);


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
-- Name: idx_thesis_challenges_open_company; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_thesis_challenges_open_company ON public.thesis_challenges USING btree (company_id, severity, created_at DESC) WHERE (status = 'open'::text);


--
-- Name: idx_thesis_challenges_response_analysis; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_thesis_challenges_response_analysis ON public.thesis_challenges USING btree (response_analysis_id) WHERE (response_analysis_id IS NOT NULL);


--
-- Name: idx_thesis_challenges_response_raw_analysis; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_thesis_challenges_response_raw_analysis ON public.thesis_challenges USING btree (response_raw_analysis_id) WHERE (response_raw_analysis_id IS NOT NULL);


--
-- Name: idx_thesis_challenges_response_revision; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_thesis_challenges_response_revision ON public.thesis_challenges USING btree (response_thesis_revision_id) WHERE (response_thesis_revision_id IS NOT NULL);


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
-- Name: agent_cohort_snapshots agent_cohort_snapshots_deterministic_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_cohort_snapshots
    ADD CONSTRAINT agent_cohort_snapshots_deterministic_run_id_fkey FOREIGN KEY (deterministic_run_id) REFERENCES public.ranking_runs(id) ON DELETE RESTRICT;


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
-- Name: company_dividends company_dividends_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_dividends
    ADD CONSTRAINT company_dividends_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


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
-- Name: comparative_agent_reviews comparative_agent_reviews_ranking_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.comparative_agent_reviews
    ADD CONSTRAINT comparative_agent_reviews_ranking_run_id_fkey FOREIGN KEY (ranking_run_id) REFERENCES public.ranking_runs(id) ON DELETE CASCADE;


--
-- Name: dividend_data_coverage dividend_data_coverage_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dividend_data_coverage
    ADD CONSTRAINT dividend_data_coverage_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: dividend_event_reviews dividend_event_reviews_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dividend_event_reviews
    ADD CONSTRAINT dividend_event_reviews_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


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
-- Name: ranking_challenger_performance_evaluations ranking_challenger_performance_eval_challenger_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ranking_challenger_performance_evaluations
    ADD CONSTRAINT ranking_challenger_performance_eval_challenger_snapshot_id_fkey FOREIGN KEY (challenger_snapshot_id) REFERENCES public.ranking_challenger_snapshots(id) ON DELETE CASCADE;


--
-- Name: ranking_challenger_snapshots ranking_challenger_snapshots_source_ranking_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ranking_challenger_snapshots
    ADD CONSTRAINT ranking_challenger_snapshots_source_ranking_run_id_fkey FOREIGN KEY (source_ranking_run_id) REFERENCES public.ranking_runs(id) ON DELETE RESTRICT;


--
-- Name: ranking_performance_evaluations ranking_performance_evaluations_ranking_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ranking_performance_evaluations
    ADD CONSTRAINT ranking_performance_evaluations_ranking_run_id_fkey FOREIGN KEY (ranking_run_id) REFERENCES public.ranking_runs(id) ON DELETE CASCADE;


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
-- Name: thesis_challenges thesis_challenges_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.thesis_challenges
    ADD CONSTRAINT thesis_challenges_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: thesis_challenges thesis_challenges_response_analysis_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.thesis_challenges
    ADD CONSTRAINT thesis_challenges_response_analysis_id_fkey FOREIGN KEY (response_analysis_id) REFERENCES public.analysis(id);


--
-- Name: thesis_challenges thesis_challenges_response_raw_analysis_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.thesis_challenges
    ADD CONSTRAINT thesis_challenges_response_raw_analysis_id_fkey FOREIGN KEY (response_raw_analysis_id) REFERENCES public.analysis(id);


--
-- Name: thesis_challenges thesis_challenges_response_thesis_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.thesis_challenges
    ADD CONSTRAINT thesis_challenges_response_thesis_revision_id_fkey FOREIGN KEY (response_thesis_revision_id) REFERENCES public.company_thesis_revisions(id);


--
-- Name: thesis_challenges thesis_challenges_thesis_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.thesis_challenges
    ADD CONSTRAINT thesis_challenges_thesis_revision_id_fkey FOREIGN KEY (thesis_revision_id) REFERENCES public.company_thesis_revisions(id) ON DELETE CASCADE;


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
    ('20260816123000'),
    ('20260816130000'),
    ('20260816131000'),
    ('20260816132000'),
    ('20260817120000'),
    ('20260818120000'),
    ('20260818130000'),
    ('20260818140000'),
    ('20260818150000'),
    ('20260818160000'),
    ('20260818170000');
