import json
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from kncompanyscraper.analysis.agent.agent_analysis_service import AgentAnalysisService
from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.codex_exec import CodexExecAdapter
from kncompanyscraper.analysis.agent.execution_boundary import AgentExecutionBoundary
from kncompanyscraper.analysis.agent.openai_responses import OpenAIModelResponse
from kncompanyscraper.analysis.agent.prompt_builder import AgentPrompt
from kncompanyscraper.analysis.agent.scenario_authoring import (
    ScenarioAuthoringPromptBuilder,
    ScenarioAuthoringService,
)
from kncompanyscraper.analysis.agent.result_parser import StockAnalysisValidationError
from kncompanyscraper.analysis.agent.result_parser import parse_scenario_authoring_result
from kncompanyscraper.analysis.agent.output_schema import (
    EvidenceCitation,
    scenario_authoring_json_schema,
)
from kncompanyscraper.analysis.valuation.forward_scenario import (
    ForwardScenarioEngine,
)
from tests.test_agent_result_boundary import valid_result
from tests.test_forward_scenario import valid_inputs
from tests.test_forward_scenario import assumption, debt_change_assumption


def scenario_response(bundles=None):
    return json.dumps(
        {
            "case_horizon_months": 36,
            "scenario_bundles": [
                asdict(bundle) for bundle in (bundles or valid_inputs().bundles)
            ],
        }
    )


def m0_scenario_fixture():
    return (
        Path(__file__).parent
        / "fixtures"
        / "stock_analysis"
        / "m0-valid-scenario.json"
    ).read_text(encoding="utf-8")


def scenario_candidate():
    return AgentCandidate(
        1,
        42,
        "TEST",
        "Testbolaget",
        full_results={
            "reverse_dcf": {
                "current_price": 10.0,
                "current_revenue": 100.0,
                "current_shares": 10.0,
                "current_net_debt": 0.0,
                "price_currency": "SEK",
                "financial_currency": "SEK",
            },
            "valuation": {
                "raw_ev_ebit": 8.0,
                "ev_ebit_guardrail_low": None,
                "ev_ebit_guardrail_high": None,
                "ev_ebit_base_ceiling": None,
                "ev_ebit_bull_ceiling": None,
            },
            "financial_history": {"scenario_history": {"source_ids": {}}},
        },
        research_evidence={"documents": [{"source_id": "report:2026-q2"}]},
    )


def test_scenario_prompt_contains_compact_deterministic_inputs():
    thesis = valid_result()
    thesis.case_horizon_months = 36

    prompt = ScenarioAuthoringPromptBuilder().build(
        scenario_candidate(),
        thesis,
    )
    packet = json.loads(prompt.user)

    assert packet["current_inputs"]["current_ev_ebit"] == 8.0
    assert packet["valuation_anchors"]["historical_terminal_multiple_range"] == [
        None,
        None,
    ]
    assert packet["deterministic_forward_readiness"]["status"] == "required"
    assert "price_range" not in packet["output_contract"]
    assert "calculated prices" in prompt.system
    assert "source_ids` whitelist" in packet["instructions"]
    assert "evidence_catalog" not in packet
    assert "citation_instructions" not in packet
    assert prompt.packet_measurement["section_sizes"]["source_ids"] > 0


def test_scenario_prompt_exposes_hard_methodology_constraints_and_schema_descriptions():
    thesis = valid_result()
    thesis.case_horizon_months = 36

    prompt = ScenarioAuthoringPromptBuilder().build(scenario_candidate(), thesis)
    packet = json.loads(prompt.user)
    constraints = packet["scenario_constraints"]
    schema = scenario_authoring_json_schema()
    net_debt_schema = schema["properties"]["scenario_bundles"]["items"][
        "properties"
    ]["net_debt_change"]

    assert constraints["all_cases_share_horizon"] is True
    assert constraints["deterministic_output_requirements"] == {
        "base_annualized_return_spread_max": 0.15,
        "calculated_by": "local_forward_scenario_engine",
        "model_must_not_author_calculated_outputs": True,
    }
    assert constraints["net_debt_change_provenance"]["zero_value"] == (
        "not_applicable"
    )
    assert constraints["net_debt_change_provenance"]["non_zero_values"] == [
        "source_backed",
        "analyst_sensitivity",
    ]
    assert "For `net_debt_change`" in packet["instructions"]
    assert "provenance_type` must be exactly `not_applicable`" in packet[
        "instructions"
    ]
    assert "use the selected `case_horizon_months` for all" in packet[
        "instructions"
    ]
    assert "zero" in net_debt_schema["description"]
    assert "not_applicable" in net_debt_schema["properties"]["provenance_type"][
        "description"
    ]


