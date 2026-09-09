import json
from copy import deepcopy
from dataclasses import dataclass

from kncompanyscraper.analysis.agent.prompt_builder import AgentPromptBuilder
from kncompanyscraper.analysis.agent.context_provenance import (
    deterministic_context_sha256,
)
from kncompanyscraper.analysis.agent.readiness import AgentReadinessGate
from kncompanyscraper.analysis.agent.result_parser import (
    StockAnalysisValidationError,
    parse_qualitative_stock_analysis_result,
    parse_scenario_authoring_result,
    parse_stock_analysis_result,
)
from kncompanyscraper.analysis.agent.scenario_authoring import scenario_source_whitelist
from kncompanyscraper.constants import RAW_RESPONSE_TRANSIENT_METADATA_KEYS
from kncompanyscraper.logger import get_logger


logger = get_logger(__name__)


@dataclass(frozen=True)
class QualitativeStageResult:
    qualitative: object
    metadata: dict
    response: object


class AgentAnalysisService:
    def __init__(
        self,
        model_adapter,
        execution_boundary,
        prompt_builder=None,
        raw_response_repository=None,
        readiness_gate=None,
        scenario_authoring_service=None,
    ):
        self.model_adapter = model_adapter
        self.execution_boundary = execution_boundary
        self.prompt_builder = prompt_builder or AgentPromptBuilder()
        self.raw_response_repository = raw_response_repository
        self.readiness_gate = readiness_gate or AgentReadinessGate()
        self.scenario_authoring_service = scenario_authoring_service

    def build_qualitative_prompt(self, candidate):
        return self.prompt_builder.build(candidate)

    def run_qualitative(
        self, candidate, *, prompt=None, prior_metadata=None
    ) -> QualitativeStageResult:
        """Run only qualitative generation and validation for a checkpoint."""
        self.readiness_gate.require_ready([candidate])
        prompt = prompt or self.build_qualitative_prompt(candidate)
        deterministic_metadata = self._deterministic_metadata(candidate, prompt)
        prior_metadata = dict(prior_metadata or {})
        if prior_metadata.get("qualitative_attempts", 0) >= 2:
            raise StockAnalysisValidationError(
                "qualitative validation attempts are exhausted for this job"
            )
        response = self.model_adapter.generate(prompt)
        qualitative, metadata, final_response = self._run_qualitative_stage(
            candidate,
            prompt,
            response,
            deterministic_metadata,
            prior_metadata=prior_metadata,
        )
        return QualitativeStageResult(qualitative, metadata, final_response)

    def build_scenario_prompt(self, candidate, qualitative):
        if self.scenario_authoring_service is None or not self._requires_forward_scenario(
            candidate
        ):
            return None
        return self.scenario_authoring_service.prompt_builder.build(
            candidate, qualitative
        )

    def run_scenario(self, candidate, qualitative, metadata, *, prompt=None):
        """Run the scenario stage against an already accepted qualitative result."""
        if self.scenario_authoring_service is None:
            return qualitative
        if not self._requires_forward_scenario(candidate):
            return qualitative
        return self._enrich_with_scenarios(
            qualitative, candidate, metadata, base_prompt=prompt
        )

    def persist(self, candidate, qualitative, metadata, *, created_by: str):
        """Persist one already completed, validated full analysis."""
        return self.execution_boundary.persist_validated_result(
            qualitative,
            candidate,
            created_by=created_by,
            metadata=metadata,
        )

    def validate_qualitative_artifact(self, raw_response: str, candidate):
        """Rehydrate a frozen qualitative artifact without a model call."""
        return self.execution_boundary.validate_qualitative_response(
            raw_response, candidate
        )

    def rehydrate_scenario(self, candidate, qualitative, raw_response, metadata):
        """Rebuild an accepted scenario stage without another model call."""
        authored = parse_scenario_authoring_result(raw_response)
        if authored["case_horizon_months"] != qualitative.case_horizon_months:
            raise ValueError("stored scenario horizon no longer matches qualitative thesis")
        scenario_result = deepcopy(qualitative)
        scenario_result.case_horizon_months = authored["case_horizon_months"]
        scenario_result.scenario_bundles = list(authored["scenario_bundles"])
        self.execution_boundary.validate_forward_scenario_sources(
            scenario_result,
            candidate,
            source_whitelist=scenario_source_whitelist(candidate),
        )
        analysis = self.execution_boundary.calculate_forward_scenario(
            scenario_result, candidate
        )
        if analysis.status != "available":
            raise ValueError(
                "stored scenario artifact rejected: "
                + "; ".join(analysis.methodology_flags)
            )
        scenario_result.forward_scenario_analysis = analysis
        self.execution_boundary.validate_verdict_coherence(
            scenario_result, candidate
        )
        qualitative.case_horizon_months = authored["case_horizon_months"]
        qualitative.scenario_bundles = list(authored["scenario_bundles"])
        qualitative.forward_scenario_analysis = analysis
        metadata["scenario_authoring_raw_analysis_ids"] = metadata.get(
            "scenario_authoring_raw_analysis_ids", []
        )
        return qualitative

    @staticmethod
    def _deterministic_metadata(candidate, prompt):
        return {
            "policy_name": prompt.policy_name,
            "policy_version": prompt.policy_version,
            "policy_sha256": prompt.policy_sha256,
            "candidate_rank": candidate.rank,
            "evidence_as_of": candidate.research_evidence.get("as_of"),
            "evidence_source_ids": [
                source["source_id"]
                for key in ("documents", "insider_transactions")
                for source in candidate.research_evidence.get(key, [])
            ]
            + candidate.research_evidence.get("ownership_liquidity", {}).get(
                "source_ids", []
            ),
            "deterministic_context_sha256": deterministic_context_sha256(candidate),
        }

    def analyze(self, candidates: list) -> list:
        assessments = self.readiness_gate.require_ready(candidates)
        scenario_company_ids = {
            assessment.company_id
            for assessment in assessments
            if assessment.forward_scenario_readiness is not None
            and assessment.forward_scenario_readiness.status == "required"
        }
        persisted = []
        for candidate in candidates:
            logger.info(
                "Starting model analysis for %s (%s)",
                candidate.ticker,
                candidate.company_id,
            )
            prompt = self.prompt_builder.build(candidate)
            deterministic_metadata = {
                "policy_name": prompt.policy_name,
                "policy_version": prompt.policy_version,
                "policy_sha256": prompt.policy_sha256,
                "candidate_rank": candidate.rank,
                "evidence_as_of": candidate.research_evidence.get("as_of"),
                "evidence_source_ids": [
                    source["source_id"]
                    for key in ("documents", "insider_transactions")
                    for source in candidate.research_evidence.get(key, [])
                ]
                + candidate.research_evidence.get("ownership_liquidity", {}).get(
                    "source_ids", []
                ),
                "deterministic_context_sha256": deterministic_context_sha256(candidate),
            }
            response = self.model_adapter.generate(prompt)
            qualitative, metadata, final_response = self._run_qualitative_stage(
                candidate, prompt, response, deterministic_metadata
            )
            if (
                self.scenario_authoring_service is not None
                and candidate.company_id in scenario_company_ids
            ):
                qualitative = self._enrich_with_scenarios(
                    qualitative, candidate, metadata
                )
            persisted.append(
                self.execution_boundary.persist_validated_result(
                    qualitative,
                    candidate,
                    created_by=final_response.model,
                    metadata=metadata,
                )
            )
        return persisted

    def _run_qualitative_stage(
        self,
        candidate,
        prompt,
        response,
        deterministic_metadata,
        *,
        prior_metadata=None,
    ):
        """Run the qualitative stage with one initial call and one repair."""
        prior_metadata = dict(prior_metadata or {})
        raw_analysis_ids = list(prior_metadata.get("qualitative_raw_analysis_ids", []))
        validation_errors = list(
            prior_metadata.get("qualitative_validation_errors", [])
        )
        input_measurements = list(
            prior_metadata.get("qualitative_input_measurements", [])
        )
        model_response_ids = list(
            prior_metadata.get("qualitative_model_response_ids", [])
        )
        first_attempt = prior_metadata.get("qualitative_attempts", 0) + 1
        for attempt in range(first_attempt, 3):
            input_measurement = getattr(response, "input_measurement", None)
            if input_measurement is not None:
                input_measurements.append(input_measurement)
            model_response_ids.append(response.response_id)
            metadata = {
                "model_response_id": response.response_id,
                "usage": response.usage,
                **deterministic_metadata,
            }
            if input_measurement is not None:
                metadata["input_measurement"] = input_measurement
            raw_analysis_id = None
            if self.raw_response_repository is not None:
                raw_analysis_id = self.raw_response_repository.save_stock_analysis_raw(
                    candidate.company_id,
                    response.output_text,
                    created_by=response.model,
                    metadata={
                        "analysis_mode": "initial",
                        "analysis_stage": "qualitative",
                        "analysis_attempt": attempt,
                        "artifact_type": "model_response",
                        **metadata,
                    },
                )
                if raw_analysis_id is not None:
                    raw_analysis_ids.append(raw_analysis_id)
            try:
                qualitative = self.execution_boundary.validate_qualitative_response(
                    response.output_text, candidate
                )
            except StockAnalysisValidationError as exc:
                validation_errors.append(str(exc))
                if raw_analysis_id is not None:
                    self.raw_response_repository.update_raw_validation(
                        raw_analysis_id, "rejected", str(exc)
                    )
                repair = getattr(self.model_adapter, "repair", None)
                if repair is None or attempt == 2:
                    exc.stage_metadata = self._qualitative_stage_metadata(
                        attempt,
                        raw_analysis_ids,
                        input_measurements,
                        validation_errors,
                        model_response_ids,
                    )
                    raise
                try:
                    response = repair(prompt, response.output_text, str(exc))
                except Exception as interruption:
                    interruption.stage_metadata = self._qualitative_stage_metadata(
                        attempt,
                        raw_analysis_ids,
                        input_measurements,
                        validation_errors,
                        model_response_ids,
                    )
                    raise
                continue

            if raw_analysis_id is not None:
                self.raw_response_repository.update_raw_validation(
                    raw_analysis_id, "accepted"
                )
                metadata["raw_analysis_id"] = raw_analysis_id
            metadata["qualitative_raw_analysis_id"] = raw_analysis_id
            metadata["qualitative_raw_analysis_ids"] = raw_analysis_ids
            metadata["qualitative_attempts"] = attempt
            metadata["qualitative_validation_errors"] = validation_errors
            if input_measurements:
                metadata["qualitative_input_measurements"] = input_measurements
            return qualitative, metadata, response
        raise AssertionError("qualitative stage did not return or raise")

    @staticmethod
    def _qualitative_stage_metadata(
        attempts,
        raw_analysis_ids,
        input_measurements,
        validation_errors,
        model_response_ids,
    ):
        return {
            "qualitative_attempts": attempts,
            "qualitative_raw_analysis_ids": list(raw_analysis_ids),
            "qualitative_input_measurements": list(input_measurements),
            "qualitative_validation_errors": list(validation_errors),
            "qualitative_model_response_ids": list(model_response_ids),
        }

    def repair_rejected(self, candidates: list) -> list:
        if self.raw_response_repository is None:
            raise ValueError("raw response repository is required for repair")
        repair = getattr(self.model_adapter, "repair", None)
        if repair is None:
            raise ValueError("selected model adapter does not support repair")
        self.readiness_gate.require_ready(candidates)
        rejected = self.raw_response_repository.get_latest_rejected_initial_analyses(
            [candidate.company_id for candidate in candidates]
        )
        persisted = []
        for candidate in candidates:
            raw = rejected.get(candidate.company_id)
            if raw is None:
                continue
            prompt = self.prompt_builder.build(candidate)
            error = (raw.get("metadata") or {}).get("validation_error")
            if not error:
                raise ValueError(
                    f"rejected response {raw['id']} has no validation error"
                )
            logger.info(
                "Repairing stored response %s for %s",
                raw["id"],
                candidate.ticker,
            )
            response = repair(prompt, raw["content"], error)
            deterministic_metadata = {
                "policy_name": prompt.policy_name,
                "policy_version": prompt.policy_version,
                "policy_sha256": prompt.policy_sha256,
                "candidate_rank": candidate.rank,
                "evidence_as_of": candidate.research_evidence.get("as_of"),
                "evidence_source_ids": [
                    source["source_id"]
                    for key in ("documents", "insider_transactions")
                    for source in candidate.research_evidence.get(key, [])
                ]
                + candidate.research_evidence.get("ownership_liquidity", {}).get(
                    "source_ids", []
                ),
                "deterministic_context_sha256": deterministic_context_sha256(
                    candidate
                ),
                "repaired_from_raw_analysis_id": raw["id"],
            }
            qualitative, metadata, final_response = self._run_qualitative_stage(
                candidate, prompt, response, deterministic_metadata
            )
            if (
                self.scenario_authoring_service is not None
                and self._requires_forward_scenario(candidate)
            ):
                qualitative = self._enrich_with_scenarios(
                    qualitative, candidate, metadata
                )
            persisted.append(
                self.execution_boundary.persist_validated_result(
                    qualitative,
                    candidate,
                    created_by=final_response.model,
                    metadata=metadata,
                )
            )
        return persisted

    def revalidate_rejected(self, candidates: list) -> list:
        if self.raw_response_repository is None:
            raise ValueError("raw response repository is required for revalidation")
        rejected = self.raw_response_repository.get_latest_rejected_initial_analyses(
            [candidate.company_id for candidate in candidates]
        )
        persisted = []
        for candidate in candidates:
            raw = rejected.get(candidate.company_id)
            if raw is None:
                continue
            metadata = dict(raw.get("metadata") or {})
            for key in RAW_RESPONSE_TRANSIENT_METADATA_KEYS:
                metadata.pop(key, None)
            metadata["raw_analysis_id"] = raw["id"]
            try:
                content = raw["content"]
                if (
                    self.scenario_authoring_service is not None
                    and self._requires_forward_scenario(candidate)
                ):
                    qualitative = self.execution_boundary.validate_qualitative_response(
                        content, candidate
                    )
                    content = self._enrich_with_scenarios(
                        qualitative, candidate, metadata
                    )
                    content = json.dumps(content.to_dict(), ensure_ascii=False)
                accepted = self.execution_boundary.persist_response(
                    content,
                    candidate,
                    created_by=raw["created_by"],
                    metadata=metadata,
                )
            except Exception as exc:
                self.raw_response_repository.update_raw_validation(
                    raw["id"], "rejected", str(exc)
                )
                raise
            self.raw_response_repository.update_raw_validation(raw["id"], "accepted")
            persisted.append(accepted)
        return persisted

    def _requires_forward_scenario(self, candidate) -> bool:
        assessment = self.readiness_gate.assess(candidate)
        readiness = assessment.forward_scenario_readiness
        return readiness is not None and readiness.status == "required"

    def _enrich_with_scenarios(
        self, qualitative, candidate, metadata, *, base_prompt=None
    ):
        if isinstance(qualitative, str):
            qualitative = parse_qualitative_stock_analysis_result(qualitative)

        def validate(qualitative_result, horizon, bundles):
            scenario_result = deepcopy(qualitative_result)
            scenario_result.case_horizon_months = horizon
            scenario_result.scenario_bundles = list(bundles)
            self.execution_boundary.validate_forward_scenario_sources(
                scenario_result,
                candidate,
                source_whitelist=scenario_source_whitelist(candidate),
            )
            analysis = self.execution_boundary.calculate_forward_scenario(
                scenario_result, candidate
            )
            if callable(getattr(analysis, "band", None)) and analysis.band("base") is not None:
                scenario_result.forward_scenario_analysis = analysis
                self.execution_boundary.validate_verdict_coherence(
                    scenario_result,
                    candidate,
                    require_forward_scenario=analysis.status == "available",
                )
            return analysis

        authored = self.scenario_authoring_service.author(
            candidate,
            qualitative,
            validate,
            base_prompt=base_prompt,
            prior_metadata=metadata,
        )
        qualitative.case_horizon_months = authored.case_horizon_months
        qualitative.scenario_bundles = list(authored.scenario_bundles)
        qualitative.forward_scenario_analysis = authored.analysis
        metadata["scenario_authoring_attempts"] = authored.attempts
        metadata["scenario_authoring_raw_analysis_ids"] = list(
            authored.raw_analysis_ids
        )
        metadata["scenario_policy_name"] = getattr(authored, "policy_name", "")
        metadata["scenario_policy_version"] = getattr(authored, "policy_version", "")
        metadata["scenario_policy_sha256"] = getattr(authored, "policy_sha256", "")
        metadata["scenario_input_hashes"] = list(
            getattr(authored, "scenario_input_hashes", ())
        )
        metadata["scenario_input_measurements"] = list(
            getattr(authored, "scenario_input_measurements", ())
        )
        metadata["scenario_validation_errors"] = list(
            getattr(authored, "scenario_validation_errors", ())
        )
        metadata["scenario_model_response_ids"] = list(
            getattr(authored, "model_response_ids", ())
        )
        qualitative.case_horizon_months = authored.case_horizon_months
        qualitative.scenario_bundles = list(authored.scenario_bundles)
        return qualitative
