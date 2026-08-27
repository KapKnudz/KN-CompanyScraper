import json
import math
from copy import deepcopy

from kncompanyscraper.analysis.agent.output_schema import (
    AssessmentClaim,
    BusinessModelProfile,
    CompanyFact,
    CompanyFactLedger,
    EvidenceCitation,
    ManagementClaimAssessment,
    ManagementCredibilityCoverage,
    MarginExpansionCase,
    STOCK_ANALYSIS_OUTPUT_CONTRACT,
    StockAnalysisResult,
    ThesisCatalyst,
    TimingAssessment,
    THESIS_UPDATE_OUTPUT_CONTRACT,
    ThesisUpdateResult,
    ValuationScenario,
)
from kncompanyscraper.analysis.valuation.forward_scenario import (
    NetDebtChangeAssumption,
    ScenarioEndpoint,
    SourcedAssumption,
)


class StockAnalysisValidationError(ValueError):
    pass


SCENARIO_ASSUMPTION_NAMES = (
    "revenue_cagr",
    "ebit_margin",
    "terminal_ev_ebit",
    "net_debt",
    "net_debt_change",
    "share_count_growth",
    "distributions_per_share",
)
COMPACT_ENDPOINT_FIELDS = {
    "kind",
    "side",
    "horizon_months",
    "base_endpoint",
    "base_assumptions",
    "overrides",
}
COMPACT_OVERRIDE_FIELDS = {"field", "assumption"}


def parse_stock_analysis_result(raw_response: str) -> StockAnalysisResult:
    payload = _parse_contract(raw_response, STOCK_ANALYSIS_OUTPUT_CONTRACT, "stock-analysis")
    return _stock_analysis_from_payload(payload)


def parse_thesis_update_result(raw_response: str) -> ThesisUpdateResult:
    payload = _parse_contract(raw_response, THESIS_UPDATE_OUTPUT_CONTRACT, "thesis-update")
    return ThesisUpdateResult(
        impact=payload["impact"],
        summary=payload["summary"],
        changed_sections=payload["changed_sections"],
        thesis=_stock_analysis_from_payload(payload["thesis"]),
    )


def _parse_contract(raw_response: str, contract: dict, label: str) -> dict:
    try:
        payload = json.loads(raw_response, object_pairs_hook=_object_without_duplicates)
        payload = _normalize_compact_scenarios(payload)
        _validate_value(payload, contract, "result")
    except (json.JSONDecodeError, StockAnalysisValidationError) as exc:
        raise StockAnalysisValidationError(f"Invalid {label} JSON: {exc}") from exc
    return payload


def _normalize_compact_scenarios(value):
    if isinstance(value, list):
        return [_normalize_compact_scenarios(item) for item in value]
    if not isinstance(value, dict):
        return value

    normalized = {
        key: _normalize_compact_scenarios(item) for key, item in value.items()
    }
    _normalize_management_ledger_contract(normalized)
    endpoints = normalized.get("forward_scenario_assumptions")
    if isinstance(endpoints, list) and endpoints:
        normalized["forward_scenario_assumptions"] = _expand_compact_endpoints(
            endpoints
        )
    return normalized


def _normalize_management_ledger_contract(payload: dict) -> None:
    ledger = payload.get("management_credibility_ledger")
    if not isinstance(ledger, list):
        return

    for assessment in ledger:
        if not isinstance(assessment, dict):
            continue
        legacy_source_ids = list(assessment.get("source_ids", []))
        assessment.setdefault("claim_source_ids", legacy_source_ids)
        assessment.setdefault("outcome_source_ids", [])
        assessment.setdefault(
            "source_ids",
            list(
                dict.fromkeys(
                    [
                        *assessment["claim_source_ids"],
                        *assessment["outcome_source_ids"],
                    ]
                )
            ),
        )

    if "management_credibility_coverage" not in payload:
        assessed = sum(
            assessment.get("result")
            in {"kept", "delayed", "missed", "changed"}
            for assessment in ledger
            if isinstance(assessment, dict)
        )
        pending = sum(
            assessment.get("result") == "unverifiable"
            for assessment in ledger
            if isinstance(assessment, dict)
        )
        payload["management_credibility_coverage"] = {
            "eligible_claim_count": assessed + pending,
            "assessed_claim_count": assessed,
            "pending_claim_count": pending,
            "omitted_claim_count": 0,
            "omission_reasons": [],
        }


