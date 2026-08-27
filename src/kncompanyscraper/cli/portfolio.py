from pathlib import Path
from kncompanyscraper.logger import get_logger

logger = get_logger("cli.portfolio")


def register(subparsers):
    portfolio_parser = subparsers.add_parser(
        "select-portfolio", help="Build a durable portfolio-selection run"
    )
    portfolio_parser.add_argument("--target-size", type=int, default=5)
    portfolio_parser.add_argument("--output", type=Path, help="JSON export path")
    portfolio_parser.set_defaults(func=_cmd_select_portfolio)


def _cmd_select_portfolio(args):
    import json
    from datetime import date
    from kncompanyscraper.analysis.portfolio_selection import PortfolioSelectionService
    from kncompanyscraper.repositories.analysis_repository import AnalysisRepository
    from kncompanyscraper.repositories.ranking_repository import RankingRepository
    from kncompanyscraper.repositories.portfolio_repository import PortfolioRepository

    as_of = date.today()
    ranking = RankingRepository().get_latest_monthly_run_before(as_of.replace(day=1))
    if ranking is None:
        raise SystemExit("No monthly ranking run found; run comparative ranking first.")
    ranking_scores = ranking.get("scores", [])
    analyses = AnalysisRepository().get_latest_validated_stock_analyses()
    from kncompanyscraper.analysis.ranking.company_score import CompanyScore, WatchlistRanking

    scores = [CompanyScore(**score) for score in ranking_scores]
    selection = PortfolioSelectionService().select(
        WatchlistRanking(scores=scores), analyses, as_of=as_of, target_size=args.target_size
    )
    PortfolioRepository().save_run(selection.to_dict())
    payload = json.dumps(selection.to_dict(), indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
