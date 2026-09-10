import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kncompanyscraper.analysis.agent.pilot_manifest import (
    PilotManifestError,
    validate_three_company_pilot,
)
from kncompanyscraper.analysis.agent.shadow_integration import (
    ShadowIntegrationRunner,
    ShadowOptInRequired,
)
from kncompanyscraper.cli.agent import _cmd_run_shadow_analysis


class SpecialistSpy:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def run(self, packet, *, run_id, packet_hash, deterministic_scenario_data):
        self.calls += 1
        self.result.run_id = run_id
        self.result.packet_hash = packet_hash
        self.result.company_id = packet["company_id"]
        self.result.scenario = deterministic_scenario_data
        return self.result


class AggregatorSpy:
    def __init__(self):
        self.inputs = []

    def run(self, inputs):
        self.inputs.append(inputs)
        return SimpleNamespace(
            status="accepted",
            raw_artifact_ids=(10,),
            validated_artifact_ids=(11,),
            validation_errors=(),
            to_dict=lambda: {"status": "accepted"},
        )


class ShadowResult:
    def __init__(self):
        self.run_id = "wrong"
        self.packet_hash = "wrong"
        self.company_id = 0
        self.results = [
            SimpleNamespace(agent_name=agent, status="accepted", artifact_ids=())
            for agent in (
                "business_model",
                "management_credibility",
                "margin",
                "insider_ownership",
                "growth_valuation",
                "sell_conditions",
            )
        ]
        self.conflicts = ()

    def to_dict(self):
        return {"run_id": self.run_id, "packet_hash": self.packet_hash}


def packet():
    return {
        "company_id": 7,
        "ticker": "SYN",
        "name": "Synthetic",
        "full_results": {
            "reverse_dcf": {"status": "available"},
            "forward_scenario": {"status": "available"},
        },
        "research_evidence": {},
    }


def test_complete_shadow_sequence_is_opt_in_and_keeps_frozen_identity():
    specialists = SpecialistSpy(ShadowResult())
    aggregator = AggregatorSpy()
    runner = ShadowIntegrationRunner(specialists, aggregator)

    with pytest.raises(ShadowOptInRequired):
        runner.run(packet(), run_id="run-7")
    assert specialists.calls == 0

    result = runner.run(packet(), run_id="run-7", allow_model_calls=True)

    assert result.status == "accepted"
    assert list(result.stage_order) == [
        "first_wave_specialists",
        "deterministic_inputs",
        "sell_conditions",
        "conflict_evaluation",
        "petter_aggregator",
    ]
    assert specialists.calls == 1
    assert aggregator.inputs[0].run_id == "run-7"
    assert aggregator.inputs[0].packet_hash == result.packet_hash
    assert aggregator.inputs[0].deterministic_scenario_results == {
        "status": "available"
    }


def test_shadow_plan_is_bounded():
    summary = ShadowIntegrationRunner.expected_work_summary(3)
    assert summary["minimum_model_calls"] == 21
    assert summary["maximum_model_calls"] == 42


def test_shadow_rejects_mixed_packet_identity_before_execution():
    specialists = SpecialistSpy(ShadowResult())
    runner = ShadowIntegrationRunner(specialists, AggregatorSpy())
    with pytest.raises(ValueError, match="packet_hash"):
        runner.run(packet(), run_id="run-7", packet_hash="bad", allow_model_calls=True)
    assert specialists.calls == 0


def test_shadow_cli_rejects_non_pilot_packet_count(tmp_path):
    second_packet = copy.deepcopy(packet())
    second_packet.update(company_id=8, ticker="ALT")
    packets_path = tmp_path / "packets.json"
    packets_path.write_text(json.dumps({"packets": [packet(), second_packet]}))

    with pytest.raises(SystemExit, match="exactly three packets"):
        _cmd_run_shadow_analysis(
            SimpleNamespace(
                packets=packets_path,
                output=tmp_path / "shadow.json",
                provider="local",
                model=None,
                reasoning_effort=None,
                run_id_prefix="shadow-pilot",
                allow_model_calls=True,
            )
        )


def test_pilot_manifest_requires_three_distinct_labeled_packet_bindings():
    template = {
        "schema_version": "specialist-three-company-pilot-v1",
        "companies": [
            {
                "case_id": f"case-{index}",
                "company_id": index,
                "ticker": f"T{index}",
                "packet_ref": str(index),
                "packet_hash": "a" * 64,
                "labels_ref": f"labels-{index}.json",
            }
            for index in range(1, 4)
        ],
    }
    assert len(validate_three_company_pilot(template)["companies"]) == 3
    invalid = copy.deepcopy(template)
    invalid["companies"].pop()
    with pytest.raises(PilotManifestError, match="exactly three"):
        validate_three_company_pilot(invalid)


def test_aggregator_case_artifact_is_consumed_by_evaluation_boundary():
    fixture_dir = Path(__file__).parent / "fixtures" / "specialist_evaluation"
    cases = json.loads((fixture_dir / "cases.json").read_text())
    artifacts = json.loads((fixture_dir / "artifacts.json").read_text())
    case = cases["cases"][0]
    artifacts["artifacts"].append(
        {
            "metadata": {
                "artifact_type": "aggregator_validated",
                "result_scope": "case",
                "run_id": "synthetic-run",
                "packet_hash": case["packet_hash"],
                "validation_status": "accepted",
                "final_verdict": "watch",
            },
            "content": json.dumps(
                {
                    "candidate": {
                        "company_id": case["company_id"],
                        "ticker": case["ticker"],
                        "verdict": "watch",
                    },
                    "manifest": {
                        "run_id": "synthetic-run",
                        "packet_hash": case["packet_hash"],
                    },
                }
            ),
        }
    )
    from kncompanyscraper.analysis.agent.specialist_evaluation import compare_specialist_evaluations

    report = compare_specialist_evaluations(
        cases, artifacts,
        packets=json.loads((fixture_dir / "packets.json").read_text()),
    )
    assert report["cases"][0]["case_level_result"]["available"] is True
    assert report["metrics"]["final_verdict_agreement"]["unavailable"] == 0
