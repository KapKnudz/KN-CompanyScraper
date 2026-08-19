from pathlib import Path
from kncompanyscraper.logger import get_logger

logger = get_logger("cli.agent")


def register(subparsers):
    export_prompts_parser = subparsers.add_parser(
        "export-agent-prompts", help="Export model-ready prompts for deterministic shortlist"
    )
    export_prompts_parser.add_argument("--output-dir", required=True, type=Path)
    export_prompts_parser.add_argument("--max-candidates", type=int, default=5)
    export_prompts_parser.set_defaults(func=_cmd_export_agent_prompts)

    check_readiness_parser = subparsers.add_parser(
        "check-agent-readiness", help="Report deterministic blockers"
    )
    check_readiness_parser.add_argument("--max-candidates", type=int, default=5)
    check_readiness_parser.set_defaults(func=_cmd_check_agent_readiness)

    analyze_shortlist_parser = subparsers.add_parser(
        "analyze-shortlist", help="Run model analysis for the agent shortlist"
    )
    analyze_shortlist_parser.add_argument("--max-candidates", type=int, default=1)
    analyze_shortlist_parser.add_argument("--provider", choices=("openai", "deepseek"), default="openai")
    analyze_shortlist_parser.add_argument("--model")
    analyze_shortlist_parser.add_argument("--reasoning-effort")
    analyze_shortlist_parser.add_argument("--company-ids", type=int, nargs="+")
    analyze_shortlist_parser.add_argument("--retry-rejected", action="store_true")
    analyze_shortlist_parser.set_defaults(func=_cmd_analyze_shortlist)

    update_shortlist_parser = subparsers.add_parser(
        "update-shortlist", help="Incremental thesis updates for existing analysts"
    )
    update_shortlist_parser.add_argument("--max-candidates", type=int, default=5)
    update_shortlist_parser.add_argument("--provider", choices=("openai", "deepseek"), default="openai")
    update_shortlist_parser.add_argument("--model")
    update_shortlist_parser.add_argument("--reasoning-effort")
    update_shortlist_parser.add_argument("--company-ids", type=int, nargs="+")
    update_shortlist_parser.add_argument("--retry-rejected", action="store_true")
    update_shortlist_parser.set_defaults(func=_cmd_update_shortlist)

    grill_parser = subparsers.add_parser(
        "grill-thesis", help="Challenge an exact stored thesis revision"
    )
    grill_parser.add_argument("--company-id", type=int, required=True)
    grill_parser.add_argument("--question", required=True)
    grill_parser.add_argument("--provider", choices=("openai", "deepseek"), default="openai")
    grill_parser.add_argument("--model")
    grill_parser.add_argument("--reasoning-effort")
    grill_parser.set_defaults(func=_cmd_grill_thesis)

    respond_parser = subparsers.add_parser(
        "respond-to-thesis-challenge", help="Let the analyst respond to an open challenge"
    )
    respond_parser.add_argument("--challenge-id", type=int, required=True)
    respond_parser.add_argument("--provider", choices=("openai", "deepseek"), default="openai")
    respond_parser.add_argument("--model")
    respond_parser.add_argument("--reasoning-effort")
    respond_parser.set_defaults(func=_cmd_respond_to_thesis_challenge)

    resolve_parser = subparsers.add_parser(
        "resolve-thesis-challenge", help="Manually resolve an exceptional case"
    )
    resolve_parser.add_argument("--challenge-id", type=int, required=True)
    resolve_parser.add_argument("--status", choices=("upheld", "revised"), required=True)
    resolve_parser.add_argument("--note", required=True)
    resolve_parser.set_defaults(func=_cmd_resolve_thesis_challenge)

    sync_evidence_parser = subparsers.add_parser(
        "sync-agent-evidence", help="Download and store latest evidence"
    )
    sync_evidence_parser.add_argument("--max-candidates", type=int, default=5)
    sync_evidence_parser.set_defaults(func=_cmd_sync_agent_evidence)

    adjudicate_parser = subparsers.add_parser(
        "adjudicate-monthly-ranking", help="Run the comparative verdict agent"
    )
    adjudicate_parser.add_argument("--ranking-run-id", type=int, required=True)
    adjudicate_parser.add_argument("--provider", choices=("openai", "deepseek"), default="openai")
    adjudicate_parser.add_argument("--model")
    adjudicate_parser.add_argument("--reasoning-effort")
    adjudicate_parser.set_defaults(func=_cmd_adjudicate_monthly_ranking)