def test_m0_first_pass_fixture_uses_not_applicable_for_zero_net_debt():
    payload = parse_scenario_authoring_result(m0_scenario_fixture())
    zero_changes = [
        bundle.net_debt_change
        for bundle in payload["scenario_bundles"]
        if bundle.net_debt_change.value == 0
    ]
    assert len(zero_changes) == 1
    assert zero_changes[0].provenance_type == "not_applicable"

    candidate = scenario_candidate()
    candidate.research_evidence["documents"] = [
        {"source_id": "m0:report:114:2026-q2"}
    ]
    thesis = valid_result()
    thesis.case_horizon_months = 36
    adapter = MagicMock()
    adapter.generate.return_value = OpenAIModelResponse(
        "scenario-1", "test-model", m0_scenario_fixture(), {}
    )

    outcome = ScenarioAuthoringService(adapter).author(
        candidate,
        thesis,
        lambda qualitative, horizon, bundles: ForwardScenarioEngine().analyze(
            replace(
                valid_inputs(),
                case_horizon_months=horizon,
                bundles=tuple(bundles),
            )
        ),
    )

    assert outcome.attempts == 1
    assert adapter.generate.call_count == 1
    adapter.repair.assert_not_called()


def test_m2_msab_scenario_input_is_compact_without_catalog_duplication(
    msab_catalog_shape,
):
    candidate = scenario_candidate()
    candidate.full_results = msab_catalog_shape
    thesis = valid_result()
    thesis.case_horizon_months = 36

    prompt = ScenarioAuthoringPromptBuilder().build(candidate, thesis)
    full_input = CodexExecAdapter._input(prompt)

    assert len(full_input) <= 150_000
    assert "evidence_catalog" not in prompt.user
    assert "citation_instructions" not in prompt.user
    assert "full_results.financial_history.annual" not in prompt.user


def test_scenario_repair_isolated_from_documentary_and_qualitative_prompt_text():
    thesis = valid_result()
    thesis.case_horizon_months = 36
    candidate = scenario_candidate()
    candidate.research_evidence["documents"][0]["text"] = "PRIVATE REPORT BODY"
    invalid = list(valid_inputs().bundles)
    invalid[1] = replace(
        invalid[1],
        revenue_cagr=replace(invalid[1].revenue_cagr, value=0.20),
    )
    adapter = MagicMock()
    adapter.generate.return_value = OpenAIModelResponse(
        "scenario-1", "test-model", scenario_response(invalid), {}
    )
    adapter.repair.return_value = OpenAIModelResponse(
        "scenario-2", "test-model", scenario_response(), {}
    )

    ScenarioAuthoringService(adapter).author(
        candidate,
        thesis,
        lambda qualitative, horizon, bundles: ForwardScenarioEngine().analyze(
            replace(valid_inputs(), bundles=tuple(bundles))
        ),
    )

    repair_prompt = json.loads(adapter.repair.call_args.args[0].user)
    assert "PRIVATE REPORT BODY" not in adapter.repair.call_args.args[0].user
    assert "evidence_catalog" not in repair_prompt
    assert "citation_instructions" not in repair_prompt
    assert "# Policy provenance" not in adapter.repair.call_args.args[0].user


