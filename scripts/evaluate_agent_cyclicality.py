import argparse
from datetime import date
import json
from pathlib import Path

from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.cyclicality_evaluation import (
    CONSENSUS_POLICY_VERSION,
    CyclicalityEvaluator,
    build_cyclicality_consensus,
    summarize_cyclicality_runs,
)
from kncompanyscraper.analysis.agent.deepseek_chat import DeepSeekChatAdapter
from kncompanyscraper.analysis.agent.research_evidence import ResearchEvidenceBuilder
from kncompanyscraper.analysis.agent.research_document_ingestion import (
    ResearchDocumentIngestionService,
)
from kncompanyscraper.repositories.company_repository import CompanyRepository
from kncompanyscraper.repositories.insider_repository import InsiderRepository
from kncompanyscraper.repositories.news_repository import NewsRepository
from kncompanyscraper.repositories.research_document_repository import (
    ResearchDocumentRepository,
)
from kncompanyscraper.repositories.valuation_repository import ValuationRepository


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--companies", nargs="+", required=True, help="Ticker or exact company name")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--model")
    parser.add_argument("--reasoning-effort", default="high")
    parser.add_argument("--max-output-tokens", type=int, default=16000)
    parser.add_argument("--skip-controls", action="store_true")
    parser.add_argument("--controls-only", action="store_true")
    parser.add_argument(
        "--persist-consensus",
        action="store_true",
        help="Persist completed three-run consensus for later stock analyses",
    )
    parser.add_argument(
        "--sync-evidence",
        action="store_true",
        help="Fetch MFN releases and report attachments for the selected companies first",
    )
    parser.add_argument(
        "--sync-only",
        action="store_true",
        help="Stop after syncing evidence without calling the model",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.skip_controls and args.controls_only:
        parser.error("--skip-controls and --controls-only cannot be combined")
    if args.sync_only:
        args.sync_evidence = True
    if not args.sync_only and args.output is None:
        parser.error("--output is required unless --sync-only is used")

    companies = CompanyRepository().get_active_companies()
    lookup = {
        key.casefold(): company
        for company in companies
        for key in (company.ticker, company.name)
    }
    missing = [name for name in args.companies if name.casefold() not in lookup]
    if missing:
        raise SystemExit("Unknown active companies: " + ", ".join(missing))

    selected_companies = [lookup[name.casefold()] for name in args.companies]
    if args.sync_evidence:
        ingestion = ResearchDocumentIngestionService(
            NewsRepository(),
            ResearchDocumentRepository(),
        )
        for company in selected_companies:
            result = ingestion.sync_company(company)
            print(
                f"{company.name}: {result.releases_added} releases, "
                f"{result.documents_added} report PDFs added"
            )
        if args.sync_only:
            return

    evidence_builder = ResearchEvidenceBuilder(
        ResearchDocumentRepository(),
        NewsRepository(),
        InsiderRepository(),
        ValuationRepository(),
    )
    candidates = []
    for company in selected_companies:
        evidence = evidence_builder.build(company.id, as_of=date.today()).to_dict()
        candidates.append(
            AgentCandidate(
                rank=0,
                company_id=company.id,
                ticker=company.ticker,
                name=company.name,
                research_evidence=evidence,
            )
        )

    evaluator = CyclicalityEvaluator(
        DeepSeekChatAdapter(
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            max_output_tokens=args.max_output_tokens,
        )
    )
    runs = [] if args.controls_only else evaluator.evaluate(candidates, args.runs)
    controls = [] if args.skip_controls else evaluator.negative_controls(candidates)
    policy = evaluator.prompt_builder.build(candidates[0])
    report = {
        "as_of": date.today().isoformat(),
        "classifier_policy": {
            "name": policy.policy_name,
            "version": policy.policy_version,
        },
        "consensus_policy_version": CONSENSUS_POLICY_VERSION,
        "sample": [
            {
                "company_id": candidate.company_id,
                "ticker": candidate.ticker,
                "company_name": candidate.name,
                "document_count": len(candidate.research_evidence.get("documents", [])),
            }
            for candidate in candidates
        ],
        "summary": summarize_cyclicality_runs(runs),
        "consensus": build_cyclicality_consensus(runs),
        "negative_control_pass_rate": (
            sum(
                run.classification is not None
                and run.classification.risk_profile == "slightly_cyclical"
                and all(
                    dimension.assessment == "unclassified"
                    for dimension in run.classification.dimensions.values()
                )
                for run in controls
            )
            / len(controls)
            if controls
            else None
        ),
        "runs": [run.to_dict() for run in runs],
        "negative_controls": [run.to_dict() for run in controls],
    }
    if args.persist_consensus:
        from kncompanyscraper.repositories.cyclicality_repository import (
            CyclicalityRepository,
        )

        repository = CyclicalityRepository()
        for consensus in report["consensus"]:
            if consensus["status"] != "complete":
                continue
            repository.save_consensus(
                consensus["company_id"],
                consensus,
                classifier_policy_version=policy.policy_version,
                consensus_policy_version=CONSENSUS_POLICY_VERSION,
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    if report["negative_control_pass_rate"] is not None:
        print(f"Negative-control pass rate: {report['negative_control_pass_rate']:.1%}")
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
