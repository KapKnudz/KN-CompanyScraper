import argparse
import sys
from pathlib import Path
from kncompanyscraper import scheduler
from kncompanyscraper.logger import get_logger
from kncompanyscraper.models.enums import RankingModel

logger = get_logger("main")


def _build_watchlist_analysis_service():
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.financial_repository import FinancialRepository
    from kncompanyscraper.repositories.valuation_repository import ValuationRepository
    from kncompanyscraper.analysis.financial.financial_skill import FinancialSkill
    from kncompanyscraper.analysis.sector_kpi_skill import SectorKpiSkill
    from kncompanyscraper.analysis.fundamental_kpi_skill import FundamentalKpiSkill
    from kncompanyscraper.analysis.valuation.valuation_skill import ValuationSkill
    from kncompanyscraper.analysis.valuation.reverse_dcf_skill import ReverseDcfSkill
    from kncompanyscraper.analysis.base.analysisengine import AnalysisEngine
    from kncompanyscraper.analysis.ranking.ranking_engine import RankingEngine
    from kncompanyscraper.analysis.watchlist.watchlist_analysis_service import (
        WatchlistAnalysisService,
    )
    from kncompanyscraper.repositories.ranking_repository import RankingRepository

    company_repo = CompanyRepository()
    financial_repo = FinancialRepository()
    valuation_repo = ValuationRepository()

    financial_skill = FinancialSkill(financial_repo)
    valuation_skill = ValuationSkill(valuation_repo, financial_repo)
    reverse_dcf_skill = ReverseDcfSkill(valuation_repo, financial_repo)

    sector_kpi_skill = SectorKpiSkill(valuation_repo)
    fundamental_kpi_skill = FundamentalKpiSkill(valuation_repo)
    analysis_engine = AnalysisEngine(
        [
            financial_skill,
            valuation_skill,
            reverse_dcf_skill,
            sector_kpi_skill,
            fundamental_kpi_skill,
        ]
    )
    ranking_engine = RankingEngine(ranking_repository=RankingRepository())

    return WatchlistAnalysisService(company_repo, analysis_engine, ranking_engine)


def _build_agent_model_adapter(provider, model, reasoning_effort):
    from kncompanyscraper.analysis.agent.openai_responses import OpenAIResponsesAdapter
    from kncompanyscraper.analysis.agent.deepseek_chat import DeepSeekChatAdapter
    from kncompanyscraper import config

    if provider == "openai":
        return OpenAIResponsesAdapter(
            api_key=config.OPENAI_API_KEY,
            model=model or config.OPENAI_MODEL,
            reasoning_effort=reasoning_effort or config.OPENAI_REASONING_EFFORT,
            max_output_tokens=config.OPENAI_MAX_OUTPUT_TOKENS,
        )
    elif provider == "deepseek":
        return DeepSeekChatAdapter(
            api_key=config.DEEPSEEK_API_KEY,
            model=model or config.DEEPSEEK_MODEL,
            reasoning_effort=reasoning_effort or config.DEEPSEEK_REASONING_EFFORT,
            max_output_tokens=config.DEEPSEEK_MAX_OUTPUT_TOKENS,
        )
    raise ValueError(f"Unknown provider: {provider}")


def _build_agent_context_builder():
    from kncompanyscraper.analysis.agent.agent_context_builder import (
        AgentContextBuilder,
    )
    from kncompanyscraper.analysis.agent.research_evidence import ResearchEvidenceBuilder
    from kncompanyscraper.analysis.agent.financial_evidence import (
        StructuredFinancialEvidenceBuilder,
    )
    from kncompanyscraper.repositories.research_document_repository import (
        ResearchDocumentRepository,
    )
    from kncompanyscraper.repositories.cyclicality_repository import (
        CyclicalityRepository,
    )
    from kncompanyscraper.repositories.financial_repository import FinancialRepository

    evidence_builder = ResearchEvidenceBuilder(ResearchDocumentRepository())
    financial_evidence_builder = StructuredFinancialEvidenceBuilder(FinancialRepository())
    cyclicality_repo = CyclicalityRepository()

    return AgentContextBuilder(
        evidence_builder=evidence_builder,
        cyclicality_repository=cyclicality_repo,
        financial_evidence_builder=financial_evidence_builder,
    )


def _build_agent_cohort_candidates(run, *, limit=None, context_builder=None):
    if context_builder is None:
        context_builder = _build_agent_context_builder()
    return context_builder.build_shortlist(
        run,
        run.results_by_company,
        limit=limit,
    )


def _refresh_agent_cohort_snapshot():
    from kncompanyscraper.repositories.ranking_repository import RankingRepository
    from kncompanyscraper.analysis.agent_cohort import AgentCohortService
    from kncompanyscraper.repositories.agent_cohort_repository import (
        AgentCohortRepository,
    )

    ranking_repo = RankingRepository()
    cohort_repo = AgentCohortRepository()
    service = AgentCohortService(ranking_repo, cohort_repo)

    return service.refresh_current_cohort()


def _original_research_evidence(company_id: int, original_ids: set[str]):
    from kncompanyscraper.analysis.agent.research_evidence import ResearchEvidenceBuilder
    from kncompanyscraper.repositories.research_document_repository import (
        ResearchDocumentRepository,
    )

    doc_repo = ResearchDocumentRepository()
    builder = ResearchEvidenceBuilder(doc_repo)
    # Re-extract only the evidence that was available at the time.
    return builder.build(company_id, filter_ids=original_ids).to_dict()


def main():
    from kncompanyscraper.cli import (
        agent,
        backtest,
        dividend,
        portfolio,
        ranking,
        sync,
    )

    parser = argparse.ArgumentParser(description="KN Company Scraper")
    subparsers = parser.add_subparsers(dest="command")

    # Register submodules
    sync.register(subparsers)
    ranking.register(subparsers)
    agent.register(subparsers)
    backtest.register(subparsers)
    dividend.register(subparsers)
    portfolio.register(subparsers)

    subparsers.add_parser("start-scheduler", help="Run the nightly/hourly job scheduler")

    args = parser.parse_args()

    if args.command == "start-scheduler":
        scheduler.start()
    elif hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
