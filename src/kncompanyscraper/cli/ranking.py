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
    from kncompanyscraper.composition import (
        build_watchlist_analysis_service,
        refresh_agent_cohort_snapshot,
    )

    ranking = build_watchlist_analysis_service().rank_watchlist()

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

    cohort_id, cohort, created = refresh_agent_cohort_snapshot()
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
    from kncompanyscraper.composition import refresh_agent_cohort_snapshot

    cohort_id, cohort, created = refresh_agent_cohort_snapshot()
    status = "Created" if created else "Updated existing"
    print(f"{status} agent cohort snapshot {cohort_id} with {len(cohort.members)} members.")


def _cmd_rank_analyzed_candidates(args):
    import json
    from kncompanyscraper.jobs.comparative_ranking_job import ComparativeRankingJob
    from kncompanyscraper.repositories.agent_cohort_repository import (
        AgentCohortRepository,
    )
    from kncompanyscraper.repositories.analysis_repository import AnalysisRepository
    from kncompanyscraper.repositories.ranking_repository import RankingRepository
    from kncompanyscraper.repositories.thesis_challenge_repository import (
        ThesisChallengeRepository,
    )

    ranking_repo = RankingRepository()
    result = ComparativeRankingJob(
        AnalysisRepository(),
        ThesisChallengeRepository(),
        ranking_repo,
        AgentCohortRepository(),
    ).run()
    if result.status == "no_analyses":
        print("No accepted individual theses found. Run analyze-shortlist first.")
        return

    ranking_run = ranking_repo.get_run(result.run_id)
    print(f"# Comparative ranking (Run {result.run_id})\n")
    for case in ranking_run["scores"]:
        base_band = case.get("base_band")
        base_return = (
            f"{base_band[0]:.1%}–{base_band[1]:.1%}"
            if base_band is not None
            else "n/a"
        )
        downside = case.get("bear_lower_bound")
        if downside is None:
            # Historical ranking snapshots used the two-bear display field.
            downside = case.get("worst_bear_lower_bound")
        downside_text = f"{downside:.1%}" if downside is not None else "n/a"
        print(
            f"{case['rank']:>3}. {case['ticker']:<8} "
            f"tier={case['tier']:<8} "
            f"base={base_return:<13} "
            f"downside={downside_text:<7} "
            f"confidence={case['evidence_confidence']}"
        )

    if args.output:
        with args.output.open("w", encoding="utf-8") as f:
            json.dump(ranking_run, f, indent=2, ensure_ascii=False)
        print(f"Exported results to {args.output}")
