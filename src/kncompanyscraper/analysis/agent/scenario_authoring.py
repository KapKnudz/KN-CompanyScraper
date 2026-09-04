"""Dedicated model stage for sourcing forward-scenario assumptions."""

from copy import deepcopy
from dataclasses import asdict, dataclass, is_dataclass
from hashlib import sha256
import json

from kncompanyscraper.analysis.agent.json_support import json_default
from kncompanyscraper.analysis.agent.output_schema import (
    SCENARIO_AUTHORING_OUTPUT_CONTRACT,
    scenario_authoring_json_schema,
)
from kncompanyscraper.analysis.agent.packet_measurement import measure_packet
from kncompanyscraper.analysis.agent.prompt_builder import AgentPrompt, AgentPromptBuilder
from kncompanyscraper.analysis.agent.result_parser import (
    StockAnalysisValidationError,
    parse_scenario_authoring_result,
)
from kncompanyscraper.analysis.valuation.forward_scenario import ForwardScenarioAnalysis
from kncompanyscraper.analysis.valuation.forward_scenario import ScenarioBundle


BASE_ANNUALIZED_RETURN_SPREAD_MAX = 0.15


class ScenarioAuthoringError(StockAnalysisValidationError):
    pass


@dataclass(frozen=True)
class ScenarioAuthoringOutcome:
    case_horizon_months: int
    scenario_bundles: tuple[ScenarioBundle, ...]
    analysis: ForwardScenarioAnalysis
    attempts: int
    raw_analysis_ids: tuple[int, ...] = ()
    policy_name: str = ""
    policy_version: str = ""
    policy_sha256: str = ""
    scenario_input_hashes: tuple[str, ...] = ()
    scenario_input_measurements: tuple[dict, ...] = ()
    scenario_validation_errors: tuple[str, ...] = ()
    model_response_ids: tuple[str, ...] = ()


class ScenarioAuthoringPromptBuilder:
    POLICY_NAME = "scenario-authoring-policy"
    POLICY_VERSION = "scenario-authoring-v3"
    CONTRACT_VERSION = "scenario-stage-prompt-v3"

    def build(self, candidate, qualitative_thesis, *, repair=None) -> AgentPrompt:
        payload = _scenario_packet(candidate, qualitative_thesis)
        if repair is not None:
            payload["repair"] = {
                "previous_bundles": repair["previous_bundles"],
                "methodology_flags": list(repair["methodology_flags"]),
                **(
                    {
                        "deterministic_output_diagnostic": repair[
                            "deterministic_output_diagnostic"
                        ]
                    }
                    if repair.get("deterministic_output_diagnostic") is not None
                    else {}
                ),
                "instruction": (
                    "Preserve the accepted qualitative thesis and case horizon. "
                    "Change only scenario assumptions. If the deterministic base "
                    "annualized-return spread exceeds its maximum, narrow the base "
                    "terminal-multiple interval and/or other base assumptions enough "
                    "for the deterministic engine to satisfy the maximum. Retain "
                    "sourced rationales for every changed assumption. Do not author "
                    "or reproduce calculated outputs. If the diagnostic reports a "
                    "verdict-coherence conflict, keep the qualitative verdict and "
                    "resolve it through sourced scenario assumptions: a price-latent "
                    "case must have a base lower-bound return below the required "
                    "return, while an operating-latent case must have a base "
                    "upper-bound return at or above it."
                ),
            }
        system = (
            "Return only the sourced forward-scenario assumptions requested in "
            "the scenario-authoring prompt. A zero net-debt change must use "
            "not_applicable provenance. Do not provide calculated prices, "
            "returns, probabilities, or fair values."
        )
        instructions = self._read_resource("prompts/scenario_authoring_prompt.md")
        user_payload = {
            "instructions": instructions,
            **payload,
            "output_contract": SCENARIO_AUTHORING_OUTPUT_CONTRACT,
        }
        policy_sha256 = sha256(system.encode("utf-8")).hexdigest()
        return AgentPrompt(
            system=system,
            user=json.dumps(
                user_payload,
                ensure_ascii=False,
                indent=2,
                default=json_default,
            ),
            policy_name=self.POLICY_NAME,
            policy_version=self.POLICY_VERSION,
            policy_sha256=policy_sha256,
            output_schema=scenario_authoring_json_schema(),
            schema_name="scenario_authoring",
            packet_measurement=asdict(measure_packet(user_payload, pretty=True)),
            contract_version=self.CONTRACT_VERSION,
        )

    @staticmethod
    def _read_resource(relative_path: str) -> str:
        return AgentPromptBuilder._read_resource(relative_path)


