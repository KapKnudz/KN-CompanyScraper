import argparse
import sys
from pathlib import Path
from kncompanyscraper import scheduler
from kncompanyscraper.logger import get_logger
from kncompanyscraper.models.enums import RankingModel

logger = get_logger("main")


def _build_watchlist_analysis_service():
    from kncompanyscraper.composition import build_watchlist_analysis_service

    return build_watchlist_analysis_service()


def _build_agent_model_adapter(provider, model, reasoning_effort):
    from kncompanyscraper.composition import build_agent_model_adapter

    return build_agent_model_adapter(provider, model, reasoning_effort)


def _build_agent_context_builder():
    from kncompanyscraper.composition import build_agent_context_builder

    return build_agent_context_builder()


def _build_agent_cohort_candidates(run, *, limit=None, context_builder=None):
    from kncompanyscraper.composition import build_agent_cohort_candidates

    return build_agent_cohort_candidates(run, limit=limit, context_builder=context_builder)


def _refresh_agent_cohort_snapshot():
    from kncompanyscraper.composition import refresh_agent_cohort_snapshot

    return refresh_agent_cohort_snapshot()


def _original_research_evidence(company_id: int, original_ids: set[str]):
    from kncompanyscraper.composition import build_original_research_evidence

    return build_original_research_evidence(company_id, original_ids)


def run_backtest_command(
    periods: int,
    attribution_csv: Path | None = None,
    scoring_audit_csv: Path | None = None,
):
    """Run and report the historical ranking backtest."""
    import csv
    from dataclasses import asdict
    from statistics import mean

    from kncompanyscraper.analysis.backtesting.backtest_engine import BacktestEngine
    from kncompanyscraper.repositories.benchmark_repository import BenchmarkRepository
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.dividend_repository import DividendRepository
    from kncompanyscraper.repositories.financial_repository import FinancialRepository
    from kncompanyscraper.repositories.valuation_repository import ValuationRepository

    results = BacktestEngine(
        CompanyRepository(),
        FinancialRepository(),
        ValuationRepository(),
        DividendRepository(),
        BenchmarkRepository(),
    ).run(num_periods=periods)
    if not results:
        print("No backtest results available (insufficient historical data).")
        return

    print(f"# Backtest Results: {len(results)} periods\n")
    print("## Average Decile Performance")
    print(
        f"{'Decile':<8} {'Avg 6m':>8} {'Avg 12m':>8} "
        f"{'Hit 6m':>8} {'Hit 12m':>8} {'N 6m':>6} {'N 12m':>6}"
    )
    print("-" * 66)
    for decile_num in range(1, 11):
        deciles = [
            decile
            for result in results
            for decile in result.deciles
            if decile.decile == decile_num
        ]
        if not deciles:
            continue
        def weighted(field, count_field):
            values = [
                (getattr(item, field), getattr(item, count_field))
                for item in deciles
                if getattr(item, field) is not None and getattr(item, count_field) > 0
            ]
            total = sum(count for _, count in values)
            return sum(value * count for value, count in values) / total if total else None

        format_percent = lambda value, digits: (
            f"{value:.{digits}%}" if value is not None else "—"
        )
        print(
            f"{decile_num:<8} "
            f"{format_percent(weighted('avg_6m_return', 'count_6m'), 1):>8} "
            f"{format_percent(weighted('avg_12m_return', 'count_12m'), 1):>8} "
            f"{format_percent(weighted('hit_rate_6m', 'count_6m'), 0):>8} "
            f"{format_percent(weighted('hit_rate_12m', 'count_12m'), 0):>8} "
            f"{sum(item.count_6m for item in deciles):>6} "
            f"{sum(item.count_12m for item in deciles):>6}"
        )

    if not any(result.deciles for result in results):
        print("At least 10 eligible companies are required for decile statistics.")

    for horizon, field in ((6, "top_decile_spread_6m"), (12, "top_decile_spread_12m")):
        values = [getattr(result, field) for result in results if getattr(result, field) is not None]
        if values:
            positive = sum(value > 0 for value in values)
            print(
                f"Top-bottom {horizon}m{' ' * (6 if horizon == 6 else 5)}"
                f"{positive}/{len(values)} positive "
                f"({positive / len(values):.0%}); median={sorted(values)[len(values) // 2]:.1%}"
            )
    print("Results are overlapping monthly observations, not independent statistical trials.")

    if attribution_csv:
        rows = [asdict(item) for result in results for item in result.attributions]
        if rows:
            with attribution_csv.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        print(f"Company attribution CSV written to {attribution_csv}")

    if scoring_audit_csv:
        rows = [asdict(item) for result in results for item in result.metric_attributions]
        if rows:
            with scoring_audit_csv.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        print(f"Scoring audit CSV written to {scoring_audit_csv}")


