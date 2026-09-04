from pathlib import Path

MODEL_PROVIDERS = ("local", "openai", "deepseek")


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
    analyze_shortlist_parser.add_argument("--provider", choices=MODEL_PROVIDERS, default="local")
    analyze_shortlist_parser.add_argument("--model")
    analyze_shortlist_parser.add_argument("--reasoning-effort")
    analyze_shortlist_parser.add_argument("--company-ids", type=int, nargs="+")
    analyze_shortlist_parser.add_argument("--retry-rejected", action="store_true")
    analyze_shortlist_parser.add_argument("--repair-rejected", action="store_true")
    analyze_shortlist_parser.set_defaults(func=_cmd_analyze_shortlist)

    analyze_company_parser = subparsers.add_parser(
        "analyze-company", help="Refresh and fully analyze active watchlist companies"
    )
    selector_group = analyze_company_parser.add_mutually_exclusive_group(required=True)
    selector_group.add_argument("--company-ids", type=int, nargs="+")
    selector_group.add_argument("--tickers", nargs="+")
    selector_group.add_argument("--resume-job-id", type=int)
    analyze_company_parser.add_argument("--provider", choices=MODEL_PROVIDERS)
    analyze_company_parser.add_argument("--model")
    analyze_company_parser.add_argument("--reasoning-effort")
    analyze_company_parser.set_defaults(func=_cmd_analyze_company)

    update_shortlist_parser = subparsers.add_parser(
        "update-shortlist", help="Incremental thesis updates for existing analysts"
    )
    update_shortlist_parser.add_argument("--max-candidates", type=int, default=5)
    update_shortlist_parser.add_argument("--provider", choices=MODEL_PROVIDERS, default="local")
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
    grill_parser.add_argument("--provider", choices=MODEL_PROVIDERS, default="local")
    grill_parser.add_argument("--model")
    grill_parser.add_argument("--reasoning-effort")
    grill_parser.set_defaults(func=_cmd_grill_thesis)

    respond_parser = subparsers.add_parser(
        "respond-to-thesis-challenge", help="Let the analyst respond to an open challenge"
    )
    respond_parser.add_argument("--challenge-id", type=int, required=True)
    respond_parser.add_argument("--provider", choices=MODEL_PROVIDERS, default="local")
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

    repair_evidence_parser = subparsers.add_parser(
        "repair-agent-report",
        help="Ingest one authoritative report and backfill stored report metadata",
    )
    repair_evidence_parser.add_argument("--company-id", type=int, required=True)
    repair_evidence_parser.add_argument("--title", required=True)
    repair_evidence_parser.add_argument("--url", required=True)
    repair_evidence_parser.add_argument("--published-at", required=True)
    repair_evidence_parser.add_argument("--source-release-url")
    repair_evidence_parser.add_argument(
        "--document-type",
        choices=("annual_report", "interim_report"),
    )
    repair_evidence_parser.set_defaults(func=_cmd_repair_agent_report)

    adjudicate_parser = subparsers.add_parser(
        "adjudicate-monthly-ranking", help="Run the comparative verdict agent"
    )
    adjudicate_parser.add_argument("--ranking-run-id", type=int, required=True)
    adjudicate_parser.add_argument("--provider", choices=MODEL_PROVIDERS, default="local")
    adjudicate_parser.add_argument("--model")
    adjudicate_parser.add_argument("--reasoning-effort")
    adjudicate_parser.set_defaults(func=_cmd_adjudicate_monthly_ranking)

    calibration_parser = subparsers.add_parser(
        "audit-thesis-calibration",
        help="Report diagnostic confidence and verdict calibration across theses",
    )
    calibration_parser.add_argument("--output", required=True, type=Path)
    calibration_parser.set_defaults(func=_cmd_audit_thesis_calibration)

    contract_coverage_parser = subparsers.add_parser(
        "audit-thesis-contract-coverage",
        help="Measure thesis-contract coverage across validated theses",
    )
    contract_coverage_parser.add_argument("--output", required=True, type=Path)
    contract_coverage_parser.set_defaults(func=_cmd_audit_thesis_contract_coverage)


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
        if as_stored_analysis(analysis).is_enriched_forward_scenario
    }
    args.output.write_text(
        json.dumps(summaries, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Exported {len(summaries)} validated v2 thesis summaries to {args.output}.")


def _cmd_audit_thesis_calibration(args):
    import json

    from kncompanyscraper.analysis.agent.thesis_cohort_calibration import (
        build_cohort_calibration_audit,
    )
    from kncompanyscraper.repositories.analysis_repository import AnalysisRepository

    repository = AnalysisRepository()
    audit = build_cohort_calibration_audit(
        repository.get_latest_validated_stock_analyses(),
        repository.get_validated_stock_analysis_revisions(),
    )
    args.output.write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"Exported diagnostic thesis calibration audit for {audit['company_count']} "
        f"companies to {args.output} ({audit['review_result']})."
    )
    for flag in audit["flags"]:
        print(f"  - {flag['type']}: {flag['message']}")


def _cmd_audit_thesis_contract_coverage(args):
    import json

    from kncompanyscraper.analysis.agent.thesis_contract_coverage import (
        build_falsifiable_case_coverage,
    )
    from kncompanyscraper.repositories.analysis_repository import AnalysisRepository

    analyses = AnalysisRepository().get_latest_validated_stock_analyses()
    audit = build_falsifiable_case_coverage(analyses)
    args.output.write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    rate = audit["coverage_rate"]
    rate_text = f"{rate:.1%}" if rate is not None else "n/a"
    print(
        f"Measured thesis-contract coverage for {audit['company_count']} companies: "
        f"{audit['complete_count']} complete ({rate_text})."
    )


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
    from kncompanyscraper.composition import (
        build_agent_context_builder,
        build_agent_analysis_service,
        build_agent_model_adapter,
        build_watchlist_analysis_service,
    )

    model_adapter = build_agent_model_adapter(
        args.provider, args.model, args.reasoning_effort
    )
    service = build_agent_analysis_service(model_adapter)

    run = build_watchlist_analysis_service().analyze_watchlist()
    candidates = build_agent_context_builder().build_shortlist(
        run.ranking,
        run.results_by_company,
        limit=args.max_candidates,
        company_ids=tuple(args.company_ids) if args.company_ids else None,
    )

    if args.retry_rejected and args.repair_rejected:
        raise SystemExit("Choose either --retry-rejected or --repair-rejected, not both")
    if args.retry_rejected:
        result = service.revalidate_rejected(candidates)
    elif args.repair_rejected:
        result = service.repair_rejected(candidates)
    else:
        result = service.analyze(candidates)

    print(f"Analysis complete: {len(result)} accepted.")


def _cmd_analyze_company(args):
    from kncompanyscraper.composition import (
        build_agent_model_adapter,
        build_company_analysis_pipeline,
    )
    from kncompanyscraper.repositories.job_repository import JobRepository

    if args.resume_job_id is not None:
        if any(value is not None for value in (args.provider, args.model, args.reasoning_effort)):
            raise SystemExit("Provider, model, and reasoning overrides are not allowed when resuming")
        job = JobRepository().get(args.resume_job_id)
        if job is None:
            raise SystemExit(f"Company analysis job {args.resume_job_id} not found")
        job_result = job.get("result", {})
        if job.get("status") == "success" or job_result.get("final_analysis_id"):
            adapter = None
        else:
            settings = job_result.get("settings", {})
            adapter = build_agent_model_adapter(
                settings.get("provider", "local"),
                settings.get("model"),
                settings.get("reasoning_effort"),
            )
        pipeline = build_company_analysis_pipeline(adapter)
        try:
            outcomes = (pipeline.resume(args.resume_job_id),)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    else:
        provider = args.provider or "local"
        adapter = build_agent_model_adapter(provider, args.model, args.reasoning_effort)
        pipeline = build_company_analysis_pipeline(adapter)
        companies = pipeline.resolve_companies(
            company_ids=args.company_ids,
            tickers=args.tickers,
        )
        outcomes = pipeline.run(
            companies,
            settings={
                "provider": provider,
                "model": getattr(adapter, "model", args.model),
                "reasoning_effort": getattr(
                    adapter, "reasoning_effort", args.reasoning_effort
                ),
            },
            invocation={
                "company_ids": args.company_ids,
                "tickers": args.tickers,
            },
        )

    _print_company_analysis_summary(outcomes)


def _print_company_analysis_summary(outcomes):
    from collections import Counter

    for outcome in outcomes:
        print(f"{outcome.ticker}: {outcome.status} (job {outcome.job_id})")
        if outcome.status == "resumable":
            print(f"  Resume: {outcome.resume_command}")
    counts = Counter(outcome.status for outcome in outcomes)
    print(
        "Summary: "
        + ", ".join(
            f"{status}={counts.get(status, 0)}"
            for status in (
                "accepted",
                "blocked-before-model",
                "failed",
                "resumable",
                "already-completed",
            )
        )
    )


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
    from kncompanyscraper.analysis.agent.scenario_authoring import (
        ScenarioAuthoringService,
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
        ThesisUpdateExecutionBoundary(
            AgentExecutionBoundary(
                analysis_repository,
                require_mandatory_scenarios=True,
            ),
            scenario_authoring_service=ScenarioAuthoringService(
                model_adapter,
                raw_response_repository=analysis_repository,
            ),
        ),
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
    shortlist = run.ranking.shortlist_for_agent(
        top_n=args.max_candidates, max_total=args.max_candidates
    )

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
                f"{result.documents_added} report PDFs added, "
                f"{getattr(result, 'documents_updated', 0)} metadata records updated"
            )


def _cmd_repair_agent_report(args):
    from datetime import datetime

    from kncompanyscraper.analysis.agent.research_document_ingestion import (
        ResearchDocumentIngestionService,
    )
    from kncompanyscraper.repositories.company_repository import CompanyRepository
    from kncompanyscraper.repositories.news_repository import NewsRepository
    from kncompanyscraper.repositories.research_document_repository import (
        ResearchDocumentRepository,
    )

    company = CompanyRepository().get_by_id(args.company_id)
    if company is None:
        raise SystemExit(f"Company {args.company_id} not found")
    try:
        published_at = datetime.fromisoformat(args.published_at)
    except ValueError as exc:
        raise SystemExit("--published-at must be an ISO-8601 date or timestamp") from exc

    ingestion = ResearchDocumentIngestionService(
        NewsRepository(), ResearchDocumentRepository()
    )
    inserted = ingestion.ingest_authoritative_report(
        company,
        title=args.title,
        url=args.url,
        published_at=published_at,
        source_release_url=args.source_release_url,
        document_type=args.document_type,
    )
    updated = ingestion.backfill_report_metadata(company)
    action = "added" if inserted else "already stored"
    print(
        f"Authoritative report {action}; "
        f"{updated} stored metadata records updated."
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
