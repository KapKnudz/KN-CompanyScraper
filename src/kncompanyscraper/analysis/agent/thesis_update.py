from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from kncompanyscraper.analysis.agent.context_provenance import (
    deterministic_context_sha256,
)
from kncompanyscraper.analysis.agent.output_schema import (
    THESIS_UPDATE_OUTPUT_CONTRACT,
    thesis_update_json_schema,
)
from kncompanyscraper.analysis.agent.prompt_builder import AgentPrompt, AgentPromptBuilder


@dataclass(frozen=True)
class ThesisUpdateContext:
    candidate: object
    current_thesis: dict
    current_facts: list[dict]
    prior_source_ids: tuple[str, ...]
    new_source_ids: tuple[str, ...]
    deterministic_context_sha256: str
    deterministic_context_changed: bool

    @property
    def has_changes(self) -> bool:
        return bool(self.new_source_ids) or self.deterministic_context_changed


class ThesisUpdateContextBuilder:
    def __init__(self, thesis_repository):
        self.thesis_repository = thesis_repository

    def build(self, candidate) -> ThesisUpdateContext | None:
        current_thesis = self.thesis_repository.get_latest(candidate.company_id)
        if current_thesis is None:
            return None

        current_facts = self.thesis_repository.list_latest_facts(candidate.company_id)
        prior_source_ids = self._prior_source_ids(current_thesis, current_facts)
        evidence = dict(candidate.research_evidence)
        documents = [
            item
            for item in evidence.get("documents", [])
            if item["source_id"] not in prior_source_ids
        ]
        insider_transactions = [
            item
            for item in evidence.get("insider_transactions", [])
            if item["source_id"] not in prior_source_ids
        ]
        new_source_ids = tuple(
            item["source_id"] for item in [*documents, *insider_transactions]
        )
        prior_document_source_ids = sorted(
            source_id
            for source_id in prior_source_ids
            if source_id.startswith(("document:", "news:"))
        )
        prior_insider_source_ids = sorted(
            source_id for source_id in prior_source_ids if source_id.startswith("insider:")
        )
        evidence.update(
            {
                "documents": documents,
                "insider_transactions": insider_transactions,
                "insider_status": "available" if insider_transactions else "unavailable",
                "insider_event_count": len(insider_transactions),
                "prior_source_ids": sorted(prior_source_ids),
                "prior_document_source_ids": prior_document_source_ids,
                "prior_insider_source_ids": prior_insider_source_ids,
            }
        )
        incremental_candidate = replace(candidate, research_evidence=evidence)
        context_hash = deterministic_context_sha256(candidate)
        previous_hash = (current_thesis.get("metadata") or {}).get(
            "deterministic_context_sha256"
        )
        return ThesisUpdateContext(
            candidate=incremental_candidate,
            current_thesis=current_thesis,
            current_facts=current_facts,
            prior_source_ids=tuple(sorted(prior_source_ids)),
            new_source_ids=new_source_ids,
            deterministic_context_sha256=context_hash,
            deterministic_context_changed=context_hash != previous_hash,
        )

    @classmethod
    def _prior_source_ids(cls, thesis: dict, facts: list[dict]) -> set[str]:
        source_ids = set((thesis.get("metadata") or {}).get("evidence_source_ids") or [])
        for fact in facts:
            source_ids.update(fact.get("source_ids") or [])
        content = thesis.get("content") or {}
        source_ids.update(
            citation.get("source_id")
            for citation in content.get("citations", [])
            if citation.get("source_id")
        )
        source_ids.update(content.get("risk_profile_evidence") or [])
        for claim in content.get("management_credibility_ledger", []):
            source_ids.update(claim.get("source_ids") or [])
        for entries in (content.get("company_fact_ledger") or {}).values():
            for fact in entries:
                source_ids.update(fact.get("source_ids") or [])
        profile = content.get("business_model_profile") or {}
        source_ids.update(profile.get("source_ids") or [])
        margin = content.get("margin_expansion_case") or {}
        source_ids.update(margin.get("source_ids") or [])
        source_ids.update(margin.get("contrary_source_ids") or [])
        timing = content.get("timing_assessment") or {}
        source_ids.update(timing.get("source_ids") or [])
        for catalyst in timing.get("catalysts") or []:
            source_ids.update(catalyst.get("source_ids") or [])
        return source_ids


class ThesisUpdatePromptBuilder:
    POLICY_NAME = "nordic-thesis-update-policy"
    POLICY_VERSION = "1.1.0-thesis-card"

    def build(self, context: ThesisUpdateContext) -> AgentPrompt:
        policy = AgentPromptBuilder._read_resource("resources/analyst_policy.md")
        workflow = AgentPromptBuilder._read_resource("resources/analysis_workflow.md")
        incremental_workflow = AgentPromptBuilder._read_resource(
            "resources/incremental_analysis_workflow.md"
        )
        template = AgentPromptBuilder._read_resource("prompts/thesis_update_prompt.md")
        system = f"{policy}\n\n{workflow}\n\n{incremental_workflow}"
        policy_sha256 = sha256(system.encode("utf-8")).hexdigest()
        user = template.format(
            current_thesis_json=json.dumps(
                context.current_thesis,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            current_facts_json=json.dumps(
                context.current_facts,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            candidate_json=json.dumps(
                asdict(context.candidate),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            output_contract=json.dumps(
                THESIS_UPDATE_OUTPUT_CONTRACT,
                ensure_ascii=False,
                indent=2,
            ),
        )
        return AgentPrompt(
            system=system,
            user=user,
            policy_name=self.POLICY_NAME,
            policy_version=self.POLICY_VERSION,
            policy_sha256=policy_sha256,
            output_schema=thesis_update_json_schema(),
            schema_name="thesis_update",
        )