def test_scenario_authoring_repairs_rejected_bundles_once():
    first_bundles = list(valid_inputs().bundles)
    first_bundles[1] = replace(
        first_bundles[1],
        revenue_cagr=replace(first_bundles[1].revenue_cagr, value=0.20),
    )
    adapter = MagicMock()
    adapter.generate.return_value = OpenAIModelResponse(
        "scenario-1", "test-model", scenario_response(first_bundles), {}
    )
    adapter.repair.return_value = OpenAIModelResponse(
        "scenario-2", "test-model", scenario_response(), {}
    )
    raw_repository = MagicMock()
    raw_repository.save_stock_analysis_raw.side_effect = [91, 92]
    thesis = valid_result()
    thesis.case_horizon_months = 36
    qualitative_snapshot = thesis.to_dict()
    qualitative_snapshot.pop("scenario_bundles")
    qualitative_snapshot.pop("forward_scenario_analysis")
    inputs = valid_inputs()

    def validate(qualitative, horizon, bundles):
        return ForwardScenarioEngine().analyze(replace(inputs, bundles=tuple(bundles)))

    outcome = ScenarioAuthoringService(
        adapter,
        raw_response_repository=raw_repository,
    ).author(scenario_candidate(), thesis, validate)

    assert outcome.attempts == 2
    adapter.repair.assert_called_once()
    assert outcome.analysis.status == "available"
    assert raw_repository.update_raw_validation.call_count == 2
    assert raw_repository.update_raw_validation.call_args_list[0].args[1] == "rejected"
    assert raw_repository.update_raw_validation.call_args_list[1].args[1] == "accepted"
    repair_packet = json.loads(adapter.repair.call_args.args[0].user)
    assert thesis.to_dict() == {**qualitative_snapshot, "scenario_bundles": [], "forward_scenario_analysis": None}
    assert repair_packet["qualitative_thesis"]["management_credibility_ledger"][0][
        "source_ids"
    ] == []
    assert repair_packet["scenario_constraints"]["qualitative_thesis_is_immutable"] is True
    assert any(
        "scenario engine rejected authored bundles" in flag
        for flag in repair_packet["repair"]["methodology_flags"]
    )
    raw_metadata = [
        call.kwargs["metadata"]
        for call in raw_repository.save_stock_analysis_raw.call_args_list
    ]
    assert len(outcome.scenario_input_hashes) == 2
    assert len(set(outcome.scenario_input_hashes)) == 2
    assert len(outcome.scenario_input_measurements) == 2
    assert [item["scenario_input_sha256"] for item in raw_metadata] == list(
        outcome.scenario_input_hashes
    )
    assert all(
        set(item["scenario_input_measurement"])
        == {"byte_count", "character_count", "document_count", "token_estimate", "section_sizes"}
        for item in raw_metadata
    )


def test_avt_shaped_wide_base_band_gets_calculated_repair_diagnostic_and_passes():
    candidate = scenario_candidate()
    candidate.research_evidence["documents"][0]["text"] = "PRIVATE REPORT BODY"
    thesis = valid_result()
    thesis.case_horizon_months = 36
    qualitative_snapshot = thesis.to_dict()
    qualitative_snapshot.pop("scenario_bundles")
    qualitative_snapshot.pop("forward_scenario_analysis")

    base_inputs = valid_inputs()
    wide_base = replace(
        base_inputs.bundles[1],
        revenue_cagr=assumption(0.20),
        ebit_margin=assumption(0.28),
        terminal_ev_ebit_low=assumption(15.5565),
        terminal_ev_ebit_high=assumption(23.3902),
        net_debt_change=debt_change_assumption(-10.0),
        share_count_growth=assumption(0.0),
        distributions_per_share=assumption(0.10),
    )
    bear = replace(
        base_inputs.bundles[0],
        revenue_cagr=assumption(0.10),
        ebit_margin=assumption(0.20),
        terminal_ev_ebit_low=assumption(10.0),
        terminal_ev_ebit_high=assumption(12.0),
        net_debt_change=debt_change_assumption(0.0),
        share_count_growth=assumption(0.02),
        distributions_per_share=assumption(0.0),
    )
    bull = replace(
        base_inputs.bundles[2],
        revenue_cagr=assumption(0.25),
        ebit_margin=assumption(0.30),
        terminal_ev_ebit_low=assumption(24.0),
        terminal_ev_ebit_high=assumption(27.0),
        net_debt_change=debt_change_assumption(-15.0),
        share_count_growth=assumption(-0.01),
        distributions_per_share=assumption(1.0),
    )
    wide_bundles = (bear, wide_base, bull)
    repaired_bundles = (
        bear,
        replace(wide_base, terminal_ev_ebit_high=assumption(21.0)),
        bull,
    )
    inputs = replace(
        base_inputs,
        current_price=29.587503210277426,
        current_revenue=100.0,
        current_shares=10.0,
        current_net_debt=-74.56328431065504,
        historical_terminal_multiple_range=(10.0, 27.0),
        base_terminal_multiple_ceiling=24.0,
        bull_terminal_multiple_ceiling=30.0,
        demonstrated_revenue_cagr=0.25,
        demonstrated_ebit_margin=0.30,
    )
    rejected = ForwardScenarioEngine().analyze(
        replace(inputs, bundles=wide_bundles)
    )
    assert rejected.status == "insufficient_evidence"
    assert rejected.band("base").low_annualized_return == pytest.approx(0.414995)
    assert rejected.band("base").high_annualized_return == pytest.approx(0.602360)
    assert (
        rejected.band("base").high_annualized_return
        - rejected.band("base").low_annualized_return
    ) == pytest.approx(0.187365)

    adapter = MagicMock()
    first_output = scenario_response(wide_bundles)
    adapter.generate.return_value = OpenAIModelResponse(
        "scenario-1", "test-model", first_output, {}
    )
    adapter.repair.return_value = OpenAIModelResponse(
        "scenario-2", "test-model", scenario_response(repaired_bundles), {}
    )

    outcome = ScenarioAuthoringService(adapter).author(
        candidate,
        thesis,
        lambda qualitative, horizon, bundles: ForwardScenarioEngine().analyze(
            replace(inputs, bundles=tuple(bundles))
        ),
    )

    assert outcome.analysis.status == "available"
    assert outcome.attempts == 2
    repair_packet = json.loads(adapter.repair.call_args.args[0].user)
    diagnostic = repair_packet["repair"]["deterministic_output_diagnostic"]
    assert diagnostic["case"] == "base"
    assert diagnostic["low_annualized_return"] == pytest.approx(0.414995)
    assert diagnostic["high_annualized_return"] == pytest.approx(0.602360)
    assert diagnostic["spread"] == pytest.approx(0.187365)
    assert diagnostic["maximum_spread"] == 0.15
    assert diagnostic["excess_spread"] == pytest.approx(0.037365)
    assert thesis.to_dict() == {**qualitative_snapshot, "scenario_bundles": [], "forward_scenario_analysis": None}
    assert repair_packet["case_horizon_months"] == 36
    assert repair_packet["repair"]["previous_bundles"] == json.loads(
        first_output
    )
    assert "evidence_catalog" not in repair_packet
    assert "PRIVATE REPORT BODY" not in adapter.repair.call_args.args[0].user
    assert repaired_bundles[1].terminal_ev_ebit_high.value == 21.0


