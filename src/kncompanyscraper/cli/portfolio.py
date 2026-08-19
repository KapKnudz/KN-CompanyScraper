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
    from kncompanyscraper.main import _cmd_select_portfolio as main_select
    main_select(args.target_size, args.output)
