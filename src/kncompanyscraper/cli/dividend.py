from kncompanyscraper.logger import get_logger

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
    from kncompanyscraper.main import _cmd_audit_dividends as main_audit
    main_audit(args.company_id, args.after, args.through)


def _cmd_review_dividends(args):
    from kncompanyscraper.main import _cmd_review_dividends as main_review
    main_review(
        args.company_id,
        args.after,
        args.through,
        args.status,
        args.reason,
        args.evidence_url,
    )
