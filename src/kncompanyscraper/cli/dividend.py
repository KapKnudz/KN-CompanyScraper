from kncompanyscraper.logger import get_logger
from kncompanyscraper.constants import BORSDATA_DIVIDEND_SOURCE

logger = get_logger("cli.dividend")


def register(subparsers):
    audit_div_parser = subparsers.add_parser(
        "audit-dividends", help="Inspect and resolve quarantined dividend events"
    )
    audit_div_parser.add_argument("--company-id", type=int, required=True)
    audit_div_parser.add_argument("--after", required=True, help="YYYY-MM-DD")
    audit_div_parser.add_argument("--through", required=True, help="YYYY-MM-DD")
    audit_div_parser.set_defaults(func=_cmd_audit_dividends)

    review_div_parser = subparsers.add_parser(
        "review-dividends", help="Update the status of a dividend event"
    )
    review_div_parser.add_argument("--company-id", type=int, required=True)
    review_div_parser.add_argument("--after", required=True, help="YYYY-MM-DD")
    review_div_parser.add_argument("--through", required=True, help="YYYY-MM-DD")
    review_div_parser.add_argument(
        "--status", choices=("pending", "approved", "excluded"), required=True
    )
    review_div_parser.add_argument("--reason", required=True)
    review_div_parser.add_argument("--evidence-url")
    review_div_parser.set_defaults(func=_cmd_review_dividends)


def _cmd_audit_dividends(args):
    from datetime import date
    from kncompanyscraper.repositories.dividend_repository import DividendRepository

    after = date.fromisoformat(args.after)
    through = date.fromisoformat(args.through)
    repository = DividendRepository()
    events = repository.get_dividends(
        args.company_id, after_date=after, through_date=through
    )
    reviews = repository.get_reviews(
        args.company_id,
        after_date=after,
        through_date=through,
        source=BORSDATA_DIVIDEND_SOURCE,
    )
    for event in events:
        review = reviews.get(repository.review_key(
            event.ex_date, event.amount, event.currency, event.dividend_type
        ))
        status = review.status if review else "pending"
        print(f"{event.ex_date} {event.amount:g} {event.currency} {status}")


def _cmd_review_dividends(args):
    from datetime import date
    from kncompanyscraper.repositories.dividend_repository import DividendRepository

    count = DividendRepository().review_events(
        args.company_id,
        after_date=date.fromisoformat(args.after),
        through_date=date.fromisoformat(args.through),
        status=args.status,
        reason=args.reason,
        evidence_url=args.evidence_url,
        source=BORSDATA_DIVIDEND_SOURCE,
    )
    print(f"Reviewed {count} dividend events.")
