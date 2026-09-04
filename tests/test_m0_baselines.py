import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.agent_analysis_service import AgentAnalysisService
from kncompanyscraper.analysis.agent.execution_boundary import AgentExecutionBoundary
from kncompanyscraper.analysis.agent.openai_responses import OpenAIModelResponse
from kncompanyscraper.analysis.agent.packet_measurement import measure_packet, measure_text
from kncompanyscraper.analysis.agent.prompt_builder import AgentPrompt, AgentPromptBuilder
from kncompanyscraper.analysis.agent.result_parser import (
    StockAnalysisValidationError,
    parse_qualitative_stock_analysis_result,
    parse_scenario_authoring_result,
)
from kncompanyscraper.analysis.agent.scenario_authoring import (
    ScenarioAuthoringError,
    ScenarioAuthoringService,
)
from kncompanyscraper.analysis.valuation.forward_scenario import ForwardScenarioEngine
from kncompanyscraper.cli import agent
from tests.test_forward_scenario import valid_inputs


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "stock_analysis"


def load_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_m0_exact_company_selection_characterizes_current_full_watchlist_path(
    model_spy,
):
    watchlist_service = MagicMock()
    watchlist_service.analyze_watchlist.return_value = SimpleNamespace(
        ranking=SimpleNamespace(), results_by_company={}
    )
    context_builder = MagicMock()
    context_builder.build_shortlist.return_value = []
    analysis_service = MagicMock()

    args = SimpleNamespace(
        provider="local",
        model=None,
        reasoning_effort=None,
        max_candidates=1,
        company_ids=[114],
        retry_rejected=False,
        repair_rejected=False,
    )
    with (
        patch(
            "kncompanyscraper.composition.build_agent_model_adapter",
            return_value=model_spy,
        ),
        patch(
            "kncompanyscraper.composition.build_agent_analysis_service",
            return_value=analysis_service,
        ),
        patch(
            "kncompanyscraper.composition.build_watchlist_analysis_service",
            return_value=watchlist_service,
        ),
        patch(
            "kncompanyscraper.composition.build_agent_context_builder",
            return_value=context_builder,
        ),
    ):
        agent._cmd_analyze_shortlist(args)

    watchlist_service.analyze_watchlist.assert_called_once_with()
    context_builder.build_shortlist.assert_called_once_with(
        watchlist_service.analyze_watchlist.return_value.ranking,
        watchlist_service.analyze_watchlist.return_value.results_by_company,
        limit=1,
        company_ids=(114,),
    )
    analysis_service.analyze.assert_called_once_with([])
    assert model_spy.calls == []


def test_m0_response_fixtures_have_stable_synthetic_ids_and_expected_outcomes():
    valid_qualitative = parse_qualitative_stock_analysis_result(
        load_fixture("m0-valid-qualitative.json")
    )
    invalid_source = json.loads(load_fixture("m0-qualitative-source-id-failure.json"))
    valid_scenario = parse_scenario_authoring_result(
        load_fixture("m0-valid-scenario.json")
    )

    assert valid_qualitative.company_id == 114
    assert valid_qualitative.citations[0].source_id == "m0:report:114:2026-q2"
    assert all(
        citation.source_id.startswith("m0:")
        for citation in valid_qualitative.citations
    )
    assert invalid_source["citations"][0]["source_id"] == "m0:invented:source-999"
    assert valid_scenario["case_horizon_months"] == 36
    assert [bundle.case for bundle in valid_scenario["scenario_bundles"]] == [
        "bear",
        "base",
        "bull",
    ]
    assert all(
        source_id.startswith("m0:")
        for bundle in valid_scenario["scenario_bundles"]
        for assumption in (
            bundle.revenue_cagr,
            bundle.ebit_margin,
            bundle.terminal_ev_ebit_low,
            bundle.terminal_ev_ebit_high,
            bundle.net_debt_change,
            bundle.share_count_growth,
            bundle.distributions_per_share,
        )
        for source_id in assumption.source_ids
    )