class ScenarioAuthoringService:
    """Author, validate, and repair scenario bundles at most twice."""

    MAX_ATTEMPTS = 2

    def __init__(
        self,
        model_adapter,
        prompt_builder=None,
        raw_response_repository=None,
    ):
        self.model_adapter = model_adapter
        self.prompt_builder = prompt_builder or ScenarioAuthoringPromptBuilder()
        self.raw_response_repository = raw_response_repository

    def author(
        self,
        candidate,
        qualitative_thesis,
        validate,
        *,
        base_prompt=None,
        prior_metadata=None,
    ):
        if qualitative_thesis.case_horizon_months is None:
            raise ScenarioAuthoringError(
                "qualitative thesis must select a case horizon before scenario authoring"
            )
        prior_metadata = dict(prior_metadata or {})
        prior_attempts = prior_metadata.get("scenario_authoring_attempts", 0)
        if prior_attempts >= self.MAX_ATTEMPTS:
            raise ScenarioAuthoringError(
                "scenario validation attempts are exhausted for this job"
            )
        repair = None
        raw_ids = list(prior_metadata.get("scenario_authoring_raw_analysis_ids", []))
        input_hashes = list(prior_metadata.get("scenario_input_hashes", []))
        input_measurements = list(
            prior_metadata.get("scenario_input_measurements", [])
        )
        validation_errors = list(
            prior_metadata.get("scenario_validation_errors", [])
        )
        model_response_ids = list(
            prior_metadata.get("scenario_model_response_ids", [])
        )
        for attempt in range(prior_attempts + 1, self.MAX_ATTEMPTS + 1):
            analysis = None
            prompt = (
                base_prompt
                if repair is None and base_prompt is not None
                else self.prompt_builder.build(
                    candidate,
                    qualitative_thesis,
                    repair=repair,
                )
            )
            input_hash = _scenario_input_sha256(prompt)
            input_hashes.append(input_hash)
            try:
                if repair is None:
                    response = self.model_adapter.generate(prompt)
                else:
                    response = self.model_adapter.repair(
                        prompt,
                        previous_output,
                        repair["validation_error"],
                    )
            except Exception as interruption:
                interruption.stage_metadata = self._stage_metadata(
                    attempt - 1,
                    raw_ids,
                    input_hashes,
                    input_measurements,
                    validation_errors,
                    model_response_ids,
                    prompt,
                )
                raise
            model_response_ids.append(response.response_id)
            input_measurement = getattr(response, "input_measurement", None)
            input_measurements.append(input_measurement or prompt.packet_measurement or {})
            raw_id = self._save_raw(candidate, response, prompt, attempt)
            if raw_id is not None:
                raw_ids.append(raw_id)
            try:
                authored = parse_scenario_authoring_result(response.output_text)
                if authored["case_horizon_months"] != qualitative_thesis.case_horizon_months:
                    raise ScenarioAuthoringError(
                        "scenario horizon does not match the qualitative thesis"
                    )
                _validate_scenario_source_whitelist(
                    authored["scenario_bundles"],
                    scenario_source_whitelist(candidate),
                )
                analysis = validate(
                    deepcopy(qualitative_thesis),
                    authored["case_horizon_months"],
                    authored["scenario_bundles"],
                )
                if analysis.status != "available":
                    raise ScenarioAuthoringError(
                        "scenario engine rejected authored bundles: "
                        + "; ".join(analysis.methodology_flags)
                    )
            except StockAnalysisValidationError as exc:
                validation_errors.append(str(exc))
                if raw_id is not None:
                    self.raw_response_repository.update_raw_validation(
                        raw_id, "rejected", str(exc)
                    )
                if attempt == self.MAX_ATTEMPTS or not callable(
                    getattr(self.model_adapter, "repair", None)
                ):
                    exc.stage_metadata = self._stage_metadata(
                        attempt,
                        raw_ids,
                        input_hashes,
                        input_measurements,
                        validation_errors,
                        model_response_ids,
                        prompt,
                    )
                    raise
                previous = locals().get("authored") or {}
                repair = {
                    "previous_bundles": {
                        "case_horizon_months": previous.get(
                            "case_horizon_months"
                        ),
                        "scenario_bundles": [
                            asdict(bundle)
                            for bundle in previous.get("scenario_bundles", [])
                        ],
                    },
                    "methodology_flags": tuple(
                        dict.fromkeys(
                            (
                                *getattr(
                                    locals().get("analysis"),
                                    "methodology_flags",
                                    (),
                                ),
                                str(exc),
                            )
                        )
                    ),
                    "validation_error": str(exc),
                    "deterministic_output_diagnostic": (
                        getattr(exc, "deterministic_output_diagnostic", None)
                        or _base_return_spread_diagnostic(analysis)
                    ),
                }
                previous_output = response.output_text
                continue
            if raw_id is not None:
                self.raw_response_repository.update_raw_validation(raw_id, "accepted")
            return ScenarioAuthoringOutcome(
                case_horizon_months=authored["case_horizon_months"],
                scenario_bundles=tuple(authored["scenario_bundles"]),
                analysis=analysis,
                attempts=attempt,
                raw_analysis_ids=tuple(raw_ids),
                policy_name=prompt.policy_name,
                policy_version=prompt.policy_version,
                policy_sha256=prompt.policy_sha256,
                scenario_input_hashes=tuple(input_hashes),
                scenario_input_measurements=tuple(input_measurements),
                scenario_validation_errors=tuple(validation_errors),
                model_response_ids=tuple(model_response_ids),
            )
        raise AssertionError("scenario authoring loop did not return or raise")

    @staticmethod
    def _stage_metadata(
        attempts,
        raw_ids,
        input_hashes,
        input_measurements,
        validation_errors,
        model_response_ids,
        prompt,
    ):
        return {
            "scenario_authoring_attempts": attempts,
            "scenario_authoring_raw_analysis_ids": list(raw_ids),
            "scenario_input_hashes": list(input_hashes),
            "scenario_input_measurements": list(input_measurements),
            "scenario_validation_errors": list(validation_errors),
            "scenario_model_response_ids": list(model_response_ids),
            "scenario_policy_name": prompt.policy_name,
            "scenario_policy_version": prompt.policy_version,
            "scenario_policy_sha256": prompt.policy_sha256,
        }

    def _save_raw(self, candidate, response, prompt, attempt):
        if self.raw_response_repository is None:
            return None
        return self.raw_response_repository.save_stock_analysis_raw(
            candidate.company_id,
            response.output_text,
            created_by=response.model,
            metadata={
                "analysis_mode": "scenario_authoring",
                "artifact_type": "model_response",
                "scenario_authoring_attempt": attempt,
                "policy_name": prompt.policy_name,
                "policy_version": prompt.policy_version,
                "policy_sha256": prompt.policy_sha256,
                "model_response_id": response.response_id,
                "usage": response.usage,
                "input_measurement": getattr(
                    response, "input_measurement", None
                ),
                "scenario_input_sha256": _scenario_input_sha256(prompt),
                "scenario_input_measurement": getattr(
                    response, "input_measurement", None
                )
                or prompt.packet_measurement,
            },
        )