def _expand_compact_endpoints(endpoints: list[dict]) -> list[dict]:
    if not all(isinstance(endpoint, dict) for endpoint in endpoints):
        raise StockAnalysisValidationError(
            "compact forward scenario endpoint must be an object"
        )
    compact_markers = {"base_endpoint", "base_assumptions", "overrides"}
    compact = [bool(compact_markers.intersection(endpoint)) for endpoint in endpoints]
    if not any(compact):
        return endpoints
    if not all(compact):
        raise StockAnalysisValidationError(
            "forward scenario endpoints cannot mix compact and expanded forms"
        )

    raw_by_key = {}
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            raise StockAnalysisValidationError(
                "compact forward scenario endpoint must be an object"
            )
        unexpected = set(endpoint) - COMPACT_ENDPOINT_FIELDS
        missing = COMPACT_ENDPOINT_FIELDS - set(endpoint)
        if missing:
            raise StockAnalysisValidationError(
                "compact endpoint is missing fields: " + ", ".join(sorted(missing))
            )
        if unexpected:
            raise StockAnalysisValidationError(
                "compact endpoint contains unexpected fields: "
                + ", ".join(sorted(unexpected))
            )
        key = _compact_endpoint_key(endpoint)
        if key in raw_by_key:
            raise StockAnalysisValidationError(
                f"duplicate compact scenario endpoint: {key}"
            )
        raw_by_key[key] = endpoint

    expanded_by_key = {}
    resolving = []

    def resolve(key):
        if key in expanded_by_key:
            return expanded_by_key[key]
        if key in resolving:
            cycle = " -> ".join([*resolving, key])
            raise StockAnalysisValidationError(
                f"cyclic compact scenario inheritance: {cycle}"
            )
        endpoint = raw_by_key.get(key)
        if endpoint is None:
            raise StockAnalysisValidationError(
                f"compact scenario references missing endpoint: {key}"
            )

        resolving.append(key)
        base_key = endpoint["base_endpoint"]
        if base_key is None:
            if endpoint["base_assumptions"] is None:
                raise StockAnalysisValidationError(
                    f"{key} requires base_assumptions when base_endpoint is null"
                )
            assumptions = _validate_compact_assumptions(
                endpoint["base_assumptions"], key
            )
            if endpoint["overrides"]:
                raise StockAnalysisValidationError(
                    f"{key} cannot override assumptions without a base endpoint"
                )
        else:
            if not isinstance(base_key, str) or not base_key.strip():
                raise StockAnalysisValidationError(
                    f"{key}.base_endpoint must be a non-empty endpoint key or null"
                )
            if endpoint["base_assumptions"] is not None:
                raise StockAnalysisValidationError(
                    f"{key} must omit base_assumptions when inheriting"
                )
            base = resolve(base_key)
            if endpoint["horizon_months"] != base["horizon_months"]:
                raise StockAnalysisValidationError(
                    f"{key} must use the inherited endpoint horizon"
                )
            assumptions = {
                name: deepcopy(base[name]) for name in SCENARIO_ASSUMPTION_NAMES
            }
            _apply_compact_overrides(assumptions, endpoint["overrides"], key)
            if endpoint["kind"] == "bear_multiple_compression":
                expected_base = f"base_{endpoint['side']}"
                if base_key != expected_base:
                    raise StockAnalysisValidationError(
                        f"{key} must inherit {expected_base}"
                    )
                override_fields = {
                    override["field"] for override in endpoint["overrides"]
                }
                if override_fields != {"terminal_ev_ebit"}:
                    raise StockAnalysisValidationError(
                        f"{key} may override only terminal_ev_ebit"
                    )

        expanded_by_key[key] = {
            "kind": endpoint["kind"],
            "side": endpoint["side"],
            "horizon_months": endpoint["horizon_months"],
            **assumptions,
        }
        resolving.pop()
        return expanded_by_key[key]

    return [resolve(_compact_endpoint_key(endpoint)) for endpoint in endpoints]


