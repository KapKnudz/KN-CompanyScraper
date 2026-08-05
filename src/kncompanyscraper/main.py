import argparse
import sys

from kncompanyscraper import scheduler
from kncompanyscraper.logger import get_logger

logger = get_logger("main")


def _cmd_rank_watchlist():
    """Run the deterministic watchlist ranking from persisted PostgreSQL data."""
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
    valuation_skill = ValuationSkill(valuation_repo)

    analysis_engine = AnalysisEngine([financial_skill, valuation_skill])
    ranking_engine = RankingEngine()

    service = WatchlistAnalysisService(company_repo, analysis_engine, ranking_engine)
    ranking = service.rank_watchlist()

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


def main():
    parser = argparse.ArgumentParser(description="KN Company Scraper")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("rank-watchlist", help="Run deterministic watchlist ranking")
    subparsers.add_parser("sync-borsdata", help="Persist Börsdata inputs for the active watchlist")

    args = parser.parse_args()

    if args.command == "rank-watchlist":
        _cmd_rank_watchlist()
    elif args.command == "sync-borsdata":
        _cmd_sync_borsdata()
    else:
        # Default: start the scheduler
        logger.info("Starting KN-CompanyScraper")
        try:
            scheduler.start()
        except KeyboardInterrupt:
            logger.info("Shutting down gracefully (Ctrl+C received)")


if __name__ == "__main__":
    main()