def _scenario_packet(candidate, qualitative_thesis) -> dict:
    reverse_dcf = candidate.full_results.get("reverse_dcf") or {}
    valuation = candidate.full_results.get("valuation") or {}
    history = candidate.full_results.get("financial_history") or {}
    peer_comparison = candidate.full_results.get("peer_comparison")
    source_whitelist = scenario_source_whitelist(candidate)
    qualitative = _scenario_qualitative_projection(
        qualitative_thesis.to_dict(), set(source_whitelist)
    )
    qualitative.pop("scenario_bundles", None)
    qualitative.pop("forward_scenario_analysis", None)
    return {
        "company": {
            "company_id": candidate.company_id,
            "ticker": candidate.ticker,
            "name": candidate.name,
            "ranking_model": getattr(
                candidate.ranking_model, "value", str(candidate.ranking_model)
            ),
        },
        "qualitative_thesis": qualitative,
        "case_horizon_months": qualitative_thesis.case_horizon_months,
        "deterministic_forward_readiness": _readiness_inputs(candidate),
        "scenario_constraints": _scenario_constraints(candidate, qualitative_thesis),
        "scenario_financial_history": _json_value(
            _field(history, "scenario_history")
        ),
        "current_inputs": {
            "price": _field(reverse_dcf, "current_price"),
            "revenue": _field(reverse_dcf, "current_revenue"),
            "shares": _field(reverse_dcf, "current_shares"),
            "net_debt": _field(reverse_dcf, "current_net_debt"),
            "currency": _field(reverse_dcf, "financial_currency"),
            "current_ev_ebit": _field(valuation, "raw_ev_ebit")
            or _field(valuation, "ev_ebit"),
        },
        "valuation_anchors": {
            "historical_terminal_multiple_range": (
                _field(valuation, "ev_ebit_guardrail_low"),
                _field(valuation, "ev_ebit_guardrail_high"),
            ),
            "peer_terminal_multiple_range": _json_value(
                _field(peer_comparison, "target_terminal_ev_ebit")
            ),
            "base_ceiling": _field(valuation, "ev_ebit_base_ceiling"),
            "bull_ceiling": _field(valuation, "ev_ebit_bull_ceiling"),
        },
        "source_ids": list(source_whitelist),
    }


