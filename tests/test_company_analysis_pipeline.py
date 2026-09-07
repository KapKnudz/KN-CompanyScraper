from datetime import datetime, timezone
from hashlib import sha256
from types import SimpleNamespace

import pytest

from kncompanyscraper.analysis.agent.agent_analysis_service import QualitativeStageResult
from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.prompt_builder import AgentPrompt
from kncompanyscraper.analysis.agent.scenario_authoring import ScenarioAuthoringError
from kncompanyscraper.analysis.company_analysis_pipeline import CompanyAnalysisPipeline
from kncompanyscraper.models.refresh import CompanyRefreshResult


def company(company_id):
    return SimpleNamespace(
        id=company_id,
        ticker=f"C{company_id}",
        name=f"Company {company_id}",
        branch_id=None,
    )


def refresh_result(company_id, *, blocked=False):
    return CompanyRefreshResult(
        company_id=company_id,
        domains=(),
        limitations=(),
        blocked_before_model=blocked,
    )


class JobStore:
    def __init__(self):
        self.jobs = {}
        self.next_id = 100

    def start(self, job_type, company_id):
        job_id = self.next_id
        self.next_id += 1
        self.jobs[job_id] = {
            "id": job_id,
            "job_type": job_type,
            "status": "running",
            "company_id": company_id,
            "result": {},
            "error": None,
        }
        return job_id

    def update_result(self, job_id, result):
        self.jobs[job_id]["result"] = result

    def mark_running(self, job_id):
        self.jobs[job_id]["status"] = "running"

    def complete(self, job_id, result=None):
        self.jobs[job_id].update(status="success", result=result or {})

    def fail(self, job_id, error, result=None):
        self.jobs[job_id].update(status="failed", error=error, result=result or {})

    def get(self, job_id):
        return self.jobs.get(job_id)


class Refresh:
    def __init__(self, blocked_ids=(), raising_ids=()):
        self.calls = []
        self.blocked_ids = set(blocked_ids)
        self.raising_ids = set(raising_ids)

    def refresh(self, companies):
        company = companies[0]
        self.calls.append(company.id)
        if company.id in self.raising_ids:
            raise TimeoutError("refresh timed out")
        return (refresh_result(company.id, blocked=company.id in self.blocked_ids),)


class Snapshot:
    def __init__(self):
        self.calls = []

    def analyze(self, companies):
        company = companies[0]
        self.calls.append(company.id)
        snapshot = SimpleNamespace(
            results={
                "reverse_dcf": {
                    "status": "available",
                    "policy_version": "reverse-dcf-test-v1",
                },
                "peer_comparison": {company.id: {"score": 1}},
            }
        )
        return SimpleNamespace(
            snapshots=(snapshot,),
            diagnostics=lambda: {"deterministic_duration_seconds": 0.01},
        )


class Context:
    def build_company(self, company, results):
        return AgentCandidate(
            rank=0,
            company_id=company.id,
            ticker=company.ticker,
            name=company.name,
            ranking_model="general",
            full_results=results,
            research_evidence={"documents": [{"source_id": f"document:{company.id}"}]},
        )


class RawStore:
    def __init__(self):
        self.rows = {}

    def get_stock_analysis_raw(self, analysis_id):
        return self.rows.get(analysis_id)


