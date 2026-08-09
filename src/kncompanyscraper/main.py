import argparse
import sys
from pathlib import Path
from statistics import mean

from kncompanyscraper import scheduler
from kncompanyscraper.logger import get_logger

logger = get_logger("main")


def _build_watchlist_analysis_service():
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.financial_repository import FinancialRepository
    from kncompanyscraper.repositories.insider_repository import InsiderRepository
    from kncompanyscraper.repositories.valuation_repository import ValuationRepository
    from kncompanyscraper.analysis.financial.financial_skill import FinancialSkill
    from kncompanyscraper.analysis.insider.insider_skill import InsiderSkill
    from kncompanyscraper.analysis.sector_kpi_skill import SectorKpiSkill
    from kncompanyscraper.analysis.fundamental_kpi_skill import FundamentalKpiSkill
    from kncompanyscraper.analysis.valuation.valuation_skill import ValuationSkill
    from kncompanyscraper.analysis.base.analysisengine import AnalysisEngine
    from kncompanyscraper.analysis.ranking.ranking_engine import RankingEngine
    from kncompanyscraper.analysis.watchlist.watchlist_analysis_service import WatchlistAnalysisService
    from kncompanyscraper.repositories.ranking_repository import RankingRepository
    company_repo = CompanyRepository()
    financial_repo = FinancialRepository()
    insider_repo = InsiderRepository()
    valuation_repo = ValuationRepository()

    financial_skill = FinancialSkill(financial_repo)
    insider_skill = InsiderSkill(insider_repo)
    valuation_skill = ValuationSkill(valuation_repo, financial_repo)

    sector_kpi_skill = SectorKpiSkill(valuation_repo)
    fundamental_kpi_skill = FundamentalKpiSkill(valuation_repo)
    analysis_engine = AnalysisEngine(
        [
            financial_skill,
            valuation_skill,
            insider_skill,
            sector_kpi_skill,
            fundamental_kpi_skill,
        ]
    )
    ranking_engine = RankingEngine(ranking_repository=RankingRepository())

    return WatchlistAnalysisService(company_repo, analysis_engine, ranking_engine)


def _cmd_rank_watchlist():
    """Run the deterministic watchlist ranking from persisted PostgreSQL data."""
    from kncompanyscraper.analysis.ranking.ranking_engine import RankingEngine

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
            f"model={cs.ranking_model:<8}  "
            f"eligible={'yes' if cs.rank_eligible else 'no ':<3}  "
            f"data={cs.data_quality}"
        )
        if cs.candidate_reason:
            print(f"     Reason: {cs.candidate_reason}")
        if cs.flags:
            print(f"     Flags: {', '.join(cs.flags)}")
        if cs.eligibility_reasons:
            print(f"     Incomplete: {', '.join(cs.eligibility_reasons)}")
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
    print(f"Ranking run persisted (model version: {RankingEngine.RANKING_MODEL_VERSION})")


def _cmd_sync_borsdata():
    """Fetch Börsdata inputs and persist them before any analysis is run."""
    from kncompanyscraper.borsdata.client import BorsdataClient
    from kncompanyscraper.borsdata.ingestion import BorsdataIngestionService
    from kncompanyscraper.borsdata.instrument_mapping import BorsdataInstrumentMappingService
    from kncompanyscraper.jobs.borsdata_job import BorsdataJob
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.financial_repository import FinancialRepository
    from kncompanyscraper.repositories.job_repository import JobRepository
    from kncompanyscraper.repositories.valuation_repository import ValuationRepository

    company_repo = CompanyRepository()
    companies = company_repo.get_active_companies()
    if not companies:
        print("No active companies found in watchlist.")
        return

    client = BorsdataClient()
    BorsdataInstrumentMappingService(client, company_repo).map_companies(companies)
    companies = company_repo.get_active_companies()

    job = BorsdataJob(
        BorsdataIngestionService(
            client,
            FinancialRepository(),
            ValuationRepository(),
        ),
        JobRepository(),
    )
    result = job.run(companies)
    print(
        f"Börsdata sync complete: {result.synced} synced, "
        f"{result.failed} failed, {result.attempted} attempted."
    )
    for failure in result.failures:
        print(f"  - {failure}")


def _cmd_sync_borsdata_insiders():
    """Fetch and persist Börsdata open-market insider transactions."""
    from kncompanyscraper.borsdata.client import BorsdataClient
    from kncompanyscraper.jobs.borsdata_insider_job import BorsdataInsiderJob
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.insider_repository import InsiderRepository
    from kncompanyscraper.repositories.job_repository import JobRepository

    companies = CompanyRepository().get_active_companies()
    result = BorsdataInsiderJob(
        BorsdataClient(),
        InsiderRepository(),
        JobRepository(),
    ).run(companies)
    print(
        f"Börsdata insider sync complete: {result.synced} synced, "
        f"{result.failed} failed, {result.inserted} transactions inserted."
    )
    for failure in result.failures:
        print(f"  - {failure}")


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


def _cmd_import_watchlist(csv_path: Path):
    """Import a semicolon-delimited Börsdata watchlist into PostgreSQL."""
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.watchlist_import import WatchlistImportService

    try:
        result = WatchlistImportService(CompanyRepository()).import_file(csv_path)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    print(
        f"Imported {result.imported} watchlist companies "
        f"({result.created} created, {result.updated} updated)."
    )


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


