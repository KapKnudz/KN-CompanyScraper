"""Production composition root for application services.

CLI and scheduler modules should use these factories instead of repeating
repository graphs and constructor signatures.
"""

from __future__ import annotations

from datetime import date

from kncompanyscraper import config


def build_watchlist_analysis_service():
    from kncompanyscraper.analysis.base.analysisengine import AnalysisEngine
    from kncompanyscraper.analysis.fundamental_kpi_skill import FundamentalKpiSkill
    from kncompanyscraper.analysis.financial.financial_skill import FinancialSkill
    from kncompanyscraper.analysis.insider.insider_skill import InsiderSkill
    from kncompanyscraper.analysis.ranking.ranking_engine import RankingEngine
    from kncompanyscraper.analysis.sector_kpi_skill import SectorKpiSkill
    from kncompanyscraper.analysis.valuation.reverse_dcf_skill import ReverseDcfSkill
    from kncompanyscraper.analysis.valuation.valuation_skill import ValuationSkill
    from kncompanyscraper.analysis.watchlist.watchlist_analysis_service import (
        WatchlistAnalysisService,
    )
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.financial_repository import FinancialRepository
    from kncompanyscraper.repositories.insider_repository import InsiderRepository
    from kncompanyscraper.repositories.ranking_repository import RankingRepository
    from kncompanyscraper.repositories.valuation_repository import ValuationRepository

    company_repository = CompanyRepository()
    financial_repository = FinancialRepository()
    valuation_repository = ValuationRepository()
    insider_repository = InsiderRepository()
    analysis_engine = AnalysisEngine(
        [
            FinancialSkill(financial_repository),
            ValuationSkill(valuation_repository, financial_repository),
            ReverseDcfSkill(valuation_repository, financial_repository),
            SectorKpiSkill(valuation_repository),
            FundamentalKpiSkill(valuation_repository),
            InsiderSkill(insider_repository),
        ]
    )
    ranking_engine = RankingEngine(ranking_repository=RankingRepository())
    return WatchlistAnalysisService(company_repository, analysis_engine, ranking_engine)


def build_agent_model_adapter(provider, model, reasoning_effort):
    if provider == "openai":
        from kncompanyscraper.analysis.agent.openai_responses import OpenAIResponsesAdapter

        return OpenAIResponsesAdapter(
            api_key=config.OPENAI_API_KEY,
            model=model or config.OPENAI_MODEL,
            reasoning_effort=reasoning_effort or config.OPENAI_REASONING_EFFORT,
            max_output_tokens=config.OPENAI_MAX_OUTPUT_TOKENS,
        )
    if provider == "deepseek":
        from kncompanyscraper.analysis.agent.deepseek_chat import DeepSeekChatAdapter

        return DeepSeekChatAdapter(
            api_key=config.DEEPSEEK_API_KEY,
            model=model or config.DEEPSEEK_MODEL,
            reasoning_effort=reasoning_effort or config.DEEPSEEK_REASONING_EFFORT,
            max_output_tokens=config.DEEPSEEK_MAX_OUTPUT_TOKENS,
        )
    raise ValueError(f"Unknown provider: {provider}")


def build_agent_context_builder():
    from kncompanyscraper.analysis.agent.agent_context_builder import AgentContextBuilder
    from kncompanyscraper.analysis.agent.financial_evidence import (
        StructuredFinancialEvidenceBuilder,
    )
    from kncompanyscraper.analysis.agent.peer_benchmarking import PeerComparisonBuilder
    from kncompanyscraper.analysis.agent.research_evidence import ResearchEvidenceBuilder
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.financial_repository import FinancialRepository
    from kncompanyscraper.repositories.insider_repository import InsiderRepository
    from kncompanyscraper.repositories.news_repository import NewsRepository
    from kncompanyscraper.repositories.research_document_repository import (
        ResearchDocumentRepository,
    )
    from kncompanyscraper.repositories.valuation_repository import ValuationRepository

    financial_repository = FinancialRepository()
    valuation_repository = ValuationRepository()
    return AgentContextBuilder(
        evidence_builder=ResearchEvidenceBuilder(
            ResearchDocumentRepository(),
            NewsRepository(),
            InsiderRepository(),
            valuation_repository,
        ),
        financial_evidence_builder=StructuredFinancialEvidenceBuilder(financial_repository),
        peer_comparison_builder=PeerComparisonBuilder(
            CompanyRepository(), financial_repository, valuation_repository
        ),
    )