class Agent:
    def __init__(self, raw_store, *, scenario_timeout=False):
        self.raw_response_repository = raw_store
        self.scenario_timeout = scenario_timeout
        self.qualitative_calls = 0
        self.scenario_calls = 0
        self.persist_calls = 0
        self.persisted_metadata = []
        self.qualitative = SimpleNamespace(to_dict=lambda: {"company_id": 1})

    def run_qualitative(self, candidate):
        self.qualitative_calls += 1
        raw_id = 501 + candidate.company_id
        self.raw_response_repository.rows[raw_id] = {
            "id": raw_id,
            "content": "frozen qualitative",
            "created_by": "model",
        }
        return QualitativeStageResult(
            self.qualitative,
            {
                "qualitative_raw_analysis_id": raw_id,
                "qualitative_raw_analysis_ids": [raw_id],
                "qualitative_attempts": 1,
                "qualitative_input_measurements": [
                    {
                        "byte_count": 20,
                        "character_count": 20,
                        "document_count": 1,
                        "token_estimate": 5,
                        "section_sizes": {"user": 20},
                        "input_sha256": f"qualitative-input-{candidate.company_id}",
                    }
                ],
                "policy_name": "qualitative-test-policy",
                "policy_version": "qualitative-test-v1",
                "policy_sha256": "qualitative-test-sha",
            },
            SimpleNamespace(
                model="model",
                response_id=f"qualitative-{candidate.company_id}",
                input_measurement={
                    "byte_count": 20,
                    "character_count": 20,
                    "document_count": 1,
                    "token_estimate": 5,
                    "section_sizes": {"user": 20},
                    "input_sha256": f"qualitative-input-{candidate.company_id}",
                },
            ),
        )

    def validate_qualitative_artifact(self, raw_response, candidate):
        assert raw_response == "frozen qualitative"
        return self.qualitative

    def run_scenario(self, candidate, qualitative, metadata):
        self.scenario_calls += 1
        if self.scenario_timeout:
            self.scenario_timeout = False
            raise TimeoutError("scenario timed out")
        metadata.update(
            {
                "scenario_authoring_raw_analysis_ids": [701],
                "scenario_authoring_attempts": 1,
                "scenario_policy_name": "scenario-test-policy",
                "scenario_policy_version": "scenario-test-v1",
                "scenario_policy_sha256": "scenario-test-sha",
                "scenario_input_hashes": ["scenario-input-sha"],
                "scenario_input_measurements": [
                    {
                        "byte_count": 10,
                        "character_count": 10,
                        "document_count": 0,
                        "token_estimate": 3,
                        "section_sizes": {"source_ids": 1},
                        "input_sha256": f"scenario-input-{candidate.company_id}",
                    }
                ],
            }
        )
        self.raw_response_repository.rows[701] = {
            "id": 701,
            "content": "frozen scenario",
            "created_by": "model",
        }
        return qualitative

    def rehydrate_scenario(self, candidate, qualitative, raw_response, metadata):
        assert raw_response == "frozen scenario"
        return qualitative

    def persist(self, candidate, qualitative, metadata, *, created_by):
        self.persist_calls += 1
        self.persisted_metadata.append(dict(metadata))
        return SimpleNamespace(analysis_id=801)


class PromptAwareAgent(Agent):
    def __init__(self, raw_store, *, scenario_timeout=False):
        super().__init__(raw_store, scenario_timeout=scenario_timeout)
        self.qualitative_prompts = []
        self.scenario_prompts = []
        self.prompt_generation = "original"

    def build_qualitative_prompt(self, candidate):
        return AgentPrompt(
            system=f"qualitative system {self.prompt_generation}",
            user=f"qualitative user {self.prompt_generation}",
            schema_name="stock_analysis",
            contract_version="qualitative-stage-prompt-test-v1",
        )

    def build_scenario_prompt(self, candidate, qualitative):
        return AgentPrompt(
            system=f"scenario system {self.prompt_generation}",
            user=f"scenario user {self.prompt_generation}",
            schema_name="scenario_authoring",
            contract_version="scenario-stage-prompt-test-v1",
        )

    def run_qualitative(self, candidate, *, prompt=None):
        self.qualitative_prompts.append(prompt)
        return super().run_qualitative(candidate)

    def run_scenario(self, candidate, qualitative, metadata, *, prompt=None):
        self.scenario_prompts.append(prompt)
        return super().run_scenario(candidate, qualitative, metadata)


class ScenarioAuditFailureAgent(Agent):
    def run_scenario(self, candidate, qualitative, metadata, *, prompt=None):
        error = ScenarioAuthoringError("scenario validation failed")
        error.stage_metadata = {
            "scenario_authoring_attempts": 2,
            "scenario_authoring_raw_analysis_ids": [702, 703],
            "scenario_input_hashes": ["scenario-base", "scenario-repair"],
            "scenario_input_measurements": [
                {"character_count": 10, "input_sha256": "scenario-base"},
                {"character_count": 20, "input_sha256": "scenario-repair"},
            ],
            "scenario_validation_errors": ["bad bundle", "scenario validation failed"],
            "scenario_model_response_ids": ["scenario-1", "scenario-2"],
            "scenario_policy_name": "scenario-policy",
            "scenario_policy_version": "scenario-v1",
            "scenario_policy_sha256": "scenario-sha",
        }
        raise error