def test_scenario_projection_exposes_only_whitelisted_structured_source_ids():
    candidate = scenario_candidate()
    allowed_document = "report:2026-q2"
    allowed_financial = "financial:r12:2025-12-31"
    forbidden_alias = "deterministic:reverse_dcf:operating_history"
    candidate.full_results["financial_history"]["scenario_history"] = {
        "source_ids": {"revenue": [allowed_financial]},
    }
    thesis = valid_result()
    thesis.case_horizon_months = 36
    thesis.management_credibility_ledger[0].source_ids = [
        allowed_document,
        forbidden_alias,
    ]
    thesis.management_credibility_ledger[0].claim_source_ids = [forbidden_alias]
    thesis.citations = [
        EvidenceCitation(allowed_financial, "Allowed history."),
        EvidenceCitation(forbidden_alias, "Forbidden aggregate alias."),
    ]
    original = thesis.to_dict()

    packet = json.loads(ScenarioAuthoringPromptBuilder().build(candidate, thesis).user)

    visible = []

    def collect(value, field=None):
        if isinstance(value, dict):
            for key, nested in value.items():
                collect(nested, key)
        elif isinstance(value, list):
            for nested in value:
                collect(nested, field)
        elif isinstance(value, str) and field and (
            field == "source_id" or field.endswith("source_ids")
        ):
            visible.append(value)

    collect(
        {
            key: value
            for key, value in packet.items()
            if key not in {"instructions", "output_contract"}
        }
    )
    assert set(visible).issubset(set(packet["source_ids"]))
    assert allowed_document in visible
    assert allowed_financial in visible
    assert forbidden_alias not in visible
    assert thesis.to_dict() == original


def test_scenario_authoring_allows_one_bounded_repair():
    invalid = list(valid_inputs().bundles)
    invalid[1] = replace(
        invalid[1],
        revenue_cagr=replace(invalid[1].revenue_cagr, value=0.20),
    )
    adapter = MagicMock()
    adapter.generate.return_value = OpenAIModelResponse(
        "scenario-1", "test-model", scenario_response(invalid), {}
    )
    adapter.repair.return_value = OpenAIModelResponse(
        "scenario-2", "test-model", scenario_response(invalid), {}
    )
    thesis = valid_result()
    thesis.case_horizon_months = 36
    inputs = valid_inputs()

    with pytest.raises(StockAnalysisValidationError, match="scenario engine rejected"):
        ScenarioAuthoringService(adapter).author(
            scenario_candidate(),
            thesis,
            lambda qualitative, horizon, bundles: ForwardScenarioEngine().analyze(
                replace(inputs, bundles=tuple(bundles))
            ),
        )

    assert adapter.generate.call_count == 1
    assert adapter.repair.call_count == 1


