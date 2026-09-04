"""Durable exact-company analysis orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from inspect import signature
from time import perf_counter
from typing import Callable, Iterable

from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.agent_packet import (
    AgentCandidatePacket,
    deserialize_packet,
    serialize_packet,
)
from kncompanyscraper.analysis.agent.packet_measurement import measure_packet
from kncompanyscraper.analysis.agent.prompt_artifact import (
    deserialize_prompt,
    prompt_sha256,
    serialize_prompt,
)
from kncompanyscraper.analysis.agent.readiness import AgentReadinessError
from kncompanyscraper.analysis.agent.result_parser import StockAnalysisValidationError


@dataclass(frozen=True)
class CompanyAnalysisOutcome:
    company_id: int
    ticker: str
    status: str
    job_id: int
    error: str | None = None
    analysis_id: int | None = None
    thesis_revision_id: int | None = None

    @property
    def resume_command(self) -> str:
        return f"python -m kncompanyscraper.main analyze-company --resume-job-id {self.job_id}"


class FrozenStageInputIntegrityError(ValueError):
    """A persisted stage prompt cannot be trusted for resume."""


class CompanyAnalysisPipeline:
    """Run one company at a time and checkpoint every durable stage."""

    JOB_TYPE = "company_full_analysis"

    def __init__(
        self,
        company_repository,
        refresh_service,
        snapshot_service,
        context_builder,
        analysis_service,
        job_repository,
        *,
        clock: Callable[[], datetime] | None = None,
        timer: Callable[[], float] | None = None,
        progress: Callable[[str], None] | None = None,
    ):
        self.company_repository = company_repository
        self.refresh_service = refresh_service
        self.snapshot_service = snapshot_service
        self.context_builder = context_builder
        self.analysis_service = analysis_service
        self.job_repository = job_repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.timer = timer or perf_counter
        self.progress = progress or print
        self._job_starts = {}
        self._stage_starts = {}

    def resolve_companies(
        self,
        *,
        company_ids: Iterable[int] | None = None,
        tickers: Iterable[str] | None = None,
    ) -> list:
        """Resolve only active watchlist companies, without loading the universe."""
        has_ids = company_ids is not None
        has_tickers = tickers is not None
        if has_ids == has_tickers:
            raise ValueError("exactly one of company_ids or tickers is required")

        values = list(company_ids if has_ids else tickers)
        if not values:
            raise ValueError("at least one company selector is required")
        normalized = [
            value if has_ids else str(value).strip().upper() for value in values
        ]
        if len(normalized) != len(set(normalized)):
            raise ValueError("duplicate company selector")

        companies = []
        for selector in normalized:
            company = (
                self.company_repository.get_active_by_id(selector)
                if has_ids
                else self.company_repository.get_active_by_ticker(selector)
            )
            if company is None:
                kind = "company ID" if has_ids else "ticker"
                raise ValueError(f"unknown or inactive {kind}: {selector}")
            companies.append(company)
        return companies

    def run(
        self,
        companies: Iterable,
        *,
        settings: dict | None = None,
        invocation: dict | None = None,
    ) -> tuple[CompanyAnalysisOutcome, ...]:
        settings = dict(settings or {})
        invocation = dict(invocation or {})
        outcomes = []
        for company in companies:
            try:
                outcomes.append(
                    self._run_company(company, settings=settings, invocation=invocation)
                )
            except Exception as exc:
                outcomes.append(
                    CompanyAnalysisOutcome(
                        company.id,
                        company.ticker,
                        "failed",
                        -1,
                        str(exc),
                    )
                )
        return tuple(outcomes)

    analyze = run

    def resume(self, job_id: int) -> CompanyAnalysisOutcome:
        job = self.job_repository.get(job_id)
        if job is None:
            raise ValueError(f"company analysis job {job_id} not found")
        result = dict(job.get("result") or {})
        company = self.company_repository.get_by_id(job.get("company_id"))
        ticker = result.get("company", {}).get("ticker") or getattr(company, "ticker", "")
        if job.get("job_type") != self.JOB_TYPE:
            raise ValueError(f"job {job_id} is not a company analysis job")
        if job.get("status") == "success" or result.get("final_analysis_id"):
            return CompanyAnalysisOutcome(
                job.get("company_id"), ticker, "already-completed", job_id,
                analysis_id=result.get("final_analysis_id"),
                thesis_revision_id=result.get("thesis_revision_id"),
            )
        if self._validation_attempts_exhausted(result):
            raise ValueError(
                f"job {job_id} exhausted its bounded validation attempts; fix the "
                "policy or prompt issue and start a fresh explicit-company reassessment"
            )
        if company is None:
            raise ValueError(f"company {job.get('company_id')} for job {job_id} not found")
        packet_json = result.get("packet_json")
        if not packet_json:
            raise ValueError(f"job {job_id} has no frozen packet to resume")

        candidate = self._candidate_from_packet(packet_json)
        self.job_repository.mark_running(job_id)
        result["status"] = "running"
        self.job_repository.update_result(job_id, result)
        self._job_starts[job_id] = self.timer()
        try:
            self._verify_packet_hash(job_id, result)
            self._verify_frozen_stage_inputs(job_id, result)
            qualitative, metadata, created_by = self._resume_model_stages(
                job_id, result, candidate
            )
            return self._persist_and_complete(
                job_id, result, candidate, qualitative, metadata, created_by
            )
        except AgentReadinessError as exc:
            return self._finish_failure(
                job_id, result, candidate, "blocked-before-model", exc, resumable=False
            )
        except FrozenStageInputIntegrityError as exc:
            return self._finish_failure(
                job_id, result, candidate, "failed", exc, resumable=False
            )
        except StockAnalysisValidationError as exc:
            result["terminal_failure_reason"] = "validation_attempts_exhausted"
            return self._finish_failure(
                job_id, result, candidate, "failed", exc, resumable=False
            )
        except Exception as exc:
            return self._finish_failure(
                job_id,
                result,
                candidate,
                "resumable" if result.get("packet_json") else "failed",
                exc,
                resumable=bool(result.get("packet_json")),
            )

    def _run_company(self, company, *, settings, invocation):
        job_id = self.job_repository.start(self.JOB_TYPE, company.id)
        result = {
            "company": {
                "company_id": company.id,
                "ticker": company.ticker,
                "name": company.name,
            },
            "settings": settings,
            "invocation": invocation,
            "status": "running",
            "stages": {},
            "next_resumable_stage": "refresh",
        }
        self.job_repository.update_result(job_id, result)
        started = self.timer()
        self._job_starts[job_id] = started
        try:
            self._start_stage(result, job_id, "refresh")
            refresh = self.refresh_service.refresh([company])[0]
            result["refresh"] = refresh.to_dict()
            if refresh.blocked_before_model:
                return self._finish_failure(
                    job_id,
                    result,
                    company,
                    "blocked-before-model",
                    ValueError("mandatory refresh failed"),
                    resumable=False,
                )
            self._complete_stage(result, job_id, "refresh", refresh=result["refresh"])

            self._start_stage(result, job_id, "deterministic")
            snapshot_run = self.snapshot_service.analyze([company])
            snapshot = snapshot_run.snapshots[0]
            candidate = self.context_builder.build_company(company, snapshot.results)
            candidate.research_evidence["refresh_limitations"] = [
                limitation.to_dict() for limitation in refresh.limitations
            ]
            self._complete_stage(
                result,
                job_id,
                "deterministic",
                diagnostics=snapshot_run.diagnostics(),
            )

            self._start_stage(result, job_id, "readiness")
            readiness_gate = getattr(self.analysis_service, "readiness_gate", None)
            if readiness_gate is not None:
                readiness_gate.require_ready([candidate])
            self._complete_stage(result, job_id, "readiness")

            self._start_stage(result, job_id, "packet")
            packet = AgentCandidatePacket.from_candidate(candidate)
            packet_json = serialize_packet(packet)
            result["packet_json"] = packet_json
            result["packet_hash"] = sha256(packet_json.encode("utf-8")).hexdigest()
            result["packet_measurement"] = asdict(measure_packet(packet, pretty=False))
            self._complete_stage(
                result,
                job_id,
                "packet",
                packet_hash=result["packet_hash"],
                packet_measurement=result["packet_measurement"],
            )

            qualitative, metadata, created_by = self._run_model_stages(
                job_id, result, candidate
            )
            outcome = self._persist_and_complete(
                job_id, result, candidate, qualitative, metadata, created_by
            )
            return outcome
        except AgentReadinessError as exc:
            return self._finish_failure(
                job_id, result, company, "blocked-before-model", exc, resumable=False
            )
        except StockAnalysisValidationError as exc:
            result["terminal_failure_reason"] = "validation_attempts_exhausted"
            return self._finish_failure(
                job_id, result, company, "failed", exc, resumable=False
            )
        except Exception as exc:
            next_stage = result.get("next_resumable_stage") or "refresh"
            resumable = bool(result.get("packet_json")) and next_stage in {
                "qualitative", "scenario", "persistence"
            }
            return self._finish_failure(
                job_id,
                result,
                company,
                "resumable" if resumable else "failed",
                exc,
                resumable=resumable,
            )

    def _run_model_stages(
        self, job_id, result, candidate, *, qualitative_prompt=None
    ):
        self._start_stage(result, job_id, "qualitative")
        qualitative_prompt = self._prepare_stage_prompt(
            job_id,
            result,
            "qualitative",
            candidate,
            prompt=qualitative_prompt,
        )
        prior_metadata = dict(
            result.get("stages", {}).get("qualitative", {}).get("metadata") or {}
        )
        try:
            qualitative_stage = self._run_qualitative(
                candidate, qualitative_prompt, prior_metadata=prior_metadata
            )
        except Exception as exc:
            self._record_stage_failure_metadata(
                result, job_id, "qualitative", getattr(exc, "stage_metadata", {})
            )
            raise
        qualitative = qualitative_stage.qualitative
        metadata = dict(qualitative_stage.metadata)
        created_by = qualitative_stage.response.model
        result["accepted_qualitative_raw_analysis_id"] = metadata.get(
            "qualitative_raw_analysis_id"
        )
        result["accepted_qualitative_created_by"] = created_by
        self._complete_stage(
            result,
            job_id,
            "qualitative",
            raw_analysis_id=result["accepted_qualitative_raw_analysis_id"],
            raw_analysis_ids=metadata.get("qualitative_raw_analysis_ids", []),
            attempts=metadata.get("qualitative_attempts", 1),
            input_measurements=metadata.get("qualitative_input_measurements", []),
            input_hashes=[
                item.get("input_sha256")
                for item in metadata.get("qualitative_input_measurements", [])
                if item.get("input_sha256")
            ],
            validation_results=metadata.get("qualitative_validation_errors", []),
            metadata=metadata,
        )

        self._start_stage(result, job_id, "scenario")
        scenario_prompt = self._prepare_stage_prompt(
            job_id, result, "scenario", candidate, qualitative
        )
        try:
            qualitative = self._run_scenario(
                candidate, qualitative, metadata, scenario_prompt
            )
        except Exception as exc:
            self._record_stage_failure_metadata(
                result, job_id, "scenario", getattr(exc, "stage_metadata", {})
            )
            raise
        result["scenario_raw_analysis_ids"] = metadata.get(
            "scenario_authoring_raw_analysis_ids", []
        )
        self._complete_stage(
            result,
            job_id,
            "scenario",
            raw_analysis_ids=result["scenario_raw_analysis_ids"],
            attempts=metadata.get("scenario_authoring_attempts", 0),
            input_measurements=metadata.get("scenario_input_measurements", []),
            input_hashes=[
                item.get("input_sha256")
                for item in metadata.get("scenario_input_measurements", [])
                if item.get("input_sha256")
            ],
            validation_results=metadata.get("scenario_validation_errors", []),
            metadata=metadata,
        )
        return qualitative, metadata, created_by

    def _run_qualitative(self, candidate, prompt, *, prior_metadata=None):
        method = self.analysis_service.run_qualitative
        kwargs = {}
        if prompt is not None:
            kwargs["prompt"] = prompt
        if prior_metadata and "prior_metadata" in signature(method).parameters:
            kwargs["prior_metadata"] = prior_metadata
        return method(candidate, **kwargs)

    def _run_scenario(self, candidate, qualitative, metadata, prompt):
        if prompt is None:
            return self.analysis_service.run_scenario(
                candidate, qualitative, metadata
            )
        return self.analysis_service.run_scenario(
            candidate, qualitative, metadata, prompt=prompt
        )

    def _prepare_stage_prompt(
        self, job_id, result, stage, candidate, qualitative=None, *, prompt=None
    ):
        if prompt is None:
            builder = getattr(
                self.analysis_service, f"build_{stage}_prompt", None
            )
            if not callable(builder):
                return None
            prompt = (
                builder(candidate, qualitative)
                if stage == "scenario"
                else builder(candidate)
            )
        if prompt is None:
            return None

        artifact = serialize_prompt(prompt)
        artifact_hash = prompt_sha256(artifact)
        stage_result = result.setdefault("stages", {}).setdefault(stage, {})
        existing_hash = stage_result.get("base_prompt_sha256")
        if existing_hash is not None and existing_hash != artifact_hash:
            raise FrozenStageInputIntegrityError(
                f"job {job_id} stage {stage} frozen prompt artifact changed"
            )
        if stage_result.get("base_prompt_artifact") not in (None, artifact):
            raise FrozenStageInputIntegrityError(
                f"job {job_id} stage {stage} frozen prompt artifact changed"
            )
        if stage_result.get("base_prompt_artifact") is None:
            checkpoint = {
                "base_prompt_artifact": artifact,
                "base_prompt_sha256": artifact_hash,
                "prompt_contract_version": getattr(prompt, "contract_version", ""),
                "base_prompt_measurement": getattr(
                    prompt, "packet_measurement", None
                ),
            }
            stage_result.update(checkpoint)
            checkpoint_method = getattr(
                self.job_repository, "checkpoint_stage_input", None
            )
            if callable(checkpoint_method):
                checkpoint_method(job_id, stage, checkpoint)
            else:
                self.job_repository.update_result(job_id, result)
        return prompt

    def _verify_packet_hash(self, job_id, result):
        expected_hash = result.get("packet_hash")
        packet_json = result.get("packet_json")
        if expected_hash and packet_json:
            actual_hash = sha256(packet_json.encode("utf-8")).hexdigest()
            if actual_hash != expected_hash:
                raise FrozenStageInputIntegrityError(
                    f"job {job_id} frozen packet hash mismatch"
                )

    def _verify_frozen_stage_inputs(self, job_id, result):
        for stage in ("qualitative", "scenario"):
            stage_result = result.get("stages", {}).get(stage, {})
            if not stage_result:
                continue
            if not (
                stage_result.get("base_prompt_artifact")
                or stage_result.get("base_prompt_sha256")
            ):
                if stage_result.get("status") in {"accepted", "failed", "running"} and callable(
                    getattr(self.analysis_service, f"build_{stage}_prompt", None)
                ):
                    raise FrozenStageInputIntegrityError(
                        f"job {job_id} stage {stage} has no frozen prompt artifact"
                    )
                continue
            self._frozen_stage_prompt(job_id, result, stage)

    def _frozen_stage_prompt(self, job_id, result, stage):
        stage_result = result.get("stages", {}).get(stage, {})
        artifact = stage_result.get("base_prompt_artifact")
        if not artifact:
            raise FrozenStageInputIntegrityError(
                f"job {job_id} stage {stage} has no frozen prompt artifact"
            )
        expected_hash = stage_result.get("base_prompt_sha256")
        if not expected_hash:
            raise FrozenStageInputIntegrityError(
                f"job {job_id} stage {stage} has no frozen prompt hash"
            )
        actual_hash = prompt_sha256(artifact)
        if actual_hash != expected_hash:
            raise FrozenStageInputIntegrityError(
                f"job {job_id} stage {stage} frozen prompt artifact hash mismatch"
            )
        try:
            prompt = deserialize_prompt(artifact)
        except ValueError as exc:
            raise FrozenStageInputIntegrityError(
                f"job {job_id} stage {stage} frozen prompt artifact is corrupt"
            ) from exc
        stored_contract_version = stage_result.get("prompt_contract_version")
        if stored_contract_version != getattr(prompt, "contract_version", ""):
            raise FrozenStageInputIntegrityError(
                f"job {job_id} stage {stage} prompt contract version mismatch"
            )
        return prompt

    def _resume_model_stages(self, job_id, result, candidate):
        qualitative_stage = result.get("stages", {}).get("qualitative", {})
        raw_id = result.get("accepted_qualitative_raw_analysis_id")
        raw_repository = self.analysis_service.raw_response_repository
        if qualitative_stage.get("status") == "accepted" and raw_id:
            raw = raw_repository.get_stock_analysis_raw(raw_id)
            if raw is None:
                raise ValueError(f"qualitative artifact {raw_id} is missing")
            qualitative = self.analysis_service.validate_qualitative_artifact(
                raw["content"], candidate
            )
            metadata = dict(qualitative_stage.get("metadata") or {})
            created_by = raw.get("created_by") or result.get("accepted_qualitative_created_by", "")
        else:
            qualitative_prompt = self._resume_stage_prompt(
                job_id, result, "qualitative"
            )
            qualitative, metadata, created_by = self._run_model_stages(
                job_id,
                result,
                candidate,
                qualitative_prompt=qualitative_prompt,
            )
            return qualitative, metadata, created_by

        if result.get("stages", {}).get("scenario", {}).get("status") == "accepted":
            ids = result.get("scenario_raw_analysis_ids") or []
            if ids:
                raw = raw_repository.get_stock_analysis_raw(ids[-1])
                if raw is None:
                    raise ValueError(f"scenario artifact {ids[-1]} is missing")
                qualitative = self.analysis_service.rehydrate_scenario(
                    candidate, qualitative, raw["content"], metadata
                )
            return qualitative, metadata, created_by

        scenario_stage = result.get("stages", {}).get("scenario", {})
        metadata.update(dict(scenario_stage.get("metadata") or {}))
        self._start_stage(result, job_id, "scenario")
        scenario_prompt = self._resume_stage_prompt(job_id, result, "scenario")
        try:
            qualitative = self._run_scenario(
                candidate, qualitative, metadata, scenario_prompt
            )
        except Exception as exc:
            self._record_stage_failure_metadata(
                result, job_id, "scenario", getattr(exc, "stage_metadata", {})
            )
            raise
        result["scenario_raw_analysis_ids"] = metadata.get(
            "scenario_authoring_raw_analysis_ids", []
        )
        self._complete_stage(
            result,
            job_id,
            "scenario",
            raw_analysis_ids=result["scenario_raw_analysis_ids"],
            attempts=metadata.get("scenario_authoring_attempts", 0),
            input_measurements=metadata.get("scenario_input_measurements", []),
            input_hashes=[
                item.get("input_sha256")
                for item in metadata.get("scenario_input_measurements", [])
                if item.get("input_sha256")
            ],
            validation_results=metadata.get("scenario_validation_errors", []),
            metadata=metadata,
        )
        return qualitative, metadata, created_by

    def _resume_stage_prompt(self, job_id, result, stage):
        stage_result = result.get("stages", {}).get(stage, {})
        if not stage_result.get("base_prompt_artifact") and not callable(
            getattr(self.analysis_service, f"build_{stage}_prompt", None)
        ):
            # Compatibility for older service doubles that never exposed a prompt.
            return None
        return self._frozen_stage_prompt(job_id, result, stage)

    def _persist_and_complete(
        self, job_id, result, candidate, qualitative, metadata, created_by
    ):
        self._start_stage(result, job_id, "persistence")
        metadata = {
            **metadata,
            "analysis_mode": "initial",
            "thesis_revision_type": "full_reassessment",
            "company_analysis_job_id": job_id,
            "packet_hash": result.get("packet_hash"),
        }
        result["reproducibility"] = self._reproducibility_manifest(
            result, candidate, metadata
        )
        repository = self._analysis_repository()
        analysis_id = (
            repository.get_stock_analysis_for_job(job_id)
            if repository is not None
            else None
        )
        if analysis_id is None:
            persisted = self.analysis_service.persist(
                candidate, qualitative, metadata, created_by=created_by
            )
            analysis_id = persisted.analysis_id
        thesis_revision_id = self._thesis_revision_id(analysis_id)
        result.update(
            {
                "status": "success",
                "final_analysis_id": analysis_id,
                "thesis_revision_id": thesis_revision_id,
                "next_resumable_stage": None,
            }
        )
        self._record_elapsed(result, job_id)
        self._complete_stage(
            result,
            job_id,
            "persistence",
            analysis_id=analysis_id,
            thesis_revision_id=thesis_revision_id,
        )
        result["next_resumable_stage"] = None
        self.job_repository.complete(job_id, result)
        self.progress(f"{candidate.ticker}: accepted (job {job_id})")
        return CompanyAnalysisOutcome(
            candidate.company_id,
            candidate.ticker,
            "accepted",
            job_id,
            analysis_id=analysis_id,
            thesis_revision_id=thesis_revision_id,
        )

    def _thesis_revision_id(self, analysis_id):
        repository = self._analysis_repository()
        getter = getattr(repository, "get_thesis_revision_id", None)
        return getter(analysis_id) if callable(getter) else None

    def _analysis_repository(self):
        boundary = getattr(self.analysis_service, "execution_boundary", None)
        return getattr(boundary, "analysis_repository", None)

    def _finish_failure(self, job_id, result, item, status, exc, *, resumable):
        self._fail_active_stage(result, job_id)
        result["status"] = "failed"
        result["error"] = str(exc)
        if getattr(exc, "code", None):
            result["error_code"] = exc.code
            result["error_metadata"] = dict(getattr(exc, "metadata", {}) or {})
        result["next_resumable_stage"] = (
            self._next_stage(result) if resumable else None
        )
        self.job_repository.fail(job_id, str(exc), result)
        ticker = item.ticker
        if resumable:
            command = f"python -m kncompanyscraper.main analyze-company --resume-job-id {job_id}"
            self.progress(f"{ticker}: resumable after {self._next_stage(result)}; {command}")
        else:
            self.progress(f"{ticker}: {status}: {exc}")
        return CompanyAnalysisOutcome(
            getattr(item, "company_id", getattr(item, "id", None)),
            ticker,
            status,
            job_id,
            str(exc),
        )

    @staticmethod
    def _next_stage(result):
        stages = result.get("stages", {})
        for stage in ("qualitative", "scenario", "persistence"):
            if stages.get(stage, {}).get("status") != "accepted":
                return stage
        return "persistence"

    def _start_stage(self, result, job_id, stage):
        result["next_resumable_stage"] = stage
        stage_result = result.setdefault("stages", {}).setdefault(stage, {})
        stage_result.update(
            {
                "status": "running",
                "started_at": self.clock().isoformat(),
                "model_settings": dict(result.get("settings") or {}),
            }
        )
        self._stage_starts[(job_id, stage)] = self.timer()
        self.job_repository.update_result(job_id, result)
        self.progress(f"{result['company']['ticker']}: {stage} started")

    def _complete_stage(self, result, job_id, stage, **details):
        stage_result = result.setdefault("stages", {}).setdefault(stage, {})
        if "attempts" in details:
            details["attempts"] = max(
                stage_result.get("attempts", 0) or 0,
                details.get("attempts", 0) or 0,
            )
        stage_result.update(
            {
                "status": "accepted",
                "completed_at": self.clock().isoformat(),
                "duration_seconds": self._stage_duration(job_id, stage),
                **details,
            }
        )
        self._update_stage_timings(result)
        result["next_resumable_stage"] = self._next_stage(result)
        self.job_repository.update_result(job_id, result)

    def _stage_duration(self, job_id, stage):
        started = self._stage_starts.pop((job_id, stage), None)
        return max(0.0, self.timer() - started) if started is not None else None

    def _fail_active_stage(self, result, job_id):
        for stage, stage_result in result.get("stages", {}).items():
            if stage_result.get("status") != "running":
                continue
            stage_result.update(
                {
                    "status": "failed",
                    "completed_at": self.clock().isoformat(),
                    "duration_seconds": self._stage_duration(job_id, stage),
                }
            )
        self._update_stage_timings(result)
        self._record_elapsed(result, job_id)

    def _record_stage_failure_metadata(self, result, job_id, stage, metadata):
        if not metadata:
            return
        stage_result = result.setdefault("stages", {}).setdefault(stage, {})
        prefix = "scenario_authoring" if stage == "scenario" else "qualitative"
        attempts = metadata.get(f"{prefix}_attempts", 0)
        stage_result.update(
            {
                "attempts": max(stage_result.get("attempts", 0) or 0, attempts or 0),
                "raw_analysis_ids": metadata.get(
                    f"{prefix}_raw_analysis_ids", []
                ),
                "input_measurements": metadata.get(
                    f"{stage}_input_measurements", []
                ),
                "input_hashes": metadata.get(f"{stage}_input_hashes")
                or [
                    item.get("input_sha256")
                    for item in metadata.get(f"{stage}_input_measurements", [])
                    if item.get("input_sha256")
                ],
                "validation_results": metadata.get(
                    f"{stage}_validation_errors", []
                ),
                "metadata": {
                    **dict(stage_result.get("metadata") or {}),
                    **metadata,
                },
                **metadata,
            }
        )
        if stage == "scenario":
            result["scenario_raw_analysis_ids"] = list(
                metadata.get("scenario_authoring_raw_analysis_ids", [])
            )
        self.job_repository.update_result(job_id, result)

    @staticmethod
    def _validation_attempts_exhausted(result):
        if result.get("terminal_failure_reason") == "validation_attempts_exhausted":
            return True
        for stage in ("qualitative", "scenario"):
            details = result.get("stages", {}).get(stage, {})
            if (
                details.get("status") == "failed"
                and (details.get("attempts", 0) or 0) >= 2
                and details.get("validation_results")
            ):
                return True
        return False

    @staticmethod
    def _update_stage_timings(result):
        result["stage_timings_seconds"] = {
            stage: details["duration_seconds"]
            for stage, details in result.get("stages", {}).items()
            if details.get("duration_seconds") is not None
        }
        result["model_call_count"] = sum(
            details.get("attempts", 0) or 0
            for stage, details in result.get("stages", {}).items()
            if stage in {"qualitative", "scenario"}
        )
        result["semantic_model_call_count"] = result["model_call_count"]
        result["validation_failure_count"] = sum(
            max(0, (details.get("attempts", 0) or 0) - 1)
            for stage, details in result.get("stages", {}).items()
            if stage in {"qualitative", "scenario"}
        )

    def _record_elapsed(self, result, job_id):
        started = self._job_starts.pop(job_id, None)
        if started is not None:
            result["elapsed_seconds"] = result.get("elapsed_seconds", 0.0) + max(
                0.0, self.timer() - started
            )

    @staticmethod
    def _reproducibility_manifest(result, candidate, metadata):
        deterministic_policy_versions = {}
        for section, value in asdict(candidate)["full_results"].items():
            if isinstance(value, dict):
                for raw_key, item in value.items():
                    key = str(raw_key)
                    if key.endswith("policy_version") or key == "model_version":
                        if isinstance(item, str) and item:
                            deterministic_policy_versions[f"{section}.{key}"] = item
        return {
            "packet_hash": result.get("packet_hash"),
            "settings": dict(result.get("settings") or {}),
            "prompt_contract_versions": {
                stage: details.get("prompt_contract_version")
                for stage, details in result.get("stages", {}).items()
                if stage in {"qualitative", "scenario"}
                and details.get("prompt_contract_version")
            },
            "stage_input_sha256": {
                stage: details.get("base_prompt_sha256")
                for stage, details in result.get("stages", {}).items()
                if stage in {"qualitative", "scenario"}
                and details.get("base_prompt_sha256")
            },
            "raw_stage_analysis_ids": {
                "qualitative": list(
                    result.get("stages", {})
                    .get("qualitative", {})
                    .get("raw_analysis_ids", [])
                ),
                "scenario": list(
                    result.get("stages", {})
                    .get("scenario", {})
                    .get("raw_analysis_ids", [])
                ),
            },
            "policy_versions": {
                "qualitative": {
                    output_key: metadata.get(input_key)
                    for output_key, input_key in (
                        ("name", "policy_name"),
                        ("version", "policy_version"),
                        ("sha256", "policy_sha256"),
                    )
                    if metadata.get(input_key)
                },
                "scenario": {
                    output_key: metadata.get(input_key)
                    for output_key, input_key in (
                        ("name", "scenario_policy_name"),
                        ("version", "scenario_policy_version"),
                        ("sha256", "scenario_policy_sha256"),
                    )
                    if metadata.get(input_key)
                },
                "deterministic": deterministic_policy_versions,
            },
        }

    @staticmethod
    def _candidate_from_packet(packet_json):
        payload = deserialize_packet(packet_json)
        fields = {
            field: payload[field]
            for field in (
                "rank", "company_id", "ticker", "name", "ranking_model",
                "rank_eligible", "eligibility_reasons", "total_score",
                "score_breakdown", "data_quality", "flags", "candidate_reason",
                "positives", "negatives", "missing_data", "full_results",
                "research_evidence",
            )
        }
        return AgentCandidate(**fields)