class InterruptedScenarioAgent(Agent):
    def run_scenario(self, candidate, qualitative, metadata, *, prompt=None):
        self.scenario_calls += 1
        if self.scenario_calls == 1:
            error = TimeoutError("scenario repair timed out")
            error.stage_metadata = {
                "scenario_authoring_attempts": 1,
                "scenario_authoring_raw_analysis_ids": [702],
                "scenario_input_hashes": ["scenario-base"],
                "scenario_input_measurements": [
                    {"character_count": 10, "input_sha256": "scenario-base"}
                ],
                "scenario_validation_errors": ["bad bundle"],
                "scenario_model_response_ids": ["scenario-1"],
            }
            raise error
        assert metadata["scenario_authoring_attempts"] == 1
        metadata.update(
            {
                "scenario_authoring_attempts": 2,
                "scenario_authoring_raw_analysis_ids": [702, 703],
                "scenario_input_hashes": ["scenario-base", "scenario-resume"],
                "scenario_input_measurements": [
                    {"character_count": 10, "input_sha256": "scenario-base"},
                    {"character_count": 12, "input_sha256": "scenario-resume"},
                ],
                "scenario_validation_errors": ["bad bundle"],
                "scenario_model_response_ids": ["scenario-1", "scenario-2"],
            }
        )
        return qualitative


class CommittedAnalysisRepository:
    def __init__(self):
        self.analysis_id = None

    def get_stock_analysis_for_job(self, job_id):
        return self.analysis_id

    def get_thesis_revision_id(self, analysis_id):
        return 902


class CrashAfterCommitAgent(Agent):
    def __init__(self, raw_store):
        super().__init__(raw_store)
        self.repository = CommittedAnalysisRepository()
        self.execution_boundary = SimpleNamespace(analysis_repository=self.repository)

    def persist(self, candidate, qualitative, metadata, *, created_by):
        self.persist_calls += 1
        self.repository.analysis_id = 801
        raise TimeoutError("process interrupted after commit")


class Companies:
    def __init__(self, companies):
        self.companies = {item.id: item for item in companies}

    def get_by_id(self, company_id):
        return self.companies.get(company_id)


def pipeline(companies, *, refresh=None, agent=None, jobs=None):
    jobs = jobs or JobStore()
    refresh = refresh or Refresh()
    agent = agent or Agent(RawStore())
    return (
        CompanyAnalysisPipeline(
            Companies(companies),
            refresh,
            Snapshot(),
            Context(),
            agent,
            jobs,
            progress=lambda message: None,
        ),
        refresh,
        agent,
        jobs,
    )


def test_pipeline_runs_stages_in_order_and_starts_a_fresh_full_reassessment():
    companies = [company(1)]
    service, refresh, agent, jobs = pipeline(companies)
    events = []
    service.progress = events.append

    outcomes = service.run(
        companies,
        settings={"provider": "local", "model": "luna", "reasoning_effort": "high"},
        invocation={"company_ids": [1]},
    )
    service.run(companies, settings={"provider": "local"})

    assert [outcome.status for outcome in outcomes] == ["accepted"]
    assert len(jobs.jobs) == 2
    assert refresh.calls == [1, 1]
    assert agent.qualitative_calls == 2
    assert agent.scenario_calls == 2
    assert agent.persist_calls == 2
    assert [
        metadata["thesis_revision_type"] for metadata in agent.persisted_metadata
    ] == ["full_reassessment", "full_reassessment"]
    first_job = jobs.jobs[100]
    assert first_job["result"]["stages"]["qualitative"]["status"] == "accepted"
    assert first_job["result"]["stages"]["scenario"]["status"] == "accepted"
    assert first_job["result"]["stages"]["persistence"]["status"] == "accepted"
    assert first_job["result"]["stages"]["qualitative"]["attempts"] == 1
    assert first_job["result"]["stages"]["scenario"]["attempts"] == 1
    assert first_job["result"]["model_call_count"] == 2
    assert first_job["result"]["next_resumable_stage"] is None
    assert set(first_job["result"]["stage_timings_seconds"]) == {
        "refresh",
        "deterministic",
        "readiness",
        "packet",
        "qualitative",
        "scenario",
        "persistence",
    }
    assert first_job["result"]["elapsed_seconds"] >= 0
    assert first_job["result"]["settings"]["reasoning_effort"] == "high"
    stage_starts = [
        event for event in events if event.endswith(" started")
    ]
    assert stage_starts[:7] == [
        "C1: refresh started",
        "C1: deterministic started",
        "C1: readiness started",
        "C1: packet started",
        "C1: qualitative started",
        "C1: scenario started",
        "C1: persistence started",
    ]