def test_interrupted_scenario_repair_resumes_with_one_remaining_attempt():
    invalid = list(valid_inputs().bundles)
    invalid[1] = replace(
        invalid[1],
        revenue_cagr=replace(invalid[1].revenue_cagr, value=0.20),
    )
    adapter = MagicMock()
    adapter.generate.side_effect = [
        OpenAIModelResponse(
            "scenario-1", "test-model", scenario_response(invalid), {}
        ),
        OpenAIModelResponse(
            "scenario-2", "test-model", scenario_response(), {}
        ),
    ]
    adapter.repair.side_effect = TimeoutError("repair timed out")
    service = ScenarioAuthoringService(adapter)
    thesis = valid_result()
    thesis.case_horizon_months = 36
    inputs = valid_inputs()

    def validate(qualitative, horizon, bundles):
        return ForwardScenarioEngine().analyze(
            replace(inputs, bundles=tuple(bundles))
        )

    with pytest.raises(TimeoutError) as interrupted:
        service.author(scenario_candidate(), thesis, validate)

    assert interrupted.value.stage_metadata["scenario_authoring_attempts"] == 1
    outcome = service.author(
        scenario_candidate(),
        thesis,
        validate,
        prior_metadata=interrupted.value.stage_metadata,
    )

    assert outcome.attempts == 2
    assert outcome.scenario_validation_errors
    assert adapter.generate.call_count == 2
    assert adapter.repair.call_count == 1


def test_interrupted_qualitative_repair_resumes_with_one_remaining_attempt():
    thesis = valid_result()
    adapter = MagicMock()
    adapter.generate.side_effect = [
        OpenAIModelResponse("qualitative-1", "test-model", "invalid", {}),
        OpenAIModelResponse("qualitative-2", "test-model", "valid", {}),
    ]
    adapter.repair.side_effect = TimeoutError("repair timed out")
    boundary = MagicMock()
    boundary.validate_qualitative_response.side_effect = [
        StockAnalysisValidationError("unknown source"),
        thesis,
    ]
    readiness = MagicMock()
    service = AgentAnalysisService(
        adapter,
        boundary,
        MagicMock(build=MagicMock(return_value=AgentPrompt(system="p", user="c"))),
        readiness_gate=readiness,
    )

    with pytest.raises(TimeoutError) as interrupted:
        service.run_qualitative(scenario_candidate())

    assert interrupted.value.stage_metadata["qualitative_attempts"] == 1
    outcome = service.run_qualitative(
        scenario_candidate(), prior_metadata=interrupted.value.stage_metadata
    )

    assert outcome.metadata["qualitative_attempts"] == 2
    assert outcome.metadata["qualitative_validation_errors"] == ["unknown source"]
    assert adapter.generate.call_count == 2
    assert adapter.repair.call_count == 1


def test_failed_scenario_attempts_expose_bounded_audit_metadata():
    invalid = list(valid_inputs().bundles)
    invalid[1] = replace(
        invalid[1],
        revenue_cagr=replace(invalid[1].revenue_cagr, value=0.20),
    )
    adapter = MagicMock()
    adapter.generate.return_value = OpenAIModelResponse(
        "scenario-1", "test-model", scenario_response(invalid), {}
    )
    adapter.repair.return_value = OpenAIModelResponse(
        "scenario-2", "test-model", scenario_response(invalid), {}
    )
    raw_repository = MagicMock()
    raw_repository.save_stock_analysis_raw.side_effect = [91, 92]
    thesis = valid_result()
    thesis.case_horizon_months = 36
    inputs = valid_inputs()

    with pytest.raises(StockAnalysisValidationError) as raised:
        ScenarioAuthoringService(
            adapter,
            raw_response_repository=raw_repository,
        ).author(
            scenario_candidate(),
            thesis,
            lambda qualitative, horizon, bundles: ForwardScenarioEngine().analyze(
                replace(inputs, bundles=tuple(bundles))
            ),
        )

    audit = raised.value.stage_metadata
    assert audit["scenario_authoring_attempts"] == 2
    assert audit["scenario_authoring_raw_analysis_ids"] == [91, 92]
    assert audit["scenario_model_response_ids"] == ["scenario-1", "scenario-2"]
    assert len(audit["scenario_input_hashes"]) == 2
    assert len(audit["scenario_input_measurements"]) == 2
    assert len(audit["scenario_validation_errors"]) == 2
    assert audit["scenario_policy_version"] == "scenario-authoring-v3"


