from pathlib import Path
from kncompanyscraper.logger import get_logger
from kncompanyscraper.models.enums import RankingModel

logger = get_logger("cli.backtest")


def register(subparsers):
    backtest_parser = subparsers.add_parser(
        "backtest", help="Validate deterministic ranking policy over history"
    )
    backtest_parser.add_argument("--periods", type=int, default=12)
    backtest_parser.add_argument(
        "--attribution-csv",
        type=Path,
        help="Write long-form historical ranking and return data to CSV",
    )
    backtest_parser.add_argument(
        "--scoring-audit-csv",
        type=Path,
        help="Write long-form metric weights and score contributions to CSV",
    )
    backtest_parser.set_defaults(func=_cmd_backtest)

    calibration_parser = subparsers.add_parser(
        "calibrate-weights", help="Evaluate bounded ranking-weight candidates"
    )
    calibration_parser.add_argument("--attribution-csv", required=True, type=Path)
    calibration_parser.add_argument(
        "--ranking-model",
        choices=[m.value for m in RankingModel],
        default=RankingModel.GENERAL.value,
    )
    calibration_parser.add_argument(
        "--horizon-months", choices=(6, 12, 24, 36, 48), default=12, type=int
    )
    calibration_parser.set_defaults(func=_cmd_calibrate_weights)

    audit_parser = subparsers.add_parser(
        "analyze-scoring-audit", help="Evaluate individual metric sensitivities"
    )
    audit_parser.add_argument("--scoring-audit-csv", required=True, type=Path)
    audit_parser.add_argument(
        "--horizon-months", choices=(6, 12, 24, 36, 48), default=12, type=int
    )
    audit_parser.set_defaults(func=_cmd_analyze_scoring_audit)

    performance_parser = subparsers.add_parser(
        "evaluate-ranking-performance", help="Measure forward returns"
    )
    performance_parser.add_argument("--max-horizon-months", type=int, default=48)
    performance_parser.set_defaults(func=_cmd_evaluate_ranking_performance)

    report_performance_parser = subparsers.add_parser(
        "report-ranking-performance", help="Report realized ranking performance"
    )
    report_performance_parser.add_argument("--ranking-run-id", type=int)
    report_performance_parser.add_argument("--limit", type=int, default=24)
    report_performance_parser.set_defaults(func=_cmd_report_ranking_performance)

    evaluate_challenger_parser = subparsers.add_parser(
        "evaluate-ranking-challengers", help="Measure forward return for challengers"
    )
    evaluate_challenger_parser.add_argument("--max-horizon-months", type=int, default=48)
    evaluate_challenger_parser.set_defaults(func=_cmd_evaluate_ranking_challengers)

    report_challenger_parser = subparsers.add_parser(
        "report-ranking-challengers", help="Compare challengers to production"
    )
    report_challenger_parser.add_argument("--challenger-snapshot-id", type=int)
    report_challenger_parser.add_argument("--limit", type=int, default=24)
    report_challenger_parser.set_defaults(func=_cmd_report_ranking_challengers)


def _cmd_backtest(args):
    # This command is huge in main.py, I'll move its implementation logic if possible, 
    # but for now I'll just import it from where it ends up.
    # Actually, main.py is the one I'm emptying.
    from kncompanyscraper.main import _cmd_backtest as main_backtest
    main_backtest(args.periods, args.attribution_csv, args.scoring_audit_csv)


def _cmd_calibrate_weights(args):
    from kncompanyscraper.main import _cmd_calibrate_weights as main_calibrate
    main_calibrate(args.attribution_csv, args.ranking_model, args.horizon_months)


def _cmd_analyze_scoring_audit(args):
    from kncompanyscraper.main import _cmd_analyze_scoring_audit as main_analyze
    main_analyze(args.scoring_audit_csv, args.horizon_months)


def _cmd_evaluate_ranking_performance(args):
    from kncompanyscraper.main import _cmd_evaluate_ranking_performance as main_eval
    main_eval(args.max_horizon_months)


def _cmd_report_ranking_performance(args):
    from kncompanyscraper.main import _cmd_report_ranking_performance as main_report
    main_report(args.ranking_run_id, args.limit)


def _cmd_evaluate_ranking_challengers(args):
    from kncompanyscraper.main import _cmd_evaluate_ranking_challengers as main_eval_chall
    main_eval_chall(args.max_horizon_months)


def _cmd_report_ranking_challengers(args):
    from kncompanyscraper.main import _cmd_report_ranking_challengers as main_report_chall
    main_report_chall(args.challenger_snapshot_id, args.limit)