def test_timeout_after_qualitative_acceptance_resumes_without_qualitative_call():
    companies = [company(1)]
    raw_store = RawStore()
    agent = Agent(raw_store, scenario_timeout=True)
    service, refresh, agent, jobs = pipeline(companies, agent=agent)

    first = service.run(companies)[0]
    assert first.status == "resumable"
    assert agent.qualitative_calls == 1
    assert agent.scenario_calls == 1
    assert agent.persist_calls == 0

    resumed = service.resume(first.job_id)
    assert resumed.status == "accepted"
    assert agent.qualitative_calls == 1
    assert agent.scenario_calls == 2
    assert agent.persist_calls == 1


def test_failed_scenario_persists_attempt_audit_without_regenerating_qualitative():
    agent = ScenarioAuditFailureAgent(RawStore())
    service, _, _, jobs = pipeline([company(1)], agent=agent)
    events = []
    service.progress = events.append

    outcome = service.run([company(1)])[0]

    assert outcome.status == "failed"
    result = jobs.jobs[outcome.job_id]["result"]
    scenario = result["stages"]["scenario"]
    assert scenario["status"] == "failed"
    assert scenario["attempts"] == 2
    assert scenario["raw_analysis_ids"] == [702, 703]
    assert scenario["input_hashes"] == ["scenario-base", "scenario-repair"]
    assert scenario["validation_results"] == ["bad bundle", "scenario validation failed"]
    assert scenario["metadata"]["scenario_model_response_ids"] == [
        "scenario-1",
        "scenario-2",
    ]
    assert agent.qualitative_calls == 1
    assert agent.scenario_calls == 0
    assert result["next_resumable_stage"] is None
    assert result["semantic_model_call_count"] == 3
    assert not any("--resume-job-id" in event for event in events)

    result["stages"]["qualitative"]["attempts"] = 2
    result["semantic_model_call_count"] = 4
    result["model_call_count"] = 4

    with pytest.raises(ValueError, match="fresh explicit-company reassessment"):
        service.resume(outcome.job_id)

    assert agent.qualitative_calls == 1
    assert agent.scenario_calls == 0


def test_interrupted_scenario_resume_preserves_cumulative_attempt_audit():
    agent = InterruptedScenarioAgent(RawStore())
    service, _, _, jobs = pipeline([company(1)], agent=agent)

    first = service.run([company(1)])[0]
    assert first.status == "resumable"
    first_result = jobs.jobs[first.job_id]["result"]
    assert first_result["semantic_model_call_count"] == 2
    assert first_result["stages"]["scenario"]["attempts"] == 1

    resumed = service.resume(first.job_id)

    assert resumed.status == "accepted"
    result = jobs.jobs[first.job_id]["result"]
    assert result["semantic_model_call_count"] == 3
    assert result["stages"]["scenario"]["attempts"] == 2
    assert result["stages"]["scenario"]["raw_analysis_ids"] == [702, 703]
    assert result["stages"]["scenario"]["input_hashes"] == [
        "scenario-base",
        "scenario-resume",
    ]


def test_resume_uses_frozen_stage_prompts_after_prompt_builder_changes():
    agent = PromptAwareAgent(RawStore(), scenario_timeout=True)
    service, _, _, jobs = pipeline([company(1)], agent=agent)

    first = service.run([company(1)])[0]
    first_result = jobs.jobs[first.job_id]["result"]
    qualitative_artifact = first_result["stages"]["qualitative"]["base_prompt_artifact"]
    scenario_artifact = first_result["stages"]["scenario"]["base_prompt_artifact"]
    assert first_result["stages"]["qualitative"]["prompt_contract_version"] == (
        "qualitative-stage-prompt-test-v1"
    )
    assert first_result["stages"]["scenario"]["prompt_contract_version"] == (
        "scenario-stage-prompt-test-v1"
    )
    assert sha256(qualitative_artifact.encode("utf-8")).hexdigest() == (
        first_result["stages"]["qualitative"]["base_prompt_sha256"]
    )
    assert sha256(scenario_artifact.encode("utf-8")).hexdigest() == (
        first_result["stages"]["scenario"]["base_prompt_sha256"]
    )

    agent.prompt_generation = "changed-after-timeout"
    service.context_builder.build_company = lambda *args: (_ for _ in ()).throw(
        AssertionError("resume rebuilt the packet")
    )
    resumed = service.resume(first.job_id)

    assert resumed.status == "accepted"
    assert len(agent.qualitative_prompts) == 1
    assert len(agent.scenario_prompts) == 2
    assert agent.qualitative_prompts[0].user == "qualitative user original"
    assert [prompt.user for prompt in agent.scenario_prompts] == [
        "scenario user original",
        "scenario user original",
    ]
    assert jobs.jobs[first.job_id]["result"]["stages"]["qualitative"][
        "base_prompt_artifact"
    ] == qualitative_artifact
    assert jobs.jobs[first.job_id]["result"]["stages"]["scenario"][
        "base_prompt_artifact"
    ] == scenario_artifact
    assert jobs.jobs[first.job_id]["result"]["reproducibility"][
        "prompt_contract_versions"
    ] == {
        "qualitative": "qualitative-stage-prompt-test-v1",
        "scenario": "scenario-stage-prompt-test-v1",
    }


