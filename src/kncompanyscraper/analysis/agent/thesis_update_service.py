from dataclasses import dataclass
import json

from kncompanyscraper.analysis.agent.result_parser import (
    StockAnalysisValidationError,
    parse_stock_analysis_result,
    parse_thesis_update_result,
)
from kncompanyscraper.analysis.agent.thesis_update import ThesisUpdatePromptBuilder


@dataclass(frozen=True)
class PersistedThesisUpdate:
    update: object
    persisted_analysis: object | None


@dataclass(frozen=True)
class ThesisUpdateOutcome:
    company_id: int
    status: str
    impact: str | None = None
    analysis_id: int | None = None


class ThesisUpdateExecutionBoundary:
    VALIDATION_VERSION = "thesis-update-boundary-v1"

    def __init__(self, stock_analysis_boundary):
        self.stock_analysis_boundary = stock_analysis_boundary

    def persist_response(self, raw_response, context, created_by, metadata=None):
        update = parse_thesis_update_result(raw_response)
        if update.thesis.company_id != context.candidate.company_id:
            raise StockAnalysisValidationError(
                "updated thesis company_id does not match the candidate"
            )
        if not update.summary.strip():
            raise StockAnalysisValidationError("thesis update summary cannot be empty")
        if update.impact == "no_material_change" and update.changed_sections:
            raise StockAnalysisValidationError(
                "no_material_change cannot contain changed sections"
            )
        if update.impact == "no_material_change":
            current_content = dict(context.current_thesis.get("content") or {})
            current_content.setdefault("confidence_limitations", [])
            current_content.setdefault(
                "company_fact_ledger",
                {
                    "business_model": [],
                    "revenue_drivers": [],
                    "margins_and_operating_leverage": [],
                    "balance_sheet_and_capital_allocation": [],
                    "management_and_execution": [],
                    "ownership_and_insiders": [],
                    "valuation_expectations": [],
                    "risks_and_disconfirming_evidence": [],
                },
            )
            updated_content = update.thesis.to_dict()
            if (
                updated_content.get("company_fact_ledger")
                != current_content.get("company_fact_ledger")
            ):
                updated_content["company_fact_ledger"] = current_content[
                    "company_fact_ledger"
                ]
                update.thesis = parse_stock_analysis_result(
                    json.dumps(updated_content, ensure_ascii=False)
                )
            if updated_content != current_content:
                changed_fields = sorted(
                    key
                    for key in set(current_content) | set(updated_content)
                    if current_content.get(key) != updated_content.get(key)
                )
                raise StockAnalysisValidationError(
                    "no_material_change must preserve the current thesis; changed fields: "
                    + ", ".join(changed_fields)
                )
        if update.impact not in {
            "no_material_change",
            "full_reassessment_required",
        } and not update.changed_sections:
            raise StockAnalysisValidationError(
                "material thesis updates must identify changed sections"
            )

        if update.impact == "full_reassessment_required":
            return PersistedThesisUpdate(update=update, persisted_analysis=None)

        validation_metadata = dict(metadata or {})
        validation_metadata.update(
            {
                "thesis_update_validation_version": self.VALIDATION_VERSION,
                "thesis_revision_type": "incremental_update",
                "thesis_update_impact": update.impact,
                "thesis_update_summary": update.summary.strip(),
                "thesis_update_changed_sections": update.changed_sections,
            }
        )
        persisted = self.stock_analysis_boundary.persist_response(
            json.dumps(update.thesis.to_dict(), ensure_ascii=False),
            context.candidate,
            created_by=created_by,
            metadata=validation_metadata,
        )
        return PersistedThesisUpdate(update=update, persisted_analysis=persisted)


