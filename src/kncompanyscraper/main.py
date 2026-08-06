import argparse
import sys
from pathlib import Path

from kncompanyscraper import scheduler
from kncompanyscraper.logger import get_logger

logger = get_logger("main")


def _build_watchlist_analysis_service():
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.financial_repository import FinancialRepository
    from kncompanyscraper.repositories.valuation_repository import ValuationRepository
    from kncompanyscraper.analysis.financial.financial_skill import FinancialSkill
    from kncompanyscraper.analysis.valuation.valuation_skill import ValuationSkill
    from kncompanyscraper.analysis.base.analysisengine import AnalysisEngine
    from kncompanyscraper.analysis.ranking.ranking_engine import RankingEngine
    from kncompanyscraper.analysis.watchlist.watchlist_analysis_service import WatchlistAnalysisService
    company_repo = CompanyRepository()
    financial_repo = FinancialRepository()
    valuation_repo = ValuationRepository()

    financial_skill = FinancialSkill(financial_repo)
    valuation_skill = ValuationSkill(valuation_repo, financial_repo)

    analysis_engine = AnalysisEngine([financial_skill, valuation_skill])
    ranking_engine = RankingEngine()

    return WatchlistAnalysisService(company_repo, analysis_engine, ranking_engine)


def _cmd_rank_watchlist():
    """Run the deterministic watchlist ranking from persisted PostgreSQL data."""
    ranking = _build_watchlist_analysis_service().rank_watchlist()

    if not ranking.scores:
        print("No active companies found in watchlist.")
        return

    print("# Watchlist ranking\n")
    for i, cs in enumerate(ranking.scores, 1):
        print(
            f"{i:>3}. {cs.name:<25} "
            f"total={cs.total_score:>5.1f}  "
            f"quality={cs.quality_score:>5.1f}  "
            f"growth={cs.growth_score:>5.1f}  "
            f"valuation={cs.valuation_score:>5.1f}  "
            f"balance={cs.balance_sheet_score:>5.1f}  "
            f"data={cs.data_quality}"
        )
        if cs.candidate_reason:
            print(f"     Reason: {cs.candidate_reason}")
        if cs.flags:
            print(f"     Flags: {', '.join(cs.flags)}")
        if cs.positives:
            for p in cs.positives[:5]:
                print(f"     + {p}")
        if cs.negatives:
            for n in cs.negatives[:3]:
                print(f"     - {n}")
        print()

    # Print shortlist summary
    shortlist = ranking.shortlist_for_agent(top_n=25, max_total=30)
    print(f"---")
    print(f"Total companies ranked: {len(ranking.scores)}")
    print(f"Agent shortlist size:   {len(shortlist)}")


def _cmd_sync_borsdata():
    """Fetch Börsdata inputs and persist them before any analysis is run."""
    from kncompanyscraper.borsdata.client import BorsdataClient
    from kncompanyscraper.borsdata.ingestion import BorsdataIngestionService
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.financial_repository import FinancialRepository
    from kncompanyscraper.repositories.valuation_repository import ValuationRepository

    company_repo = CompanyRepository()
    companies = company_repo.get_active_companies()
    if not companies:
        print("No active companies found in watchlist.")
        return

    service = BorsdataIngestionService(
        BorsdataClient(),
        FinancialRepository(),
        ValuationRepository(),
    )
    synced = service.sync_companies(companies)
    print(f"Synced Börsdata inputs for {synced} companies.")


def _cmd_map_borsdata():
    """Resolve local watchlist companies to Börsdata instrument identifiers."""
    from kncompanyscraper.borsdata.client import BorsdataClient
    from kncompanyscraper.borsdata.instrument_mapping import BorsdataInstrumentMappingService
    from kncompanyscraper.repositories.company_repository import CompanyRepository

    company_repo = CompanyRepository()
    companies = company_repo.get_active_companies()
    result = BorsdataInstrumentMappingService(BorsdataClient(), company_repo).map_companies(companies)

    print(f"Mapped {result.mapped} companies to Börsdata instruments.")
    if result.unresolved:
        print(f"Unresolved: {', '.join(result.unresolved)}")


def _cmd_export_agent_prompts(output_dir: Path):
    """Export model-ready prompts for the deterministic shortlist."""
    from kncompanyscraper.analysis.agent.agent_context_builder import AgentContextBuilder
    from kncompanyscraper.analysis.agent.prompt_exporter import AgentPromptExporter

    run = _build_watchlist_analysis_service().analyze_watchlist()
    candidates = AgentContextBuilder().build_shortlist(run.ranking, run.results_by_company)
    paths = AgentPromptExporter().export(candidates, output_dir)
    print(f"Exported {len(paths)} agent prompts to {output_dir}.")


def _cmd_analyze_shortlist(max_candidates: int, model: str | None, reasoning_effort: str | None):
    """Analyze and persist a spend-bounded subset of the current shortlist."""
    from kncompanyscraper.analysis.agent.agent_analysis_service import AgentAnalysisService
    from kncompanyscraper.analysis.agent.agent_context_builder import AgentContextBuilder
    from kncompanyscraper.analysis.agent.execution_boundary import AgentExecutionBoundary
    from kncompanyscraper.analysis.agent.openai_responses import OpenAIResponsesAdapter
    from kncompanyscraper.repositories.analysis_repository import AnalysisRepository

    try:
        model_adapter = OpenAIResponsesAdapter(model=model, reasoning_effort=reasoning_effort)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    run = _build_watchlist_analysis_service().analyze_watchlist()
    candidates = AgentContextBuilder().build_shortlist(run.ranking, run.results_by_company)
    candidates = candidates[:max_candidates]
    if not candidates:
        print("No companies available in the agent shortlist.")
        return

    service = AgentAnalysisService(
        model_adapter,
        AgentExecutionBoundary(AnalysisRepository()),
    )
    persisted = service.analyze(candidates)
    print(f"Persisted {len(persisted)} stock analyses.")


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def main():
    parser = argparse.ArgumentParser(description="KN Company Scraper")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("rank-watchlist", help="Run deterministic watchlist ranking")
    subparsers.add_parser("sync-borsdata", help="Persist Börsdata inputs for the active watchlist")
    subparsers.add_parser("map-borsdata", help="Map watchlist companies to Börsdata instruments")
    export_parser = subparsers.add_parser(
        "export-agent-prompts",
        help="Export prompts for the agent shortlist without calling a model",
    )
    export_parser.add_argument("--output-dir", required=True, type=Path)
    analyze_parser = subparsers.add_parser(
        "analyze-shortlist",
        help="Call OpenAI for a bounded shortlist subset and persist validated results",
    )
    analyze_parser.add_argument("--max-candidates", required=True, type=_positive_int)
    analyze_parser.add_argument("--model")
    analyze_parser.add_argument(
        "--reasoning-effort",
        choices=("low", "medium", "high", "xhigh", "max"),
    )

    args = parser.parse_args()

    if args.command == "rank-watchlist":
        _cmd_rank_watchlist()
    elif args.command == "sync-borsdata":
        _cmd_sync_borsdata()
    elif args.command == "map-borsdata":
        _cmd_map_borsdata()
    elif args.command == "export-agent-prompts":
        _cmd_export_agent_prompts(args.output_dir)
    elif args.command == "analyze-shortlist":
        _cmd_analyze_shortlist(args.max_candidates, args.model, args.reasoning_effort)
    else:
        # Default: start the scheduler
        logger.info("Starting KN-CompanyScraper")
        try:
            scheduler.start()
        except KeyboardInterrupt:
            logger.info("Shutting down gracefully (Ctrl+C received)")


if __name__ == "__main__":
    main()
