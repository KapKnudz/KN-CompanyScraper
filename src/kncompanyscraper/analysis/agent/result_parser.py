import json
import math

from kncompanyscraper.analysis.agent.output_schema import (
    BusinessModelProfile,
    CompanyFact,
    CompanyFactLedger,
    EvidenceCitation,
    ManagementClaimAssessment,
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
    ScenarioEndpoint,
    SourcedAssumption,
)


class StockAnalysisValidationError(ValueError):
    pass


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
    except (json.JSONDecodeError, StockAnalysisValidationError) as exc:
        raise StockAnalysisValidationError(f"Invalid {label} JSON: {exc}") from exc

    _validate_value(payload, contract, "result")
    return payload


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
                name: SourcedAssumption(
                    value=endpoint[name]["value"],
                    source_ids=tuple(endpoint[name]["source_ids"]),
                    rationale=endpoint[name]["rationale"],
                    guardrail_exception=endpoint[name]["guardrail_exception"],
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