def _cmd_backtest(periods: int):
    """Run backtest against historical data."""
    from kncompanyscraper.analysis.backtesting.backtest_engine import BacktestEngine
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.financial_repository import FinancialRepository
    from kncompanyscraper.repositories.valuation_repository import ValuationRepository

    engine = BacktestEngine(
        CompanyRepository(),
        FinancialRepository(),
        ValuationRepository(),
    )
    results = engine.run(num_periods=periods)

    if not results:
        print("No backtest results available (insufficient historical data).")
        return

    # Aggregate across periods
    all_top_6m = [r.top_decile_spread_6m for r in results if r.top_decile_spread_6m is not None]
    all_top_12m = [r.top_decile_spread_12m for r in results if r.top_decile_spread_12m is not None]

    print(f"# Backtest Results: {len(results)} periods\n")

    # Decile performance table
    print("## Average Decile Performance")
    print(
        f"{'Decile':<8} {'Avg 6m':>8} {'Avg 12m':>8} "
        f"{'Hit 6m':>8} {'Hit 12m':>8} {'N 6m':>6} {'N 12m':>6}"
    )
    print("-" * 66)
    for decile_num in range(1, 11):
        decile_results = []
        for r in results:
            for d in r.deciles:
                if d.decile == decile_num:
                    decile_results.append(d)
                    break
        if not decile_results:
            continue
        avg_6m = _weighted_decile_mean(decile_results, "avg_6m_return", "count_6m")
        avg_12m = _weighted_decile_mean(decile_results, "avg_12m_return", "count_12m")
        hit_6m = _weighted_decile_mean(decile_results, "hit_rate_6m", "count_6m")
        hit_12m = _weighted_decile_mean(decile_results, "hit_rate_12m", "count_12m")
        count_6m = sum(d.count_6m for d in decile_results)
        count_12m = sum(d.count_12m for d in decile_results)
        print(
            f"{decile_num:<8} "
            f"{_format_percent(avg_6m, 1):>8} "
            f"{_format_percent(avg_12m, 1):>8} "
            f"{_format_percent(hit_6m, 0):>8} "
            f"{_format_percent(hit_12m, 0):>8} "
            f"{count_6m:>6} {count_12m:>6}"
        )

    if not any(result.deciles for result in results):
        print("At least 10 eligible companies are required for decile statistics.")

    # Top-decile spread
    print(f"\n## Top-Bottom Spread")
    if all_top_6m:
        print(f"6-month spread:  {mean(all_top_6m):.1%} avg")
    if all_top_12m:
        print(f"12-month spread: {mean(all_top_12m):.1%} avg")

    # Category correlations
    print(f"\n## Category Correlation with 12-month Returns")
    cat_corrs: dict[str, list[float]] = {}
    for r in results:
        for c in r.correlations:
            if c.correlation_12m is not None:
                cat_corrs.setdefault(c.category, []).append(c.correlation_12m)
    for category, corrs in cat_corrs.items():
        label = category.replace("_score", "").replace("_", " ").title()
        print(f"  {label:<20} {mean(corrs):>+.3f}")

    print(f"\n## Period Details")
    for r in results:
        spread_str = ""
        if r.top_decile_spread_6m is not None:
            spread_str += f" 6m-spread={r.top_decile_spread_6m:.1%}"
        if r.top_decile_spread_12m is not None:
            spread_str += f" 12m-spread={r.top_decile_spread_12m:.1%}"
        print(f"  {r.observation_date}: {r.eligible_count} eligible{spread_str}")


def _weighted_decile_mean(deciles, value_field: str, count_field: str) -> float | None:
    observations = [
        (getattr(decile, value_field), getattr(decile, count_field))
        for decile in deciles
        if getattr(decile, value_field) is not None
        and getattr(decile, count_field) > 0
    ]
    total_count = sum(count for _, count in observations)
    if total_count == 0:
        return None
    return sum(value * count for value, count in observations) / total_count


def _format_percent(value: float | None, decimals: int) -> str:
    return f"{value:.{decimals}%}" if value is not None else "—"


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
    subparsers.add_parser(
        "sync-borsdata-insiders",
        help="Persist Börsdata open-market insider transactions",
    )
    subparsers.add_parser("map-borsdata", help="Map watchlist companies to Börsdata instruments")
    import_parser = subparsers.add_parser(
        "import-watchlist",
        help="Import and activate companies from a Börsdata watchlist CSV",
    )
    import_parser.add_argument("--csv", required=True, type=Path)
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
    backtest_parser = subparsers.add_parser(
        "backtest",
        help="Backtest ranking against subsequent returns",
    )
    backtest_parser.add_argument(
        "--periods",
        type=_positive_int,
        default=12,
        help="Number of month-end periods to backtest (default: 12)",
    )

    args = parser.parse_args()

    if args.command == "rank-watchlist":
        _cmd_rank_watchlist()
    elif args.command == "sync-borsdata":
        _cmd_sync_borsdata()
    elif args.command == "sync-borsdata-insiders":
        _cmd_sync_borsdata_insiders()
    elif args.command == "map-borsdata":
        _cmd_map_borsdata()
    elif args.command == "import-watchlist":
        _cmd_import_watchlist(args.csv)
    elif args.command == "export-agent-prompts":
        _cmd_export_agent_prompts(args.output_dir)
    elif args.command == "analyze-shortlist":
        _cmd_analyze_shortlist(args.max_candidates, args.model, args.reasoning_effort)
    elif args.command == "backtest":
        _cmd_backtest(args.periods)
    else:
        # Default: start the scheduler
        logger.info("Starting KN-CompanyScraper")
        try:
            scheduler.start()
        except KeyboardInterrupt:
            logger.info("Shutting down gracefully (Ctrl+C received)")


if __name__ == "__main__":
    main()