def _compact_endpoint_key(endpoint: dict) -> str:
    kind = endpoint.get("kind")
    side = endpoint.get("side")
    if not isinstance(kind, str) or not isinstance(side, str):
        raise StockAnalysisValidationError(
            "compact scenario endpoint kind and side must be strings"
        )
    return f"{kind}_{side}"


def _validate_compact_assumptions(assumptions, endpoint_key: str) -> dict:
    if not isinstance(assumptions, dict):
        raise StockAnalysisValidationError(
            f"{endpoint_key}.base_assumptions must be an object"
        )
    missing = set(SCENARIO_ASSUMPTION_NAMES) - set(assumptions)
    unexpected = set(assumptions) - set(SCENARIO_ASSUMPTION_NAMES)
    if missing:
        raise StockAnalysisValidationError(
            f"{endpoint_key}.base_assumptions is missing fields: "
            + ", ".join(sorted(missing))
        )
    if unexpected:
        raise StockAnalysisValidationError(
            f"{endpoint_key}.base_assumptions contains unexpected fields: "
            + ", ".join(sorted(unexpected))
        )
    for name in SCENARIO_ASSUMPTION_NAMES:
        _validate_compact_assumption(assumptions[name], name, endpoint_key)
    return assumptions


def _validate_compact_assumption(assumption, field: str, endpoint_key: str) -> None:
    if not isinstance(assumption, dict):
        raise StockAnalysisValidationError(
            f"{endpoint_key}.{field} assumption must be an object"
        )
    expected = {
        "value",
        "source_ids",
        "rationale",
        "guardrail_exception",
    }
    if field == "net_debt_change":
        expected.update({"mechanism", "provenance_type"})
    missing = expected - set(assumption)
    unexpected = set(assumption) - expected
    if missing:
        raise StockAnalysisValidationError(
            f"{endpoint_key}.{field} is missing fields: "
            + ", ".join(sorted(missing))
        )
    if unexpected:
        raise StockAnalysisValidationError(
            f"{endpoint_key}.{field} contains unexpected fields: "
            + ", ".join(sorted(unexpected))
        )


def _apply_compact_overrides(assumptions, overrides, endpoint_key: str) -> None:
    if not isinstance(overrides, list):
        raise StockAnalysisValidationError(f"{endpoint_key}.overrides must be an array")
    seen = set()
    for override in overrides:
        if not isinstance(override, dict):
            raise StockAnalysisValidationError(
                f"{endpoint_key} override must be an object"
            )
        missing = COMPACT_OVERRIDE_FIELDS - set(override)
        unexpected = set(override) - COMPACT_OVERRIDE_FIELDS
        if missing:
            raise StockAnalysisValidationError(
                f"{endpoint_key} override is missing fields: "
                + ", ".join(sorted(missing))
            )
        if unexpected:
            raise StockAnalysisValidationError(
                f"{endpoint_key} override contains unexpected fields: "
                + ", ".join(sorted(unexpected))
            )
        field = override["field"]
        if field not in SCENARIO_ASSUMPTION_NAMES:
            raise StockAnalysisValidationError(
                f"{endpoint_key} override has an illegal field: {field}"
            )
        if field in seen:
            raise StockAnalysisValidationError(
                f"{endpoint_key} contains duplicate override: {field}"
            )
        _validate_compact_assumption(override["assumption"], field, endpoint_key)
        assumptions[field] = override["assumption"]
        seen.add(field)