def test_agent_analysis_service_persists_only_after_scenario_enrichment():
    thesis = valid_result()
    thesis.case_horizon_months = 36
    main_payload = thesis.to_dict()
    main_payload.pop("scenario_bundles")
    main_payload.pop("forward_scenario_analysis")
    main_response = json.dumps(main_payload)
    adapter = MagicMock()
    adapter.generate.side_effect = [
        OpenAIModelResponse("main-1", "test-model", main_response, {}),
        OpenAIModelResponse("scenario-1", "test-model", scenario_response(), {}),
    ]
    prompt_builder = MagicMock()
    prompt_builder.build.return_value = AgentPrompt(system="policy", user="candidate")
    boundary = MagicMock()
    boundary.calculate_forward_scenario.side_effect = (
        lambda result, candidate: ForwardScenarioEngine().analyze(
            replace(valid_inputs(), bundles=tuple(result.scenario_bundles))
        )
    )
    boundary.validate_qualitative_response.return_value = thesis
    boundary.persist_validated_result.return_value = SimpleNamespace(analysis_id=55)

    result = AgentAnalysisService(
        adapter,
        boundary,
        prompt_builder,
        scenario_authoring_service=ScenarioAuthoringService(adapter),
    ).analyze([scenario_candidate()])

    assert result[0].analysis_id == 55
    assert adapter.generate.call_count == 2
    assert [
        call.args[0].schema_name for call in adapter.generate.call_args_list
    ] == ["stock_analysis", "scenario_authoring"]
    adapter.repair.assert_not_called()
    persisted = boundary.persist_validated_result.call_args.args[0]
    assert len(persisted.scenario_bundles) == 3
    assert persisted.forward_scenario_analysis.status == "available"
    boundary.validate_forward_scenario_sources.assert_called_once()


def test_agent_analysis_service_validates_verdict_coherence_before_persistence():
    thesis = valid_result()
    thesis.case_horizon_months = 36
    thesis.verdict = "latent_case"
    thesis.latent_case_type = "price"
    thesis.activation_trigger = "The valuation reaches the entry level."
    thesis.activation_trigger_spec = valid_result().activation_trigger_spec
    adapter = MagicMock()
    adapter.generate.return_value = OpenAIModelResponse(
        "scenario-1", "test-model", scenario_response(), {}
    )
    adapter.repair.return_value = OpenAIModelResponse(
        "scenario-2", "test-model", scenario_response(), {}
    )
    boundary = MagicMock()
    boundary.calculate_forward_scenario.return_value = SimpleNamespace(
        status="available",
        methodology_flags=(),
        band=lambda case: SimpleNamespace(case=case),
    )
    coherence_error = StockAnalysisValidationError(
        "verdict coherence conflict: price latent cannot claim economically sufficient current-price returns"
    )
    coherence_error.deterministic_output_diagnostic = {
        "type": "verdict_coherence",
        "verdict": "latent_case",
        "latent_case_type": "price",
        "base_annualized_return_range": [0.1433, 0.1433],
        "required_return": 0.135,
        "conflict": "price latent cannot claim economically sufficient current-price returns",
    }
    boundary.validate_verdict_coherence.side_effect = coherence_error

    service = AgentAnalysisService(
        adapter,
        boundary,
        scenario_authoring_service=ScenarioAuthoringService(adapter),
    )

    with pytest.raises(StockAnalysisValidationError, match="verdict coherence"):
        service.run_scenario(scenario_candidate(), thesis, {})

    assert boundary.validate_verdict_coherence.call_count == 2
    boundary.persist_validated_result.assert_not_called()
    repair_packet = json.loads(adapter.repair.call_args.args[0].user)
    assert repair_packet["repair"]["deterministic_output_diagnostic"] == (
        coherence_error.deterministic_output_diagnostic
    )
    assert "price-latent case must have" in repair_packet["repair"]["instruction"]