def _cmd_export_agent_prompts(args):
    from kncompanyscraper.analysis.agent.prompt_exporter import AgentPromptExporter
    from kncompanyscraper.main import _build_watchlist_analysis_service, _build_agent_cohort_candidates

    run = _build_watchlist_analysis_service().analyze_watchlist()
    candidates = _build_agent_cohort_candidates(run, limit=args.max_candidates)
    paths = AgentPromptExporter().export(candidates, args.output_dir)
    print(f"Exported {len(paths)} agent prompts to {args.output_dir}.")


def _cmd_check_agent_readiness(args):
    from kncompanyscraper.analysis.agent.readiness import AgentReadinessGate
    from kncompanyscraper.main import _build_watchlist_analysis_service, _build_agent_cohort_candidates

    run = _build_watchlist_analysis_service().analyze_watchlist()
    candidates = _build_agent_cohort_candidates(run, limit=args.max_candidates)
    if not candidates:
        print("No companies available in the agent shortlist.")
        return

    gate = AgentReadinessGate()
    blocked = 0
    for candidate in candidates:
        assessment = gate.assess(candidate)
        print(f"{candidate.rank}. {candidate.ticker}: {assessment.status}")
        for blocker in assessment.blockers:
            print(f"  - {blocker.code}: {blocker.message}")
        blocked += int(not assessment.ready)
    print(f"Ready: {len(candidates) - blocked}; blocked: {blocked}.")


def _cmd_analyze_shortlist(args):
    from kncompanyscraper.analysis.agent.agent_analysis_service import (
        AgentAnalysisService,
    )
    from kncompanyscraper.main import (
        _build_agent_model_adapter,
        _build_agent_context_builder,
        _build_watchlist_analysis_service,
    )

    model_adapter = _build_agent_model_adapter(
        args.provider, args.model, args.reasoning_effort
    )
    service = AgentAnalysisService(
        model_adapter,
        _build_agent_context_builder(),
    )

    run = _build_watchlist_analysis_service().analyze_watchlist()
    candidates = _build_agent_context_builder().build_shortlist(
        run,
        run.results_by_company,
        limit=args.max_candidates,
        company_ids=tuple(args.company_ids) if args.company_ids else None,
    )

    if args.retry_rejected:
        result = service.revalidate_rejected(candidates)
    else:
        result = service.analyze(candidates)

    print(f"Analysis complete: {result.succeeded} accepted, {result.failed} rejected.")


def _cmd_update_shortlist(args):
    from kncompanyscraper.analysis.agent.thesis_update_service import (
        ThesisUpdateService,
    )
    from kncompanyscraper.analysis.agent.execution_boundary import (
        AgentExecutionBoundary,
    )
    from kncompanyscraper.repositories.thesis_repository import ThesisRepository
    from kncompanyscraper.repositories.research_document_repository import (
        ResearchDocumentRepository,
    )
    from kncompanyscraper.main import (
        _build_agent_model_adapter,
        _build_agent_context_builder,
        _build_watchlist_analysis_service,
    )

    model_adapter = _build_agent_model_adapter(
        args.provider, args.model, args.reasoning_effort
    )
    boundary = AgentExecutionBoundary(
        ThesisRepository(),
        ResearchDocumentRepository(),
    )
    service = ThesisUpdateService(
        model_adapter,
        _build_agent_context_builder(),
        boundary,
    )

    run = _build_watchlist_analysis_service().analyze_watchlist()
    candidates = _build_agent_context_builder().build_shortlist(
        run,
        run.results_by_company,
        limit=args.max_candidates,
        company_ids=tuple(args.company_ids) if args.company_ids else None,
    )

    if args.retry_rejected:
        result = service.revalidate_rejected(candidates)
    else:
        result = service.update(candidates)

    print(
        f"Updates complete: {result.succeeded} accepted, {result.failed} rejected, {result.skipped} skipped."
    )