def _cmd_report_ranking_performance(ranking_run_id: int | None, limit: int = 24):
    from kncompanyscraper.repositories.ranking_repository import RankingRepository

    rows = RankingRepository().list_performance_evaluations(
        ranking_run_id=ranking_run_id,
        limit=limit,
    )
    if not rows:
        suffix = f" for ranking run {ranking_run_id}" if ranking_run_id else ""
        print(f"No stored ranking-performance evaluations{suffix}.")
        return
    for row in rows:
        result = row["result"]
        print(
            f"Snapshot {row['snapshot_month']} · run {row['ranking_run_id']} · "
            f"{row['horizon_months']}m"
        )
        print(f"Status: {row['status']}")
        for key, label in (
            ("deterministic_shortlist", "Deterministic shortlist"),
            ("individual_thesis_ranking", "Individual theses"),
            ("final_ranking", "Comparative final"),
        ):
            item = result.get(key, {})
            value = item.get("value")
            price = item.get("price_value")
            value_text = f"{value:.1%}" if value is not None else "n/a"
            price_text = f"{price:.1%}" if price is not None else "n/a"
            label_spaces = {
                "Deterministic shortlist": 10,
                "Individual theses": 15,
                "Comparative final": 15,
            }[label]
            value_spaces = 5 if label == "Comparative final" else 6
            count_spaces = 4 if label != "Deterministic shortlist" else 3
            print(
                f"{label}{' ' * label_spaces}{value_text}"
                f"{' ' * value_spaces}{price_text}{' ' * count_spaces}"
                f"{item.get('observed_count', 0)}/{item.get('company_count', 0)}"
            )
        for label, key, formatter in (
            ("Agent value added", "agent_value_added", lambda v: f"{v:.1%}"),
            ("Comparative-agent increment", "comparative_agent_value_added", lambda v: f"{v:.1%}"),
        ):
            value = result.get(key)
            if value is not None:
                spaces = 17 if label == "Agent value added" else 7
                print(f"{label}{' ' * spaces}{formatter(value)}")
        recall = result.get("cohort_recall_at_30")
        if recall and recall.get("value") is not None:
            print(
                f"{'Cohort recall@30':<32} {recall['value']:.1%}  "
                f"({recall.get('captured_winner_count', 0)}/{recall.get('winner_count', 0)})"
            )
        for warning in result.get("warnings", []):
            print(f"Warning: {warning}")
        for key, label in (
            ("incomplete_dividend_company_ids", "incomplete dividends"),
            ("currency_mismatch_company_ids", "currency mismatch"),
        ):
            ids = result.get("final_ranking", {}).get(key, [])
            if ids:
                print(f"final: {label} {ids}")


def _cmd_report_ranking_challengers(challenger_snapshot_id: int | None, limit: int = 24):
    from kncompanyscraper.repositories.ranking_challenger_repository import (
        RankingChallengerRepository,
    )

    rows = RankingChallengerRepository().list_performance_evaluations(
        challenger_snapshot_id=challenger_snapshot_id,
        limit=limit,
    )
    if not rows:
        suffix = (
            f" for challenger snapshot {challenger_snapshot_id}"
            if challenger_snapshot_id
            else ""
        )
        print(f"No stored challenger-performance evaluations{suffix}.")
        return
    for row in rows:
        result = row["result"]
        print(
            f"Snapshot {row['snapshot_month']} · challenger {row['challenger_snapshot_id']} · "
            f"{row['horizon_months']}m"
        )
        print(f"Status: {row['status']}")
        for key, label in (
            ("production_top_30", "Production top-30 return"),
            ("challenger_top_30", "Challenger top-30 return"),
        ):
            item = result.get(key, {})
            value = item.get("value")
            value_text = f"{value:.1%}" if value is not None else "n/a"
            print(
                f"{label}{' ' * 11}{value_text}  "
                f"({item.get('observed_count', 0)}/{item.get('company_count', 0)})"
            )
        for key, label in (
            ("production_rank_correlation", "Production rank correlation"),
            ("challenger_rank_correlation", "Challenger rank correlation"),
        ):
            item = result.get(key, {})
            value = item.get("value")
            value_text = f"{value:.3f}" if value is not None else "n/a"
            label_spaces = 7 if "correlation" in key else 11
            print(
                f"{label}{' ' * label_spaces}{value_text}  "
                f"({item.get('observed_count', 0)}/{item.get('company_count', 0)})"
            )
        for key, label in (
            ("production_decile_spread", "Production decile spread"),
            ("challenger_decile_spread", "Challenger decile spread"),
        ):
            value = result.get(key, {}).get("value")
            if value is not None:
                print(f"{label:<34} {value:.1%}")
        membership = result.get("membership_attribution", {})
        if membership.get("value") is not None:
            print(
                f"{'Membership attribution':<34} {membership['value']:.1%} "
                f"entries={membership.get('entrant_company_ids', [])} "
                f"exits={membership.get('exit_company_ids', [])}"
            )
        missing = result.get("challenger_rank_correlation", {}).get("missing_company_ids", [])
        if missing:
            print(f"Coverage blockers: full-universe companies {missing}")
        for warning in result.get("warnings", []):
            print(f"Warning: {warning}")


# Backwards-compatible public name for callers that imported the old handler.
_cmd_backtest = run_backtest_command


def build_parser():
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

    return parser


def main():
    parser = build_parser()

    args = parser.parse_args()

    if args.command == "start-scheduler":
        scheduler.start()
    elif hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