def test_agent_analysis_service_does_not_regenerate_scenario_after_qualitative_repair():
    thesis = valid_result()
    thesis.case_horizon_months = 36
    payload = thesis.to_dict()
    payload.pop("scenario_bundles")
    payload.pop("forward_scenario_analysis")
    response_text = json.dumps(payload)
    first = OpenAIModelResponse("main-1", "test-model", response_text, {})
    repaired_payload = {**payload, "case_horizon_months": 48}
    repaired = OpenAIModelResponse(
        "main-2", "test-model", json.dumps(repaired_payload), {}
    )
    adapter = MagicMock(max_repair_attempts=1)
    adapter.generate.return_value = first
    adapter.repair.return_value = repaired
    boundary = MagicMock()
    boundary.validate_qualitative_response.side_effect = [
        StockAnalysisValidationError("qualitative citation error"),
        thesis,
    ]
    boundary.calculate_forward_scenario.return_value = SimpleNamespace(status="available")
    boundary.persist_validated_result.return_value = SimpleNamespace(analysis_id=56)
    authoring = MagicMock()
    authoring.author.return_value = SimpleNamespace(
        case_horizon_months=36,
        scenario_bundles=valid_inputs().bundles,
        analysis=SimpleNamespace(status="available"),
        attempts=1,
        raw_analysis_ids=(91,),
    )

    result = AgentAnalysisService(
        adapter,
        boundary,
        MagicMock(build=MagicMock(return_value=AgentPrompt(system="p", user="c"))),
        scenario_authoring_service=authoring,
    ).analyze([scenario_candidate()])

    assert result[0].analysis_id == 56
    authoring.author.assert_called_once()
    assert adapter.repair.call_count == 1


def test_agent_analysis_service_caps_full_job_at_four_semantic_calls():
    thesis = valid_result()
    thesis.case_horizon_months = 36
    invalid_bundles = list(valid_inputs().bundles)
    invalid_bundles[1] = replace(
        invalid_bundles[1],
        revenue_cagr=replace(invalid_bundles[1].revenue_cagr, value=0.20),
    )
    qualitative_payload = thesis.to_dict()
    qualitative_payload.pop("scenario_bundles")
    qualitative_payload.pop("forward_scenario_analysis")
    adapter = MagicMock()
    adapter.generate.side_effect = [
        OpenAIModelResponse("qual-1", "test-model", "invalid qualitative", {}),
        OpenAIModelResponse("scenario-1", "test-model", scenario_response(invalid_bundles), {}),
    ]
    adapter.repair.side_effect = [
        OpenAIModelResponse("qual-2", "test-model", json.dumps(qualitative_payload), {}),
        OpenAIModelResponse("scenario-2", "test-model", scenario_response(), {}),
    ]
    boundary = MagicMock()
    boundary.validate_qualitative_response.side_effect = [
        StockAnalysisValidationError("qualitative source failure"),
        thesis,
    ]
    boundary.validate_forward_scenario_sources.side_effect = None
    boundary.calculate_forward_scenario.side_effect = [
        SimpleNamespace(status="insufficient_evidence", methodology_flags=("bad",)),
        SimpleNamespace(status="available"),
    ]
    boundary.persist_validated_result.return_value = SimpleNamespace(analysis_id=57)

    result = AgentAnalysisService(
        adapter,
        boundary,
        MagicMock(build=MagicMock(return_value=AgentPrompt(system="p", user="c"))),
        scenario_authoring_service=ScenarioAuthoringService(adapter),
    ).analyze([scenario_candidate()])

    assert result[0].analysis_id == 57
    assert adapter.generate.call_count == 2
    assert adapter.repair.call_count == 2
    assert boundary.persist_validated_result.call_count == 1


def test_qualitative_failure_stops_before_scenario_authoring():
    adapter = MagicMock()
    adapter.generate.return_value = OpenAIModelResponse(
        "qual-1", "test-model", "invalid qualitative", {}
    )
    adapter.repair.return_value = OpenAIModelResponse(
        "qual-2", "test-model", "still invalid qualitative", {}
    )
    boundary = MagicMock()
    boundary.validate_qualitative_response.side_effect = StockAnalysisValidationError(
        "qualitative source failure"
    )
    authoring = MagicMock()

    with pytest.raises(StockAnalysisValidationError, match="qualitative source failure"):
        AgentAnalysisService(
            adapter,
            boundary,
            MagicMock(build=MagicMock(return_value=AgentPrompt(system="p", user="c"))),
            scenario_authoring_service=authoring,
        ).analyze([scenario_candidate()])

    assert adapter.generate.call_count == 1
    assert adapter.repair.call_count == 1
    authoring.author.assert_not_called()
    boundary.persist_validated_result.assert_not_called()


