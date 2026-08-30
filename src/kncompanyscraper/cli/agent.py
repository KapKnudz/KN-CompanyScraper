from pathlib import Path
def register(subparsers):
    export_prompts_parser = subparsers.add_parser(
        "export-agent-prompts", help="Export model-ready prompts for deterministic shortlist"
    )
    export_prompts_parser.add_argument("--output-dir", required=True, type=Path)
    export_prompts_parser.add_argument("--max-candidates", type=int, default=5)
    export_prompts_parser.set_defaults(func=_cmd_export_agent_prompts)

    export_thesis_parser = subparsers.add_parser(
        "export-thesis-summaries",
        help="Export validated v2 thesis summaries as JSON",
    )
    export_thesis_parser.add_argument("--output", required=True, type=Path)
    export_thesis_parser.set_defaults(func=_cmd_export_thesis_summaries)

    check_readiness_parser = subparsers.add_parser(
        "check-agent-readiness", help="Report deterministic blockers and limitations"
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
    from kncompanyscraper.composition import (
        build_agent_cohort_candidates,
        build_watchlist_analysis_service,
    )

    run = build_watchlist_analysis_service().analyze_watchlist()
    candidates = build_agent_cohort_candidates(run, limit=args.max_candidates)
    paths = AgentPromptExporter().export(candidates, args.output_dir)
    print(f"Exported {len(paths)} agent prompts to {args.output_dir}.")


def _cmd_export_thesis_summaries(args):
    import json

    from kncompanyscraper.models.stored_analysis import as_stored_analysis
    from kncompanyscraper.repositories.analysis_repository import AnalysisRepository

    analyses = AnalysisRepository().get_latest_validated_stock_analyses()
    summaries = {
        str(company_id): as_stored_analysis(analysis).thesis_summary
        for company_id, analysis in sorted(analyses.items())
        if as_stored_analysis(analysis).is_current_forward_scenario
    }
    args.output.write_text(
        json.dumps(summaries, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Exported {len(summaries)} validated v2 thesis summaries to {args.output}.")


def _cmd_check_agent_readiness(args):
    from kncompanyscraper.analysis.agent.readiness import AgentReadinessGate
    from kncompanyscraper.composition import (
        build_agent_cohort_candidates,
        build_watchlist_analysis_service,
    )

    run = build_watchlist_analysis_service().analyze_watchlist()
    candidates = build_agent_cohort_candidates(run, limit=args.max_candidates)
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
        for limitation in assessment.limitations:
            print(f"  - limitation {limitation.code}: {limitation.message}")
        blocked += int(not assessment.ready)
    print(f"Ready: {len(candidates) - blocked}; blocked: {blocked}.")


def _cmd_analyze_shortlist(args):
    from kncompanyscraper.analysis.agent.agent_analysis_service import (
        AgentAnalysisService,
    )
    from kncompanyscraper.composition import (
        build_agent_context_builder,
        build_agent_model_adapter,
        build_watchlist_analysis_service,
    )
    from kncompanyscraper.analysis.agent.execution_boundary import AgentExecutionBoundary
    from kncompanyscraper.repositories.analysis_repository import AnalysisRepository

    model_adapter = build_agent_model_adapter(
        args.provider, args.model, args.reasoning_effort
    )
    service = AgentAnalysisService(
        model_adapter,
        AgentExecutionBoundary(AnalysisRepository()),
        raw_response_repository=AnalysisRepository(),
    )

    run = build_watchlist_analysis_service().analyze_watchlist()
    candidates = build_agent_context_builder().build_shortlist(
        run.ranking,
        run.results_by_company,
        limit=args.max_candidates,
        company_ids=tuple(args.company_ids) if args.company_ids else None,
    )

    if args.retry_rejected:
        result = service.revalidate_rejected(candidates)
    else:
        result = service.analyze(candidates)

    print(f"Analysis complete: {len(result)} accepted.")


def _cmd_update_shortlist(args):
    from kncompanyscraper.composition import (
        build_agent_context_builder,
        build_agent_model_adapter,
        build_thesis_update_service,
        build_watchlist_analysis_service,
    )

    model_adapter = build_agent_model_adapter(
        args.provider, args.model, args.reasoning_effort
    )
    service = build_thesis_update_service(model_adapter)

    run = build_watchlist_analysis_service().analyze_watchlist()
    candidates = build_agent_context_builder().build_shortlist(
        run.ranking,
        run.results_by_company,
        limit=args.max_candidates,
        company_ids=tuple(args.company_ids) if args.company_ids else None,
    )

    if args.retry_rejected:
        result = service.revalidate_rejected(candidates)
    else:
        result = service.update(candidates)

    print(
        f"Updates complete: {sum(item.status == 'persisted' for item in result)} accepted, "
        f"{sum(item.status == 'full_reassessment_required' for item in result)} require full reassessment, "
        f"{sum(item.status in {'no_current_thesis', 'no_new_evidence'} for item in result)} skipped."
    )


def _cmd_grill_thesis(args):
    from kncompanyscraper.analysis.agent.thesis_challenge import ThesisChallengeService
    from kncompanyscraper.repositories.thesis_challenge_repository import (
        ThesisChallengeRepository,
    )
    from kncompanyscraper.composition import (
        build_agent_model_adapter,
        build_original_research_evidence,
    )

    thesis_repo = ThesisRepository()
    revision = thesis_repo.get_latest(args.company_id)
    if not revision:
        raise SystemExit(f"No thesis found for company {args.company_id}")

    model_adapter = build_agent_model_adapter(
        args.provider, args.model, args.reasoning_effort
    )
    service = ThesisChallengeService(model_adapter, ThesisChallengeRepository())

    evidence = build_original_research_evidence(
        args.company_id,
        set((revision.get("metadata") or {}).get("evidence_source_ids") or []),
    )
    challenge_id, result = service.challenge(revision, evidence, args.question)

    print(f"Challenge {challenge_id} persisted: {result.challenged_claim}")


def _cmd_respond_to_thesis_challenge(args):
    from kncompanyscraper.analysis.agent.execution_boundary import AgentExecutionBoundary
    from kncompanyscraper.analysis.agent.thesis_challenge import (
        ThesisChallengeResponseService,
    )
    from kncompanyscraper.analysis.agent.thesis_update_service import (
        ThesisUpdateExecutionBoundary,
    )
    from kncompanyscraper.repositories.analysis_repository import AnalysisRepository
    from kncompanyscraper.repositories.thesis_challenge_repository import (
        ThesisChallengeRepository,
    )
    from kncompanyscraper.repositories.thesis_repository import ThesisRepository
    challenge_repo = ThesisChallengeRepository()
    challenge = challenge_repo.get(args.challenge_id)
    if not challenge:
        raise SystemExit(f"Challenge {args.challenge_id} not found")

    thesis_repo = ThesisRepository()
    revision_id = challenge["thesis_revision_id"]
    revision = thesis_repo.get_revision(revision_id)
    if not revision:
        raise SystemExit(
            f"Thesis revision {revision_id} for challenge "
            f"{args.challenge_id} not found"
        )
    from kncompanyscraper.composition import (
        build_agent_context_builder,
        build_agent_model_adapter,
        build_original_research_evidence,
        build_watchlist_analysis_service,
    )

    run = build_watchlist_analysis_service().analyze_watchlist()
    candidates = build_agent_context_builder().build_shortlist(
        run.ranking,
        run.results_by_company,
        company_ids=(challenge["company_id"],),
        limit=1,
    )
    if not candidates:
        raise SystemExit(f"Company {challenge['company_id']} is not in the current ranking")
    candidate = candidates[0]
    evidence = build_original_research_evidence(
        challenge["company_id"],
        set((revision.get("metadata") or {}).get("evidence_source_ids") or []),
    )

    model_adapter = build_agent_model_adapter(
        args.provider, args.model, args.reasoning_effort
    )
    analysis_repository = AnalysisRepository()
    service = ThesisChallengeResponseService(
        model_adapter,
        ThesisUpdateExecutionBoundary(AgentExecutionBoundary(analysis_repository)),
        challenge_repo,
        analysis_repository,
    )

    outcome = service.respond(
        challenge,
        revision,
        candidate,
        evidence,
        thesis_repo.list_latest_facts(challenge["company_id"]),
    )
    print(f"Response processed: {outcome.status}")


def _cmd_resolve_thesis_challenge(args):
    from kncompanyscraper.repositories.thesis_challenge_repository import (
        ThesisChallengeRepository,
    )

    ThesisChallengeRepository().resolve(
        args.challenge_id, args.status, args.note
    )
    print(f"Challenge {args.challenge_id} resolved as {args.status}.")


def _cmd_sync_agent_evidence(args):
    from kncompanyscraper.analysis.agent.research_document_ingestion import (
        ResearchDocumentIngestionService,
    )
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.news_repository import NewsRepository
    from kncompanyscraper.repositories.research_document_repository import (
        ResearchDocumentRepository,
    )
    from kncompanyscraper.composition import build_watchlist_analysis_service

    company_repo = CompanyRepository()
    ingestion = ResearchDocumentIngestionService(
        NewsRepository(), ResearchDocumentRepository()
    )

    run = build_watchlist_analysis_service().analyze_watchlist()
    shortlist = run.shortlist_for_agent(max_total=args.max_candidates)

    for cs in shortlist:
        company = company_repo.get_by_id(cs.company_id)
        if company:
            print(f"Syncing evidence for {company.name}...")
            try:
                result = ingestion.sync_company(company)
            except Exception as exc:
                print(f"  failed: {exc}")
                continue
            print(
                f"  {result.releases_added} releases, "
                f"{result.documents_added} report PDFs added"
            )


def _cmd_adjudicate_monthly_ranking(args):
    from kncompanyscraper.repositories.ranking_repository import RankingRepository
    from kncompanyscraper.repositories.analysis_repository import AnalysisRepository
    from kncompanyscraper.composition import (
        build_agent_model_adapter,
        build_comparative_review_service,
    )

    ranking_repo = RankingRepository()
    run = ranking_repo.get_ranking_run(args.ranking_run_id)
    if not run:
        raise SystemExit(f"Ranking run {args.ranking_run_id} not found")

    analyses = AnalysisRepository().get_latest_validated_stock_analyses()
    model_adapter = build_agent_model_adapter(
        args.provider, args.model, args.reasoning_effort
    )
    service = build_comparative_review_service(model_adapter)

    result = service.review(run, analyses)
    print(
        f"Adjudication complete for run {args.ranking_run_id}: "
        f"{len(result.review.cases)} companies calibrated."
    )