def _scenario_qualitative_projection(value, allowed_source_ids: set[str], field=None):
    """Copy a qualitative artifact while hiding provenance forbidden to scenarios."""
    if isinstance(value, dict):
        projected = {}
        for key, nested in value.items():
            if key == "source_id":
                if nested in allowed_source_ids:
                    projected[key] = nested
                continue
            nested_field = (
                field
                if field is not None and field.endswith("source_ids")
                else key
            )
            projected[key] = _scenario_qualitative_projection(
                nested, allowed_source_ids, nested_field
            )
        return projected
    if isinstance(value, list):
        if field is not None and field.endswith("source_ids"):
            return [item for item in value if item in allowed_source_ids]
        return [
            _scenario_qualitative_projection(item, allowed_source_ids, field)
            for item in value
        ]
    if isinstance(value, tuple):
        return _scenario_qualitative_projection(list(value), allowed_source_ids, field)
    if field is not None and field.endswith("source_ids"):
        return value if value in allowed_source_ids else None
    return value


def scenario_source_whitelist(candidate) -> tuple[str, ...]:
    """Return the exact source IDs permitted in scenario assumptions."""
    return tuple(sorted(_source_ids(candidate)))


def _scenario_input_sha256(prompt) -> str:
    return sha256(
        json.dumps(
            {"system": prompt.system, "user": prompt.user},
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _validate_scenario_source_whitelist(bundles, source_whitelist) -> None:
    allowed = set(source_whitelist)
    source_ids = {
        source_id
        for bundle in bundles
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
    unknown = sorted(source_ids - allowed)
    if unknown:
        raise ScenarioAuthoringError(
            "scenario assumptions cite source IDs outside the supplied whitelist: "
            + ", ".join(unknown)
        )


def _scenario_constraints(candidate, qualitative_thesis) -> dict:
    valuation = candidate.full_results.get("valuation") or {}
    reverse_dcf = candidate.full_results.get("reverse_dcf") or {}

    def field(value, name):
        if isinstance(value, dict):
            return value.get(name)
        return getattr(value, name, None)

    return {
        "required_cases": ["bear", "base", "bull"],
        "allowed_horizons_months": [24, 36, 48],
        "case_horizon_months": qualitative_thesis.case_horizon_months,
        "all_cases_share_horizon": True,
        "historical_terminal_multiple_range": [
            field(valuation, "ev_ebit_guardrail_low"),
            field(valuation, "ev_ebit_guardrail_high"),
        ],
        "base_terminal_multiple_ceiling": field(
            valuation, "ev_ebit_base_ceiling"
        ),
        "bull_terminal_multiple_ceiling": field(
            valuation, "ev_ebit_bull_ceiling"
        ),
        "demonstrated_revenue_cagr": field(
            field(reverse_dcf, "operating_history"), "three_year_revenue_cagr"
        ),
        "demonstrated_ebit_margin": field(
            field(reverse_dcf, "operating_history"), "peak_ebit_margin"
        ),
        "net_debt_change_provenance": {
            "zero_value": "not_applicable",
            "non_zero_values": ["source_backed", "analyst_sensitivity"],
        },
        "assumption_requirements": {
            "every_value_must_be_finite": True,
            "every_assumption_requires_source_id": True,
            "every_assumption_requires_rationale": True,
            "net_debt_change_requires_mechanism": True,
            "non_zero_share_count_growth_requires_mechanism": True,
            "non_zero_distributions_per_share_requires_mechanism": True,
            "revenue_cagr_greater_than": -1.0,
            "ebit_margin_positive": True,
            "share_count_growth_greater_than": -1.0,
            "distributions_per_share_non_negative": True,
            "terminal_multiple_positive_and_ordered": True,
        },
        "case_order_requirements": {
            "bear_does_not_improve_any_driver_vs_base": True,
            "bull_does_not_worsen_any_driver_vs_base": True,
        },
        "plausibility_requirements": {
            "growth_and_margin_tolerance": 0.005,
            "base_may_not_exceed_demonstrated_bounds": True,
            "bull_may_exceed_at_most_one_demonstrated_bound": True,
        },
        "deterministic_output_requirements": {
            "base_annualized_return_spread_max": BASE_ANNUALIZED_RETURN_SPREAD_MAX,
            "calculated_by": "local_forward_scenario_engine",
            "model_must_not_author_calculated_outputs": True,
        },
        "qualitative_thesis_is_immutable": True,
    }


def _base_return_spread_diagnostic(
    analysis: ForwardScenarioAnalysis | None,
) -> dict | None:
    if analysis is None or not callable(getattr(analysis, "band", None)):
        return None
    base = analysis.band("base")
    if base is None:
        return None
    spread = base.high_annualized_return - base.low_annualized_return
    if spread <= BASE_ANNUALIZED_RETURN_SPREAD_MAX:
        return None
    return {
        "case": "base",
        "low_annualized_return": base.low_annualized_return,
        "high_annualized_return": base.high_annualized_return,
        "spread": spread,
        "maximum_spread": BASE_ANNUALIZED_RETURN_SPREAD_MAX,
        "excess_spread": spread - BASE_ANNUALIZED_RETURN_SPREAD_MAX,
    }


def _readiness_inputs(candidate) -> dict:
    from kncompanyscraper.analysis.agent.readiness import (
        assess_forward_scenario_readiness,
    )

    readiness = assess_forward_scenario_readiness(candidate)
    return {
        "status": readiness.status,
        "missing_inputs": list(readiness.missing_inputs),
        "warnings": list(readiness.warnings),
    }


def _source_ids(candidate) -> set[str]:
    ids = set()
    _collect_source_ids(candidate.research_evidence, ids)
    _collect_source_ids(candidate.full_results, ids)
    return ids


def _collect_source_ids(value, result: set[str], field_name: str | None = None):
    if isinstance(value, dict):
        for key, nested in value.items():
            nested_field = (
                field_name
                if field_name is not None and field_name.endswith("source_ids")
                else str(key)
            )
            _collect_source_ids(nested, result, nested_field)
        return
    if isinstance(value, (list, tuple)):
        for nested in value:
            _collect_source_ids(nested, result, field_name)
        return
    if is_dataclass(value):
        for field in value.__dataclass_fields__:
            _collect_source_ids(getattr(value, field), result, field)
        return
    if field_name in {"source_id", "source_ids"} and isinstance(value, str):
        result.add(value)


def _field(value, name):
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _json_value(value):
    if hasattr(value, "to_dict"):
        return _json_value(value.to_dict())
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {key: _json_value(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(nested) for nested in value]
    return value