def _cmd_grill_thesis(args):
    from kncompanyscraper.analysis.agent.thesis_challenge import ThesisChallengeService
    from kncompanyscraper.repositories.thesis_repository import ThesisRepository
    from kncompanyscraper.main import (
        _build_agent_model_adapter,
        _original_research_evidence,
    )

    thesis_repo = ThesisRepository()
    revision = thesis_repo.get_latest_revision(args.company_id)
    if not revision:
        raise SystemExit(f"No thesis found for company {args.company_id}")

    model_adapter = _build_agent_model_adapter(
        args.provider, args.model, args.reasoning_effort
    )
    service = ThesisChallengeService(model_adapter)

    evidence = _original_research_evidence(args.company_id, revision.evidence_ids)
    challenge = service.criticize(revision, evidence, args.question)

    print(f"Challenge {challenge.id} persisted: {challenge.claim}")


def _cmd_respond_to_thesis_challenge(args):
    from kncompanyscraper.analysis.agent.thesis_challenge import ThesisChallengeService
    from kncompanyscraper.repositories.thesis_challenge_repository import (
        ThesisChallengeRepository,
    )
    from kncompanyscraper.repositories.thesis_repository import ThesisRepository
    from kncompanyscraper.main import (
        _build_agent_model_adapter,
        _original_research_evidence,
    )

    challenge_repo = ThesisChallengeRepository()
    challenge = challenge_repo.get_challenge(args.challenge_id)
    if not challenge:
        raise SystemExit(f"Challenge {args.challenge_id} not found")

    thesis_repo = ThesisRepository()
    revision = thesis_repo.get_revision(challenge.thesis_revision_id)
    evidence = _original_research_evidence(challenge.company_id, revision.evidence_ids)

    model_adapter = _build_agent_model_adapter(
        args.provider, args.model, args.reasoning_effort
    )
    service = ThesisChallengeService(model_adapter)

    outcome = service.respond(challenge, revision, evidence)
    print(f"Response processed: {outcome.status}")


def _cmd_resolve_thesis_challenge(args):
    from kncompanyscraper.repositories.thesis_challenge_repository import (
        ThesisChallengeRepository,
    )

    ThesisChallengeRepository().resolve_challenge(
        args.challenge_id, args.status, args.note
    )
    print(f"Challenge {args.challenge_id} resolved as {args.status}.")


def _cmd_sync_agent_evidence(args):
    from kncompanyscraper.scraper.mfn_scraper import MfnScraper
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.research_document_repository import (
        ResearchDocumentRepository,
    )
    from kncompanyscraper.main import _build_watchlist_analysis_service

    company_repo = CompanyRepository()
    doc_repo = ResearchDocumentRepository()
    scraper = MfnScraper(doc_repo)

    run = _build_watchlist_analysis_service().analyze_watchlist()
    shortlist = run.shortlist_for_agent(max_total=args.max_candidates)

    for cs in shortlist:
        company = company_repo.get_company(cs.company_id)
        if company and company.mfn_id:
            print(f"Syncing evidence for {company.name}...")
            scraper.sync_company(company)


def _cmd_adjudicate_monthly_ranking(args):
    from kncompanyscraper.analysis.agent.comparative_review import (
        ComparativeReviewService,
    )
    from kncompanyscraper.repositories.ranking_repository import RankingRepository
    from kncompanyscraper.repositories.thesis_repository import ThesisRepository
    from kncompanyscraper.repositories.comparative_review_repository import (
        ComparativeReviewRepository,
    )
    from kncompanyscraper.main import _build_agent_model_adapter

    ranking_repo = RankingRepository()
    run = ranking_repo.get_ranking_run(args.ranking_run_id)
    if not run:
        raise SystemExit(f"Ranking run {args.ranking_run_id} not found")

    latest_theses = ThesisRepository().get_latest_accepted_theses()
    model_adapter = _build_agent_model_adapter(
        args.provider, args.model, args.reasoning_effort
    )
    service = ComparativeReviewService(model_adapter, ComparativeReviewRepository())

    result = service.adjudicate(run, latest_theses)
    print(
        f"Adjudication complete for run {args.ranking_run_id}: {len(result.calibrations)} companies calibrated."
    )