def _stock_analysis_from_payload(payload: dict) -> StockAnalysisResult:
    result_data = dict(payload)
    result_data["business_model_profile"] = BusinessModelProfile(
        **payload["business_model_profile"]
    )
    result_data["margin_expansion_case"] = MarginExpansionCase(
        **payload["margin_expansion_case"]
    )
    timing = payload["timing_assessment"]
    result_data["timing_assessment"] = TimingAssessment(
        **{
            **timing,
            "catalysts": [
                ThesisCatalyst(**catalyst) for catalyst in timing["catalysts"]
            ],
        }
    )
    result_data["company_fact_ledger"] = CompanyFactLedger(
        **{
            heading: [CompanyFact(**fact) for fact in facts]
            for heading, facts in payload["company_fact_ledger"].items()
        }
    )
    result_data["valuation_scenarios"] = [
        ValuationScenario(**scenario) for scenario in payload["valuation_scenarios"]
    ]
    result_data["forward_scenario_assumptions"] = [
        ScenarioEndpoint(
            kind=endpoint["kind"],
            side=endpoint["side"],
            horizon_months=endpoint["horizon_months"],
            **{
                name: (
                    NetDebtChangeAssumption(
                        value=endpoint[name]["value"],
                        source_ids=tuple(endpoint[name]["source_ids"]),
                        rationale=endpoint[name]["rationale"],
                        mechanism=endpoint[name]["mechanism"],
                        provenance_type=endpoint[name]["provenance_type"],
                        guardrail_exception=endpoint[name]["guardrail_exception"],
                    )
                    if name == "net_debt_change"
                    else SourcedAssumption(
                    value=endpoint[name]["value"],
                    source_ids=tuple(endpoint[name]["source_ids"]),
                    rationale=endpoint[name]["rationale"],
                    guardrail_exception=endpoint[name]["guardrail_exception"],
                    )
                )
                for name in (
                    "revenue_cagr",
                    "ebit_margin",
                    "terminal_ev_ebit",
                    "net_debt",
                    "net_debt_change",
                    "share_count_growth",
                    "distributions_per_share",
                )
            },
        )
        for endpoint in payload["forward_scenario_assumptions"]
    ]
    result_data["management_credibility_ledger"] = [
        ManagementClaimAssessment(**assessment)
        for assessment in payload["management_credibility_ledger"]
    ]
    result_data["management_credibility_coverage"] = ManagementCredibilityCoverage(
        **payload["management_credibility_coverage"]
    )
    result_data["management_claims"] = [
        AssessmentClaim(**claim) for claim in payload["management_claims"]
    ]
    result_data["insider_claims"] = [
        AssessmentClaim(**claim) for claim in payload["insider_claims"]
    ]
    result_data["citations"] = [
        EvidenceCitation(**citation) for citation in payload["citations"]
    ]
    return StockAnalysisResult(**result_data)


def _object_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise StockAnalysisValidationError(f"duplicate field {key!r}")
        result[key] = value
    return result


def _validate_value(value, specification, path: str) -> None:
    if isinstance(specification, dict):
        if not isinstance(value, dict):
            raise StockAnalysisValidationError(f"{path} must be an object")

        expected = set(specification)
        actual = set(value)
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        if missing:
            raise StockAnalysisValidationError(f"{path} is missing fields: {', '.join(missing)}")
        if unexpected:
            raise StockAnalysisValidationError(
                f"{path} contains unexpected fields: {', '.join(unexpected)}"
            )

        for key, nested_specification in specification.items():
            _validate_value(value[key], nested_specification, f"{path}.{key}")
        return

    if isinstance(specification, list):
        if not isinstance(value, list):
            raise StockAnalysisValidationError(f"{path} must be an array")
        if not specification:
            if value:
                raise StockAnalysisValidationError(f"{path} must be empty")
            return
        item_specification = specification[0]
        for index, item in enumerate(value):
            _validate_value(item, item_specification, f"{path}[{index}]")
        return

    options = specification.split(" | ")
    if not any(_matches_option(value, option) for option in options):
        raise StockAnalysisValidationError(f"{path} must match {specification!r}")


def _matches_option(value, option: str) -> bool:
    if option == "null":
        return value is None
    if option == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if option == "number":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and (not isinstance(value, float) or math.isfinite(value))
        )
    if option == "string":
        return isinstance(value, str)
    return value == option
