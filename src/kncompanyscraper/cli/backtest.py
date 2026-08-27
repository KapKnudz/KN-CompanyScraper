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
    from kncompanyscraper.main import run_backtest_command
    run_backtest_command(args.periods, args.attribution_csv, args.scoring_audit_csv)


def _cmd_calibrate_weights(args):
    from kncompanyscraper.analysis.backtesting.weight_calibration import (
        calibrate_weights,
        load_attribution_rows,
    )

    model = RankingModel(args.ranking_model)
    rows = load_attribution_rows(args.attribution_csv, model, args.horizon_months)
    report = calibrate_weights(rows, model, args.horizon_months)
    print(f"Calibration: {report.ranking_model.value}, {report.horizon_months}m")
    print(f"Frozen weights: {report.frozen_weights}")
    print(f"Candidate weights: {report.candidate_weights}")
    print(f"Recommendation ready: {report.recommendation_ready}")
    for reason in report.readiness_reasons:
        print(f"Reason: {reason}")


def _cmd_analyze_scoring_audit(args):
    from kncompanyscraper.analysis.backtesting.metric_audit_analysis import (
        analyze_metric_audit,
        load_metric_rows,
    )

    rows = load_metric_rows(args.scoring_audit_csv, args.horizon_months)
    report = analyze_metric_audit(rows, args.horizon_months)
    print(f"Metric audit: {report.horizon_months}m, {len(rows)} rows")
    for diagnostic in report.diagnostics:
        print(
            f"{diagnostic.key}: coverage={diagnostic.coverage:.1%}, "
            f"holdout excess delta={diagnostic.holdout_excess_delta:.1%}"
        )


def _cmd_evaluate_ranking_performance(args):
    from kncompanyscraper.jobs.ranking_performance_job import RankingPerformanceJob
    from kncompanyscraper.repositories.ranking_repository import RankingRepository
    from kncompanyscraper.composition import build_ranking_performance_evaluator

    result = RankingPerformanceJob(
        RankingRepository(),
        build_ranking_performance_evaluator(),
    ).run(max_horizon_months=args.max_horizon_months)
    print(f"Evaluated {result.evaluated_count} horizons ({result.complete_count} complete).")


def _cmd_report_ranking_performance(args):
    from kncompanyscraper.repositories.ranking_repository import RankingRepository

    rows = RankingRepository().list_performance_evaluations(
        ranking_run_id=args.ranking_run_id, limit=args.limit
    )
    for row in rows:
        print(
            f"Snapshot {row['snapshot_month']} · run {row['ranking_run_id']} · "
            f"{row['horizon_months']}m · {row['status']}"
        )


def _cmd_evaluate_ranking_challengers(args):
    from kncompanyscraper.jobs.ranking_challenger_performance_job import RankingChallengerPerformanceJob
    from kncompanyscraper.repositories.ranking_challenger_repository import RankingChallengerRepository
    from kncompanyscraper.composition import build_ranking_challenger_performance_evaluator

    result = RankingChallengerPerformanceJob(
        RankingChallengerRepository(),
        build_ranking_challenger_performance_evaluator(),
    ).run(max_horizon_months=args.max_horizon_months)
    print(f"Evaluated {result.evaluated_count} challenger horizons ({result.complete_count} complete).")


def _cmd_report_ranking_challengers(args):
    from kncompanyscraper.repositories.ranking_challenger_repository import RankingChallengerRepository

    rows = RankingChallengerRepository().list_performance_evaluations(
        challenger_snapshot_id=args.challenger_snapshot_id, limit=args.limit
    )
    for row in rows:
        print(
            f"Snapshot {row['snapshot_month']} · challenger "
            f"{row['challenger_snapshot_id']} · {row['horizon_months']}m · {row['status']}"
        )