class ThesisUpdateService:
    def __init__(
        self,
        model_adapter,
        context_builder,
        execution_boundary,
        prompt_builder=None,
        raw_response_repository=None,
    ):
        self.model_adapter = model_adapter
        self.context_builder = context_builder
        self.execution_boundary = execution_boundary
        self.prompt_builder = prompt_builder or ThesisUpdatePromptBuilder()
        self.raw_response_repository = raw_response_repository

    def update(self, candidates: list) -> list[ThesisUpdateOutcome]:
        outcomes = []
        for candidate in candidates:
            context = self.context_builder.build(candidate)
            if context is None:
                outcomes.append(ThesisUpdateOutcome(candidate.company_id, "no_current_thesis"))
                continue
            if not context.has_changes:
                outcomes.append(ThesisUpdateOutcome(candidate.company_id, "no_new_evidence"))
                continue

            prompt = self.prompt_builder.build(context)
            response = self.model_adapter.generate(prompt)
            cumulative_source_ids = list(
                dict.fromkeys([*context.prior_source_ids, *context.new_source_ids])
            )
            metadata = {
                "model_response_id": response.response_id,
                "usage": response.usage,
                "policy_name": prompt.policy_name,
                "policy_version": prompt.policy_version,
                "policy_sha256": prompt.policy_sha256,
                "candidate_rank": candidate.rank,
                "evidence_as_of": candidate.research_evidence.get("as_of"),
                "evidence_source_ids": cumulative_source_ids,
                "new_evidence_source_ids": list(context.new_source_ids),
                "prior_thesis_revision_id": context.current_thesis["id"],
                "deterministic_context_sha256": context.deterministic_context_sha256,
            }
            raw_analysis_id = None
            if self.raw_response_repository is not None:
                raw_analysis_id = self.raw_response_repository.save_stock_analysis_raw(
                    candidate.company_id,
                    response.output_text,
                    created_by=response.model,
                    metadata={"analysis_mode": "incremental_update", **metadata},
                )
                metadata["raw_analysis_id"] = raw_analysis_id
            try:
                accepted = self.execution_boundary.persist_response(
                    response.output_text,
                    context,
                    created_by=response.model,
                    metadata=metadata,
                )
            except Exception as exc:
                if raw_analysis_id is not None:
                    self.raw_response_repository.update_raw_validation(
                        raw_analysis_id,
                        "rejected",
                        str(exc),
                    )
                raise

            if raw_analysis_id is not None:
                self.raw_response_repository.update_raw_validation(raw_analysis_id, "accepted")
            if accepted.persisted_analysis is None:
                outcomes.append(
                    ThesisUpdateOutcome(
                        candidate.company_id,
                        "full_reassessment_required",
                        accepted.update.impact,
                    )
                )
            else:
                outcomes.append(
                    ThesisUpdateOutcome(
                        candidate.company_id,
                        "persisted",
                        accepted.update.impact,
                        accepted.persisted_analysis.analysis_id,
                    )
                )
        return outcomes

    def revalidate_rejected(self, candidates: list) -> list[ThesisUpdateOutcome]:
        if self.raw_response_repository is None:
            raise ValueError("raw response repository is required for revalidation")
        rejected = self.raw_response_repository.get_latest_rejected_incremental_updates(
            [candidate.company_id for candidate in candidates]
        )
        outcomes = []
        for candidate in candidates:
            raw = rejected.get(candidate.company_id)
            if raw is None:
                outcomes.append(ThesisUpdateOutcome(candidate.company_id, "no_rejected_update"))
                continue
            context = self.context_builder.build(candidate)
            if context is None:
                outcomes.append(ThesisUpdateOutcome(candidate.company_id, "no_current_thesis"))
                continue
            metadata = dict(raw.get("metadata") or {})
            for key in ("analysis_mode", "validation_status", "validation_error"):
                metadata.pop(key, None)
            metadata["raw_analysis_id"] = raw["id"]
            try:
                accepted = self.execution_boundary.persist_response(
                    raw["content"],
                    context,
                    created_by=raw["created_by"],
                    metadata=metadata,
                )
            except Exception as exc:
                self.raw_response_repository.update_raw_validation(
                    raw["id"], "rejected", str(exc)
                )
                raise
            self.raw_response_repository.update_raw_validation(raw["id"], "accepted")
            if accepted.persisted_analysis is None:
                outcomes.append(
                    ThesisUpdateOutcome(
                        candidate.company_id,
                        "full_reassessment_required",
                        accepted.update.impact,
                    )
                )
            else:
                outcomes.append(
                    ThesisUpdateOutcome(
                        candidate.company_id,
                        "persisted",
                        accepted.update.impact,
                        accepted.persisted_analysis.analysis_id,
                    )
                )
        return outcomes