def test_corrupt_frozen_prompt_artifact_blocks_resume_with_integrity_error():
    agent = PromptAwareAgent(RawStore(), scenario_timeout=True)
    service, _, _, jobs = pipeline([company(1)], agent=agent)

    first = service.run([company(1)])[0]
    jobs.jobs[first.job_id]["result"]["stages"]["scenario"][
        "base_prompt_artifact"
    ] += "corrupt"

    resumed = service.resume(first.job_id)

    assert resumed.status == "failed"
    assert "stage scenario frozen prompt artifact hash mismatch" in resumed.error
    assert jobs.jobs[first.job_id]["result"]["next_resumable_stage"] is None
    assert agent.qualitative_calls == 1
    assert agent.scenario_calls == 1
    assert agent.persist_calls == 0


def test_resuming_completed_job_does_not_persist_again():
    service, refresh, agent, jobs = pipeline([company(1)])
    accepted = service.run([company(1)])[0]
    call_counts = (agent.qualitative_calls, agent.scenario_calls)

    already_completed = service.resume(accepted.job_id)

    assert already_completed.status == "already-completed"
    assert agent.persist_calls == 1
    assert (agent.qualitative_calls, agent.scenario_calls) == call_counts
    assert len(jobs.jobs) == 1


def test_resume_after_commit_before_checkpoint_does_not_create_a_second_analysis():
    agent = CrashAfterCommitAgent(RawStore())
    service, refresh, agent, jobs = pipeline([company(1)], agent=agent)

    first = service.run([company(1)])[0]
    resumed = service.resume(first.job_id)

    assert first.status == "resumable"
    assert resumed.status == "accepted"
    assert agent.persist_calls == 1
    assert resumed.analysis_id == 801
    assert resumed.thesis_revision_id == 902


def test_one_company_failure_does_not_stop_later_companies():
    companies = [company(1), company(2), company(3)]
    service, refresh, agent, jobs = pipeline(
        companies,
        refresh=Refresh(raising_ids={2}),
    )

    outcomes = service.run(companies)

    assert [outcome.status for outcome in outcomes] == [
        "accepted",
        "failed",
        "accepted",
    ]
    assert refresh.calls == [1, 2, 3]
    assert agent.persist_calls == 2
    assert jobs.jobs[100]["status"] == "success"
    assert jobs.jobs[100]["result"]["final_analysis_id"] == 801
    assert jobs.jobs[101]["status"] == "failed"


def test_successful_company_records_stage_audit_fields_and_model_settings():
    service, _, _, jobs = pipeline([company(1)])

    outcome = service.run(
        [company(1)],
        settings={"provider": "local", "model": "luna", "reasoning_effort": "high"},
    )[0]

    assert outcome.status == "accepted"
    result = jobs.jobs[outcome.job_id]["result"]
    for stage in result["stages"].values():
        assert stage["duration_seconds"] >= 0
        assert stage["model_settings"] == result["settings"]
    for stage_name, input_hash in (
        ("qualitative", "qualitative-input-1"),
        ("scenario", "scenario-input-1"),
    ):
        stage = result["stages"][stage_name]
        assert stage["input_measurements"]
        assert stage["input_hashes"] == [input_hash]
        assert stage["validation_results"] == []
    assert result["stages"]["qualitative"]["raw_analysis_ids"] == [502]
    assert result["stages"]["scenario"]["raw_analysis_ids"] == [701]


def test_mandatory_refresh_failure_blocks_model_and_is_reported_separately():
    service, refresh, agent, jobs = pipeline(
        [company(1)], refresh=Refresh(blocked_ids={1})
    )

    outcome = service.run([company(1)])[0]

    assert outcome.status == "blocked-before-model"
    assert agent.qualitative_calls == 0
    assert agent.scenario_calls == 0
    assert agent.persist_calls == 0
    assert jobs.jobs[outcome.job_id]["status"] == "failed"
    assert jobs.jobs[outcome.job_id]["result"]["stages"]["refresh"]["status"] == "failed"