def test_scenario_failure_does_not_repair_or_regenerate_qualitative_stage():
    thesis = valid_result()
    thesis.case_horizon_months = 36
    invalid = list(valid_inputs().bundles)
    invalid[1] = replace(
        invalid[1],
        revenue_cagr=replace(invalid[1].revenue_cagr, value=0.20),
    )
    adapter = MagicMock()
    adapter.generate.side_effect = [
        OpenAIModelResponse("qual-1", "test-model", "qualitative", {}),
        OpenAIModelResponse("scenario-1", "test-model", scenario_response(invalid), {}),
    ]
    adapter.repair.return_value = OpenAIModelResponse(
        "scenario-2", "test-model", scenario_response(invalid), {}
    )
    boundary = MagicMock()
    boundary.validate_qualitative_response.return_value = thesis
    boundary.calculate_forward_scenario.return_value = SimpleNamespace(
        status="insufficient_evidence", methodology_flags=("bad scenario",)
    )

    with pytest.raises(StockAnalysisValidationError, match="scenario engine rejected"):
        AgentAnalysisService(
            adapter,
            boundary,
            MagicMock(build=MagicMock(return_value=AgentPrompt(system="p", user="c"))),
            scenario_authoring_service=ScenarioAuthoringService(adapter),
        ).analyze([scenario_candidate()])

    assert adapter.generate.call_count == 2
    assert adapter.repair.call_count == 1
    assert [
        call.args[0].schema_name for call in adapter.generate.call_args_list
    ] == ["stock_analysis", "scenario_authoring"]
    boundary.validate_qualitative_response.assert_called_once()
    assert adapter.repair.call_args.args[0].schema_name == "scenario_authoring"
    boundary.persist_validated_result.assert_not_called()


def test_forward_source_validation_rejects_unknown_assumption_before_calculation():
    inputs = valid_inputs()
    result = valid_result()
    bad_bear = replace(
        inputs.bundles[0],
        revenue_cagr=replace(
            inputs.bundles[0].revenue_cagr,
            source_ids=("financial:r12_ebit_margin_median",),
        ),
    )
    result.scenario_bundles = [bad_bear, *inputs.bundles[1:]]
    known_ids = {
        source_id
        for bundle in inputs.bundles
        for name in (
            "revenue_cagr",
            "ebit_margin",
            "terminal_ev_ebit_low",
            "terminal_ev_ebit_high",
            "net_debt_change",
            "share_count_growth",
            "distributions_per_share",
        )
        for source_id in getattr(bundle, name).source_ids
    }
    candidate = scenario_candidate()
    candidate.research_evidence["documents"] = [
        {"source_id": source_id} for source_id in known_ids
    ]

    with pytest.raises(
        StockAnalysisValidationError,
        match="financial:r12_ebit_margin_median",
    ):
        AgentExecutionBoundary.validate_forward_scenario_sources(result, candidate)


def test_forward_source_validation_uses_exact_scenario_whitelist_without_aliases():
    inputs = valid_inputs()
    result = valid_result()
    alias_like = "full_results.reverse_dcf.current_price"
    result.scenario_bundles = [
        replace(
            bundle,
            **{
                name: replace(getattr(bundle, name), source_ids=(alias_like,))
                for name in (
                    "revenue_cagr",
                    "ebit_margin",
                    "terminal_ev_ebit_low",
                    "terminal_ev_ebit_high",
                    "net_debt_change",
                    "share_count_growth",
                    "distributions_per_share",
                )
            },
        )
        for bundle in inputs.bundles
    ]

    with pytest.raises(
        StockAnalysisValidationError,
        match="full_results.reverse_dcf.current_price",
    ):
        AgentExecutionBoundary.validate_forward_scenario_sources(
            result,
            scenario_candidate(),
            source_whitelist={"report:2026-q2"},
        )


def test_scenario_compaction_preserves_deterministic_output_for_same_bundles():
    thesis = valid_result()
    thesis.case_horizon_months = 36
    adapter = MagicMock()
    adapter.generate.return_value = OpenAIModelResponse(
        "scenario-1", "test-model", scenario_response(), {}
    )
    inputs = valid_inputs()

    outcome = ScenarioAuthoringService(adapter).author(
        scenario_candidate(),
        thesis,
        lambda qualitative, horizon, bundles: ForwardScenarioEngine().analyze(
            replace(inputs, bundles=tuple(bundles))
        ),
    )

    expected = ForwardScenarioEngine().analyze(inputs)
    assert outcome.analysis == expected


def test_strict_boundary_rejects_a_completed_general_analysis_without_bands():
    candidate = scenario_candidate()
    candidate.research_evidence["documents"] = [{"source_id": "news:21"}]
    payload = valid_result()

    with pytest.raises(
        StockAnalysisValidationError,
        match="exactly three scenario bundles and three calculated bands",
    ):
        AgentExecutionBoundary(
            MagicMock(),
            require_mandatory_scenarios=True,
        ).persist_response(
            json.dumps(payload.to_dict()),
            candidate,
            created_by="test-model",
        )
