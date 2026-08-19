from kncompanyscraper.logger import get_logger
from kncompanyscraper.models.enums import RankingModel

logger = get_logger("cli.ranking")


def register(subparsers):
    subparsers.add_parser(
        "rank-watchlist",
        help="Run the deterministic watchlist ranking from persisted PostgreSQL data",
    ).set_defaults(func=_cmd_rank_watchlist)

    subparsers.add_parser(
        "snapshot-ranking-challenger",
        help="Persist this month's evaluation-only metric-removal challenger",
    ).set_defaults(func=_cmd_snapshot_ranking_challenger)

    subparsers.add_parser(
        "refresh-agent-cohort",
        help="Update the immutable monthly agent-shortlist cohort",
    ).set_defaults(func=_cmd_refresh_agent_cohort)

    rank_analyzed_parser = subparsers.add_parser(
        "rank-analyzed-candidates",
        help="Persist a comparative snapshot from latest individual theses",
    )
    from pathlib import Path
    rank_analyzed_parser.add_argument(
        "--output", type=Path, help="Optional JSON export of the results"
    )
    rank_analyzed_parser.set_defaults(func=_cmd_rank_analyzed_candidates)


def _cmd_rank_watchlist(args):
    from kncompanyscraper.analysis.ranking.ranking_engine import RankingEngine
    from kncompanyscraper.main import (
        _build_watchlist_analysis_service,
        _refresh_agent_cohort_snapshot,
    )

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

    cohort_id, cohort, created = _refresh_agent_cohort_snapshot()
    print(f"---")
    print(f"Total companies ranked: {len(ranking.scores)}")
    print(f"Agent cohort size:      {len(cohort.members)}")
    print(
        f"Agent cohort snapshot:  {cohort_id} ({'created' if created else 'existing'})"
    )
    print(
        f"Ranking run persisted (model version: {RankingEngine.RANKING_MODEL_VERSION})"
    )


def _cmd_snapshot_ranking_challenger(args):
    from datetime import date
    from kncompanyscraper.analysis.ranking_challenger import RankingChallenger
    from kncompanyscraper.repositories.ranking_challenger_repository import (
        RankingChallengerRepository,
    )
    from kncompanyscraper.repositories.ranking_repository import RankingRepository

    today = date.today()
    source_run = RankingRepository().get_latest_deterministic_run(today)
    if source_run is None:
        raise SystemExit(
            "No deterministic ranking run exists; run rank-watchlist first."
        )
    snapshot = RankingChallenger().build(
        source_run,
        snapshot_month=today.replace(day=1),
    )
    RankingChallengerRepository().save_snapshot(snapshot)
    print(f"Persisted challenger snapshot for {snapshot.snapshot_month.isoformat()}.")


def _cmd_refresh_agent_cohort(args):
    from kncompanyscraper.main import _refresh_agent_cohort_snapshot

    cohort_id, cohort, created = _refresh_agent_cohort_snapshot()
    status = "Created" if created else "Updated existing"
    print(f"{status} agent cohort snapshot {cohort_id} with {len(cohort.members)} members.")


def _cmd_rank_analyzed_candidates(args):
    import json
    from kncompanyscraper.analysis.comparative_ranking import ComparativeRankingService
    from kncompanyscraper.repositories.comparative_review_repository import (
        ComparativeReviewRepository,
    )
    from kncompanyscraper.repositories.ranking_repository import RankingRepository
    from kncompanyscraper.repositories.thesis_repository import ThesisRepository

    thesis_repo = ThesisRepository()
    ranking_repo = RankingRepository()
    review_repo = ComparativeReviewRepository()

    latest_theses = thesis_repo.get_latest_accepted_theses()
    if not latest_theses:
        print("No accepted individual theses found. Run analyze-shortlist first.")
        return

    ranking_run = ranking_repo.get_latest_deterministic_run()
    if not ranking_run:
        print("No deterministic ranking run found. Run rank-watchlist first.")
        return

    result = ComparativeRankingService(review_repo).rank(latest_theses, ranking_run)

    print(f"# Comparative ranking (Run {result.ranking_run_id})\n")
    for tier in sorted(result.tiers.keys()):
        print(f"## Tier {tier}")
        for case in result.tiers[tier]:
            print(
                f"- {case.ticker:<6} {case.name:<25} "
                f"return={case.base_return:>5.1%} "
                f"downside={case.bear_downside:>5.1%} "
                f"confidence={case.confidence:<8}"
            )
        print()

    if args.output:
        with args.output.open("w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
        print(f"Exported results to {args.output}")