def test_m0_qualitative_source_id_fixture_reproduces_boundary_failure():
    candidate = AgentCandidate(
        rank=1,
        company_id=114,
        ticker="M0 B",
        name="Synthetic Software",
        research_evidence={
            "documents": [{"source_id": "m0:report:114:2026-q2"}],
        },
    )
    repository = MagicMock()

    with pytest.raises(
        StockAnalysisValidationError, match="unknown evidence source"
    ):
        AgentExecutionBoundary(repository).persist_response(
            load_fixture("m0-qualitative-source-id-failure.json"),
            candidate,
            created_by="model-spy",
        )

    repository.save_stock_analysis.assert_not_called()


def test_m0_scenario_fixtures_reproduce_available_and_methodology_failure():
    valid_payload = parse_scenario_authoring_result(load_fixture("m0-valid-scenario.json"))
    invalid_payload = parse_scenario_authoring_result(
        load_fixture("m0-scenario-methodology-failure.json")
    )
    inputs = valid_inputs()

    valid = ForwardScenarioEngine().analyze(
        replace(
            inputs,
            case_horizon_months=valid_payload["case_horizon_months"],
            bundles=tuple(valid_payload["scenario_bundles"]),
        )
    )
    invalid = ForwardScenarioEngine().analyze(
        replace(
            inputs,
            case_horizon_months=invalid_payload["case_horizon_months"],
            bundles=tuple(invalid_payload["scenario_bundles"]),
        )
    )

    assert valid.status == "available"
    assert invalid.status == "insufficient_evidence"
    assert invalid.methodology_flags == (
        "all scenario bundles must use the same 24, 36, or 48 month horizon",
    )


def test_m0_model_spy_counts_calls_by_schema_and_stage(model_spy):
    model_spy.queue(
        "stock_analysis",
        load_fixture("m0-valid-qualitative.json"),
        load_fixture("m0-valid-qualitative.json"),
    )
    model_spy.queue("scenario_authoring", load_fixture("m0-valid-scenario.json"))
    qualitative_prompt = AgentPrompt(system="", user="", schema_name="stock_analysis")
    scenario_prompt = AgentPrompt(system="", user="", schema_name="scenario_authoring")

    model_spy.generate(qualitative_prompt)
    model_spy.generate(scenario_prompt)
    model_spy.repair(qualitative_prompt, "rejected", "synthetic source-ID error")

    assert model_spy.counts_by_stage() == {"qualitative": 2, "scenario": 1}
    assert model_spy.counts_by_schema() == {
        "stock_analysis": 2,
        "scenario_authoring": 1,
    }
    assert model_spy.count(stage="qualitative", schema_name="stock_analysis") == 2
    assert [call.operation for call in model_spy.calls] == [
        "generate",
        "generate",
        "repair",
    ]


def test_m4_bounds_qualitative_and_scenario_calls(model_spy):
    candidate = AgentCandidate(
        rank=1,
        company_id=114,
        ticker="M0 B",
        name="Synthetic Software",
        full_results={
            "reverse_dcf": {"status": "available"},
            "valuation": {
                "ev_ebit_guardrail_low": 5.0,
                "ev_ebit_guardrail_high": 15.0,
            },
        },
        research_evidence={
            "documents": [{"source_id": "m0:report:114:2026-q2"}],
        },
    )
    model_spy.max_repair_attempts = 5
    model_spy.queue(
        "stock_analysis",
        *([load_fixture("m0-qualitative-source-id-failure.json")] * 2),
    )
    boundary = MagicMock()
    boundary.validate_qualitative_response.side_effect = StockAnalysisValidationError(
        "synthetic source-ID failure"
    )

    with pytest.raises(StockAnalysisValidationError):
        AgentAnalysisService(
            model_spy,
            boundary,
            AgentPromptBuilder(),
        ).analyze([candidate])

    thesis = parse_qualitative_stock_analysis_result(
        load_fixture("m0-valid-qualitative.json")
    )
    model_spy.queue(
        "scenario_authoring",
        *([load_fixture("m0-scenario-methodology-failure.json")] * 2),
    )

    def reject_scenario(qualitative, horizon, bundles):
        return ForwardScenarioEngine().analyze(
            replace(
                valid_inputs(),
                case_horizon_months=horizon,
                bundles=tuple(bundles),
            )
        )

    with pytest.raises(ScenarioAuthoringError, match="all scenario bundles"):
        ScenarioAuthoringService(model_spy).author(
            candidate,
            thesis,
            reject_scenario,
        )

    assert model_spy.counts_by_stage() == {"qualitative": 2, "scenario": 2}
    assert model_spy.counts_by_schema() == {
        "stock_analysis": 2,
        "scenario_authoring": 2,
    }
    assert len(model_spy.calls) == 4


