"""Opt-in orchestration for the complete non-authoritative shadow graph."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
from typing import Any, Mapping

from kncompanyscraper.analysis.agent.agent_packet import serialize_packet
from kncompanyscraper.analysis.agent.petter_aggregator import AggregatorInput
from kncompanyscraper.analysis.agent.specialist_runner import (
    FIRST_WAVE_SPECIALISTS,
    ShadowSpecialistRun,
)
from kncompanyscraper.analysis.policy_versions import FORWARD_SCENARIO_POLICY_VERSION

_SCENARIO_CASES = {"bear", "base", "bull"}
_SCENARIO_HORIZONS = {24, 36, 48}
_SCENARIO_BAND_FIELDS = (
    "case",
    "horizon_months",
    "low_price",
    "high_price",
    "low_holding_value",
    "high_holding_value",
    "low_annualized_return",
    "high_annualized_return",
)

SHADOW_BUNDLE_SCHEMA_VERSION = "shadow-analysis-bundle-v1"
SHADOW_SEQUENCE = (
    "first_wave_specialists",
    "deterministic_inputs",
    "sell_conditions",
    "conflict_evaluation",
    "petter_aggregator",
)
FIRST_WAVE_CALLS = len(FIRST_WAVE_SPECIALISTS)
MAX_MODEL_CALLS_PER_COMPANY = (FIRST_WAVE_CALLS + 1 + 1) * 2


class ShadowOptInRequired(ValueError):
    """Raised when an operator has not explicitly authorized model execution."""


@dataclass(frozen=True)
class ShadowIntegrationResult:
    company_id: int
    ticker: str
    run_id: str
    packet_hash: str
    status: str
    stage_order: tuple[str, ...] = SHADOW_SEQUENCE
    specialist_run: ShadowSpecialistRun | None = None
    aggregation: Any = None
    error: str | None = None

    @property
    def artifact_ids(self) -> tuple[int, ...]:
        ids = []
        if self.specialist_run is not None:
            for result in self.specialist_run.results:
                ids.extend(result.artifact_ids)
        if self.aggregation is not None:
            ids.extend(self.aggregation.raw_artifact_ids)
            ids.extend(self.aggregation.validated_artifact_ids)
        return tuple(ids)

    def to_dict(self) -> dict:
        return {
            "schema_version": SHADOW_BUNDLE_SCHEMA_VERSION,
            "company_id": self.company_id,
            "ticker": self.ticker,
            "run_id": self.run_id,
            "packet_hash": self.packet_hash,
            "status": self.status,
            "stage_order": list(self.stage_order),
            "specialist_run": self.specialist_run.to_dict() if self.specialist_run else None,
            "aggregation": self.aggregation.to_dict() if self.aggregation else None,
            "artifact_ids": list(self.artifact_ids),
            "error": self.error,
        }


def validate_frozen_packets(packets: list[Mapping]) -> list[Mapping]:
    """Reject duplicate company identities before any model call is possible."""
    if not isinstance(packets, list) or not packets:
        raise ValueError("frozen packets must be a non-empty list")
    seen = set()
    for packet in packets:
        company_id = _packet_value(packet, "company_id")
        ticker = _packet_value(packet, "ticker")
        if not isinstance(company_id, int) or not isinstance(ticker, str) or not ticker:
            raise ValueError("each frozen packet needs company_id and ticker identity")
        if company_id in seen:
            raise ValueError(f"duplicate frozen packet company_id: {company_id}")
        seen.add(company_id)
    return packets


def validate_frozen_scenario_results(
    packets: list[Mapping], scenario_results: Mapping
) -> dict[str, Mapping]:
    packet_list = validate_frozen_packets(packets)
    if not isinstance(scenario_results, Mapping):
        raise ValueError("scenario results must be a company_id map")
    expected_ids = {str(_packet_value(packet, "company_id")) for packet in packets}
    if set(scenario_results) != expected_ids:
        raise ValueError("scenario results must bind exactly to the frozen packets")
    valid_statuses = {"available", "insufficient_evidence", "method_not_supported"}
    packet_hashes = {
        str(_packet_value(packet, "company_id")): sha256(
            serialize_packet(packet).encode("utf-8")
        ).hexdigest()
        for packet in packet_list
    }
    validated = {}
    for company_id, scenario in scenario_results.items():
        if not isinstance(scenario, Mapping):
            raise ValueError(f"scenario result for company {company_id} is invalid")
        if scenario.get("packet_hash") != packet_hashes[company_id]:
            raise ValueError(f"scenario result for company {company_id} is not bound to its packet")
        if scenario.get("policy_version") != FORWARD_SCENARIO_POLICY_VERSION:
            raise ValueError(f"scenario result for company {company_id} has an invalid policy")
        status = scenario.get("status")
        if status not in valid_statuses:
            raise ValueError(f"scenario result for company {company_id} has an invalid status")
        if status != "available":
            validated[company_id] = {
                key: value for key, value in scenario.items() if key != "packet_hash"
            }
            continue
        bands = scenario.get("bands")
        if not isinstance(bands, list) or len(bands) != len(_SCENARIO_CASES):
            raise ValueError(f"scenario result for company {company_id} is incomplete")
        if {
            band.get("case") for band in bands if isinstance(band, Mapping)
        } != _SCENARIO_CASES:
            raise ValueError(f"scenario result for company {company_id} has invalid cases")
        horizons = set()
        for band in bands:
            if not isinstance(band, Mapping) or any(
                field not in band for field in _SCENARIO_BAND_FIELDS
            ):
                raise ValueError(f"scenario result for company {company_id} has incomplete bands")
            horizon = band["horizon_months"]
            if horizon not in _SCENARIO_HORIZONS:
                raise ValueError(f"scenario result for company {company_id} has invalid horizons")
            horizons.add(horizon)
            if any(
                isinstance(band[field], bool)
                or not isinstance(band[field], (int, float))
                or not isfinite(band[field])
                for field in _SCENARIO_BAND_FIELDS[2:]
            ):
                raise ValueError(f"scenario result for company {company_id} has invalid values")
            if (
                band["low_price"] <= 0
                or band["high_price"] <= 0
                or band["low_holding_value"] <= 0
                or band["high_holding_value"] <= 0
            ):
                raise ValueError(f"scenario result for company {company_id} has non-positive values")
            if band["low_price"] > band["high_price"]:
                raise ValueError(f"scenario result for company {company_id} has an inverted price range")
        if len(horizons) != 1:
            raise ValueError(f"scenario result for company {company_id} has inconsistent horizons")
        by_case = {band["case"]: band for band in bands}
        if by_case["bear"]["high_price"] > by_case["base"]["low_price"]:
            raise ValueError(f"scenario result for company {company_id} has overlapping bear/base prices")
        if by_case["base"]["high_price"] > by_case["bull"]["low_price"]:
            raise ValueError(f"scenario result for company {company_id} has overlapping base/bull prices")
        if (
            by_case["base"]["high_annualized_return"]
            - by_case["base"]["low_annualized_return"]
            > 0.15
        ):
            raise ValueError(f"scenario result for company {company_id} has an excessive base spread")
        validated[company_id] = {
            key: value for key, value in scenario.items() if key != "packet_hash"
        }
    return validated


class ShadowIntegrationRunner:
    """Connect existing specialist and aggregator contracts without production writes."""

    def __init__(self, specialist_runner, aggregator_runner):
        self.specialist_runner = specialist_runner
        self.aggregator_runner = aggregator_runner

    @staticmethod
    def expected_work_summary(company_count: int = 1) -> dict:
        if company_count < 1:
            raise ValueError("company_count must be positive")
        return {
            "company_count": company_count,
            "stages_per_company": list(SHADOW_SEQUENCE),
            "minimum_model_calls": (FIRST_WAVE_CALLS + 1) * company_count,
            "maximum_model_calls": MAX_MODEL_CALLS_PER_COMPANY * company_count,
            "note": "Call counts are bounds: sell_conditions may be limited without a model call; each model stage may make one repair call; deterministic inputs make no model calls.",
        }

    def run(
        self,
        packet: Mapping | Any,
        *,
        run_id: str,
        packet_hash: str | None = None,
        deterministic_scenario_results: Any = None,
        allow_model_calls: bool = False,
    ) -> ShadowIntegrationResult:
        if not allow_model_calls:
            raise ShadowOptInRequired(
                "shadow model execution requires explicit allow_model_calls=True"
            )
        serialized = serialize_packet(packet)
        computed_hash = sha256(serialized.encode("utf-8")).hexdigest()
        if packet_hash is not None and packet_hash != computed_hash:
            raise ValueError("shadow integration packet_hash does not match frozen packet")
        packet_hash = packet_hash or computed_hash
        company_id = _packet_value(packet, "company_id")
        ticker = _packet_value(packet, "ticker")
        if not isinstance(company_id, int) or not isinstance(ticker, str) or not ticker:
            raise ValueError("shadow integration requires frozen company identity")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("shadow integration requires a run_id")

        scenario = deterministic_scenario_results
        if scenario is None:
            full_results = _packet_value(packet, "full_results") or {}
            scenario = full_results.get("forward_scenario")
        reverse_dcf = (_packet_value(packet, "full_results") or {}).get("reverse_dcf")
        try:
            shadow_run = self.specialist_runner.run(
                packet,
                run_id=run_id,
                packet_hash=packet_hash,
                deterministic_scenario_data=scenario,
            )
            if shadow_run.run_id != run_id or shadow_run.packet_hash != packet_hash:
                raise ValueError("specialist run identity does not match frozen packet")
            if getattr(shadow_run, "company_id", company_id) != company_id:
                raise ValueError("specialist run company does not match frozen packet")
            _require_complete_stage_set(shadow_run)
            aggregation_input = AggregatorInput.from_shadow_run(
                packet,
                shadow_run,
                deterministic_scenario_results=scenario,
                reverse_dcf_results=reverse_dcf,
            )
            aggregation = self.aggregator_runner.run(aggregation_input)
            status = "accepted" if aggregation.status == "accepted" else "failed"
            return ShadowIntegrationResult(
                company_id, ticker, run_id, packet_hash, status,
                specialist_run=shadow_run, aggregation=aggregation,
                error=None if status == "accepted" else "; ".join(aggregation.validation_errors),
            )
        except Exception as exc:
            return ShadowIntegrationResult(
                company_id, ticker, run_id, packet_hash, "failed", error=str(exc)
            )


def build_shadow_artifact_bundle(repository, packets, runs) -> dict:
    """Build evaluator input from persisted artifacts, not copied model responses."""
    packet_list = validate_frozen_packets(list(packets))
    runs = list(runs)
    if len(packet_list) != len(runs):
        raise ValueError("each frozen packet needs exactly one shadow run")
    records = []
    getter = getattr(repository, "get_shadow_artifacts_for_run", None)
    if callable(getter):
        for packet, run in zip(packet_list, runs):
            company_id = _packet_value(packet, "company_id")
            packet_hash = sha256(
                serialize_packet(packet).encode("utf-8")
            ).hexdigest()
            for record in getter(company_id, run.run_id):
                metadata = record.get("metadata") or {}
                if (
                    record.get("company_id") != company_id
                    or metadata.get("run_id") != run.run_id
                    or metadata.get("packet_hash") != packet_hash
                ):
                    raise ValueError("persisted shadow artifact identity does not match frozen run")
                records.append(record)
    return {
        "schema_version": SHADOW_BUNDLE_SCHEMA_VERSION,
        "packets": {
            str(_packet_value(packet, "company_id")): _json_value(packet)
            for packet in packet_list
        },
        "runs": [run.to_dict() for run in runs],
        "artifacts": records,
    }


def _require_complete_stage_set(shadow_run) -> None:
    expected = {agent.value for agent in FIRST_WAVE_SPECIALISTS} | {"sell_conditions"}
    actual = {result.agent_name for result in shadow_run.results}
    missing = sorted(expected - actual)
    failed = sorted(
        result.agent_name for result in shadow_run.results if result.status == "failed"
    )
    if missing:
        raise ValueError("shadow specialist stages missing: " + ", ".join(missing))
    if failed:
        raise ValueError("shadow specialist stages failed: " + ", ".join(failed))


def _packet_value(packet, name):
    return packet.get(name) if isinstance(packet, Mapping) else getattr(packet, name, None)


def _json_value(value):
    if hasattr(value, "to_dict"):
        return _json_value(value.to_dict())
    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value