def build_borsdata_ingestion_service():
    from kncompanyscraper.borsdata.client import BorsdataClient
    from kncompanyscraper.borsdata.ingestion import BorsdataIngestionService
    from kncompanyscraper.repositories.dividend_repository import DividendRepository
    from kncompanyscraper.repositories.financial_repository import FinancialRepository
    from kncompanyscraper.repositories.valuation_repository import ValuationRepository

    return BorsdataIngestionService(
        BorsdataClient(),
        FinancialRepository(),
        ValuationRepository(),
        DividendRepository(),
    )


def build_ranking_performance_evaluator():
    from kncompanyscraper.analysis.ranking_performance import RankingPerformanceEvaluator
    from kncompanyscraper.repositories.benchmark_repository import BenchmarkRepository
    from kncompanyscraper.repositories.dividend_repository import DividendRepository
    from kncompanyscraper.repositories.valuation_repository import ValuationRepository

    return RankingPerformanceEvaluator(
        ValuationRepository(), BenchmarkRepository(), DividendRepository()
    )


def build_ranking_challenger_performance_evaluator():
    from kncompanyscraper.analysis.ranking_challenger_performance import (
        RankingChallengerPerformanceEvaluator,
    )
    from kncompanyscraper.repositories.benchmark_repository import BenchmarkRepository
    from kncompanyscraper.repositories.dividend_repository import DividendRepository
    from kncompanyscraper.repositories.valuation_repository import ValuationRepository

    return RankingChallengerPerformanceEvaluator(
        ValuationRepository(), BenchmarkRepository(), DividendRepository()
    )


def build_agent_cohort_candidates(run, *, limit=None, context_builder=None):
    if context_builder is None:
        context_builder = build_agent_context_builder()
    return context_builder.build_shortlist(
        run.ranking, run.results_by_company, limit=limit
    )


def refresh_agent_cohort_snapshot():
    from kncompanyscraper.analysis.agent_cohort import AgentCohortService
    from kncompanyscraper.repositories.agent_cohort_repository import AgentCohortRepository
    from kncompanyscraper.repositories.ranking_repository import RankingRepository

    as_of = date.today()
    deterministic_run = RankingRepository().get_latest_deterministic_run(as_of)
    if deterministic_run is None:
        raise SystemExit("No deterministic ranking run found; run rank-watchlist first.")
    return AgentCohortService(AgentCohortRepository()).refresh(
        deterministic_run, as_of=as_of
    )


def build_original_research_evidence(company_id: int, original_ids: set[str]):
    from kncompanyscraper.analysis.agent.research_evidence import ResearchEvidenceBuilder
    from kncompanyscraper.repositories.insider_repository import InsiderRepository
    from kncompanyscraper.repositories.news_repository import NewsRepository
    from kncompanyscraper.repositories.research_document_repository import (
        ResearchDocumentRepository,
    )
    from kncompanyscraper.repositories.valuation_repository import ValuationRepository

    return ResearchEvidenceBuilder(
        ResearchDocumentRepository(),
        NewsRepository(),
        InsiderRepository(),
        ValuationRepository(),
    ).build(
        company_id, filter_ids=original_ids
    ).to_dict()


def build_thesis_update_service(model_adapter):
    """Build the incremental-thesis workflow with its repository graph."""
    from kncompanyscraper.analysis.agent.execution_boundary import AgentExecutionBoundary
    from kncompanyscraper.analysis.agent.thesis_update import ThesisUpdateContextBuilder
    from kncompanyscraper.analysis.agent.thesis_update_service import (
        ThesisUpdateExecutionBoundary,
        ThesisUpdateService,
    )
    from kncompanyscraper.repositories.analysis_repository import AnalysisRepository
    from kncompanyscraper.repositories.thesis_repository import ThesisRepository

    analysis_repository = AnalysisRepository()
    return ThesisUpdateService(
        model_adapter,
        ThesisUpdateContextBuilder(ThesisRepository()),
        ThesisUpdateExecutionBoundary(AgentExecutionBoundary(analysis_repository)),
        raw_response_repository=analysis_repository,
    )


def build_comparative_review_service(model_adapter):
    """Build comparative review with all repositories required by reranking."""
    from kncompanyscraper.analysis.agent.comparative_review import ComparativeReviewService
    from kncompanyscraper.repositories.comparative_review_repository import (
        ComparativeReviewRepository,
    )
    from kncompanyscraper.repositories.thesis_challenge_repository import (
        ThesisChallengeRepository,
    )

    return ComparativeReviewService(
        model_adapter,
        ComparativeReviewRepository(),
        ThesisChallengeRepository(),
    )