def test_m0_packet_measurement_is_read_only_and_labels_estimate():
    packet = {
        "research_evidence": {
            "documents": [
                {"source_id": "m0:report:unicode", "text": "Å synthetic text"}
            ]
        },
        "value": 1,
    }
    original = copy.deepcopy(packet)

    measurement = measure_packet(packet)

    assert packet == original
    assert measurement.document_count == 1
    assert measurement.byte_count > measurement.character_count
    assert measurement.token_estimate == (measurement.character_count + 3) // 4


def test_m0_five_company_prompt_size_baseline_is_metadata_only():
    baseline = json.loads(
        (Path(__file__).parent / "fixtures" / "m0_prompt_size_baseline.json").read_text(
            encoding="utf-8"
        )
    )

    assert baseline["source"] == "local-run-metadata-only"
    assert baseline["measurement"] == "full Codex input characters divided by four"
    assert baseline["contains_private_document_text"] is False
    assert len(baseline["companies"]) == 5
    assert [row["company_id"] for row in baseline["companies"]] == [
        149,
        76,
        37,
        114,
        153,
    ]
    assert all(
        set(row) == {"company_id", "ticker", "document_count", "full_input"}
        and set(row["full_input"]) == {
            "byte_count",
            "character_count",
            "document_count",
            "token_estimate",
        }
        for row in baseline["companies"]
    )
    assert min(row["full_input"]["token_estimate"] for row in baseline["companies"]) >= 50_000
    assert max(row["full_input"]["token_estimate"] for row in baseline["companies"]) <= 62_000


def test_m0_job_1175_aggregate_input_baseline_is_complete_and_metadata_only():
    baseline = json.loads(
        (Path(__file__).parent / "fixtures" / "m0_job_1175_input_baseline.json").read_text(
            encoding="utf-8"
        )
    )

    assert baseline["source"] == "job-1175-aggregate-metadata-only"
    assert baseline["contains_private_document_text"] is False
    assert baseline["frozen_packet"] == {
        "character_count": 563_982,
        "byte_count": 565_362,
        "document_count": 6,
        "token_estimate": 140_996,
    }
    assert baseline["qualitative"] == {
        "full_input_character_count": 915_366,
        "provider_character_limit": 1_048_576,
        "remaining_character_headroom": 133_210,
    }
    assert baseline["scenario"]["full_input_character_count"] == 724_894
    assert baseline["evidence_catalog"] == {
        "character_count": 312_794,
        "alias_count": 2_284,
        "alias_table_character_count": 307_407,
        "repeated_citation_instruction_character_count": 306_932,
    }
    assert baseline["packet_without_enumerated_alias_table"] == {
        "character_count": 260_246,
        "token_estimate": 65_062,
    }
    assert baseline["selected_documentary_content_character_count"] == 188_689
    assert baseline["deterministic_full_results_character_count"] == 58_523


@pytest.mark.parametrize(
    ("filename", "sha256"),
    [
        (
            "004-4-CLAS-B-validated-baseline.json",
            "929ee04671a0f382364eedc2246acc930e8e505ecca910a06a163b5c07efa17d",
        ),
        (
            "114-MSAB-B-validated-baseline.json",
            "6ddfacd1a226b0f8ded810ef59b950694089aa148acfeeb63a521c3db0cc5698",
        ),
        (
            "143-GENI-validated-baseline.json",
            "a0b9c866e790d82fe3d2c3e998760277eaba57f721a71041b82a1786b3209fff",
        ),
    ],
)
def test_m0_existing_accepted_analysis_fixture_is_unchanged(filename, sha256):
    assert hashlib.sha256((FIXTURE_DIR / filename).read_bytes()).hexdigest() == sha256