def test_refresh_manifest_is_checkpointed_before_first_model_call_and_rollout_is_company_only():
    companies = [company(1)]
    jobs = JobStore()
    refresh = Refresh()
    service, _, agent, _ = pipeline(companies, refresh=refresh, jobs=jobs)
    observed = {}

    original_qualitative = agent.run_qualitative

    def check_refresh_checkpoint(candidate):
        observed.update(jobs.jobs[100]["result"])
        return original_qualitative(candidate)

    agent.run_qualitative = check_refresh_checkpoint
    service.run(companies)

    assert observed["refresh"]["blocked_before_model"] is False
    assert observed["stages"]["refresh"]["status"] == "accepted"
    assert "ranking_run" not in observed
    assert "agent_cohort" not in observed


def test_accepted_job_has_a_reproducibility_manifest_for_packet_outputs_and_policies():
    service, _, _, jobs = pipeline([company(1)])

    outcome = service.run(
        [company(1)],
        settings={"provider": "local", "model": "luna", "reasoning_effort": "high"},
    )[0]
    result = jobs.jobs[outcome.job_id]["result"]
    manifest = result["reproducibility"]

    assert manifest["packet_hash"] == result["packet_hash"]
    assert sha256(result["packet_json"].encode("utf-8")).hexdigest() == manifest[
        "packet_hash"
    ]
    assert manifest["settings"] == result["settings"]
    assert manifest["raw_stage_analysis_ids"] == {
        "qualitative": [502],
        "scenario": [701],
    }
    assert manifest["policy_versions"] == {
        "qualitative": {
            "name": "qualitative-test-policy",
            "version": "qualitative-test-v1",
            "sha256": "qualitative-test-sha",
        },
        "scenario": {
            "name": "scenario-test-policy",
            "version": "scenario-test-v1",
            "sha256": "scenario-test-sha",
        },
        "deterministic": {"reverse_dcf.policy_version": "reverse-dcf-test-v1"},
    }
    assert result["stages"]["scenario"]["metadata"]["scenario_input_hashes"] == [
        "scenario-input-sha"
    ]
    assert result["stages"]["scenario"]["metadata"]["scenario_input_measurements"][0][
        "section_sizes"
    ] == {"source_ids": 1}


def test_selector_resolution_rejects_duplicate_and_inactive_selectors_before_refresh():
    active = company(1)
    repository = SimpleNamespace(
        get_active_by_id=lambda company_id: active if company_id == 1 else None,
        get_active_by_ticker=lambda ticker: active if ticker == "C1" else None,
    )
    service = CompanyAnalysisPipeline(
        repository, None, None, None, None, None, progress=lambda message: None
    )

    with pytest.raises(ValueError, match="duplicate"):
        service.resolve_companies(company_ids=[1, 1])
    with pytest.raises(ValueError, match="unknown or inactive"):
        service.resolve_companies(company_ids=[2])
    assert service.resolve_companies(tickers=["c1"])[0] is active


class ShadowRun:
    run_id = "company-analysis-100"
    packet_hash = "packet-hash"
    results = ()

    def to_dict(self):
        return {"run_id": self.run_id, "packet_hash": self.packet_hash, "results": []}


class ShadowSpy:
    def __init__(self):
        self.calls = 0

    def run(self, packet, *, run_id, packet_hash):
        self.calls += 1
        assert packet.company_id == 1
        assert packet_hash
        return ShadowRun()


def test_shadow_specialists_are_opt_in_and_do_not_change_authoritative_result():
    companies = [company(1)]
    service, _, agent, jobs = pipeline(companies)
    shadow = ShadowSpy()
    service.shadow_specialist_runner = shadow

    off = service.run(companies)[0]
    assert off.status == "accepted"
    assert shadow.calls == 0
    assert "shadow_specialists" not in jobs.jobs[100]["result"]["stages"]

    service.shadow_specialists_enabled = True
    on = service.run(companies)[0]
    assert on.status == "accepted"
    assert shadow.calls == 1
    assert jobs.jobs[101]["result"]["stages"]["shadow_specialists"]["status"] == "accepted"
    assert jobs.jobs[101]["result"]["final_analysis_id"] == 801
    assert agent.persisted_metadata[-1]["analysis_mode"] == "initial"
