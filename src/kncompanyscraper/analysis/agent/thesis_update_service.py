from dataclasses import asdict, dataclass
import json

from kncompanyscraper.analysis.agent.result_parser import (
    StockAnalysisValidationError,
    parse_stock_analysis_result,
    parse_thesis_update_result,
)
from kncompanyscraper.analysis.agent.thesis_update import ThesisUpdatePromptBuilder
from kncompanyscraper.analysis.agent.output_schema import (
    BusinessModelProfile,
    MarginExpansionCase,
    TimingAssessment,
)
from kncompanyscraper.constants import RAW_RESPONSE_TRANSIENT_METADATA_KEYS


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

    def __init__(self, stock_analysis_boundary, scenario_authoring_service=None):
        self.stock_analysis_boundary = stock_analysis_boundary
        self.scenario_authoring_service = scenario_authoring_service

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
        current_content = dict(context.current_thesis.get("content") or {})
        if (
            current_content.get("thesis_card_version") != "individual-thesis-card-v2"
            and update.impact != "full_reassessment_required"
        ):
            raise StockAnalysisValidationError(
                "v1 theses require a full reassessment before incremental updates"
            )
        self._validate_trigger_progress(update, context)
        if update.impact == "no_material_change":
            current_content["forward_scenario_analysis"] = None
            current_content.setdefault("confidence_limitations", [])
            current_content.setdefault(
                "thesis_card_version", "individual-thesis-card-v2"
            )
            current_content["evidence_as_of"] = (
                context.candidate.research_evidence.get("as_of")
            )
            current_content.setdefault(
                "business_model_profile", asdict(BusinessModelProfile())
            )
            current_content.setdefault(
                "margin_expansion_case", asdict(MarginExpansionCase())
            )
            current_content.setdefault(
                "timing_assessment", asdict(TimingAssessment())
            )
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
            # A no-material-change response does not invoke the authoring model;
            # carry forward the last accepted assumptions so the stock boundary
            # can recalculate the enriched analysis without dropping scenarios.
            updated_content["scenario_bundles"] = current_content.get(
                "scenario_bundles", []
            )
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
                    if (
                        current_content.get(key) != updated_content.get(key)
                        and key != "activation_trigger_evidence"
                    )
                )
                if changed_fields:
                    raise StockAnalysisValidationError(
                        "no_material_change must preserve the current thesis; changed fields: "
                        + ", ".join(changed_fields)
                    )
        elif self.scenario_authoring_service is not None:
            def validate(qualitative_result, horizon, bundles):
                qualitative_result.case_horizon_months = horizon
                qualitative_result.scenario_bundles = list(bundles)
                return self.stock_analysis_boundary.calculate_forward_scenario(
                    qualitative_result, context.candidate
                )

            authored = self.scenario_authoring_service.author(
                context.candidate,
                update.thesis,
                validate,
            )
            update.thesis.case_horizon_months = authored.case_horizon_months
            update.thesis.scenario_bundles = list(authored.scenario_bundles)
            if metadata is None:
                metadata = {}
            metadata["scenario_authoring_attempts"] = authored.attempts
            metadata["scenario_authoring_raw_analysis_ids"] = list(
                authored.raw_analysis_ids
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

    @staticmethod
    def _validate_trigger_progress(update, context):
        """Require incremental updates to evaluate, not silently roll, a trigger."""
        current = context.current_thesis.get("content") or {}
        if current.get("verdict") != "latent_case" or not current.get(
            "activation_trigger_spec"
        ):
            return
        if update.impact == "full_reassessment_required":
            return
        if not context.new_source_ids and not context.deterministic_context_changed:
            return

        entries = update.thesis.activation_trigger_evidence
        new_source_ids = set(context.new_source_ids)
        evaluated_entries = [
            entry
            for entry in entries
            if new_source_ids.intersection(entry.source_ids)
            or any(
                source_id.startswith(("full_results.", "deterministic:", "valuation:"))
                for source_id in entry.source_ids
            )
        ]
        if not evaluated_entries:
            raise StockAnalysisValidationError(
                "incremental update must evaluate the stored activation trigger with new evidence"
            )

        current_spec = current["activation_trigger_spec"]
        updated_spec = update.thesis.activation_trigger_spec
        same_trigger = (
            updated_spec is not None
            and ThesisUpdateExecutionBoundary._trigger_identity(current_spec)
            == ThesisUpdateExecutionBoundary._trigger_identity(updated_spec)
        )
        timing_changed = (
            updated_spec is not None
            and any(
                current_spec.get(field) != getattr(updated_spec, field)
                for field in ("evidence_window", "observation_requirement")
            )
        )
        if same_trigger and timing_changed and any(
            entry.status == "unresolved" for entry in evaluated_entries
        ):
            raise StockAnalysisValidationError(
                "incremental update cannot roll an unresolved activation trigger into an equivalent new waiting period"
            )
        if (
            same_trigger
            and update.thesis.verdict == "latent_case"
            and any(entry.status == "confirms" for entry in evaluated_entries)
        ):
            raise StockAnalysisValidationError(
                "resolved activation trigger requires activation or a revised thesis"
            )
    @staticmethod
    def _trigger_identity(spec):
        fields = ("unresolved_claim", "observable_metric_or_event", "threshold_or_direction")
        if isinstance(spec, dict):
            return tuple(spec.get(field) for field in fields)
        return tuple(getattr(spec, field) for field in fields)


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
            for key in RAW_RESPONSE_TRANSIENT_METADATA_KEYS:
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
