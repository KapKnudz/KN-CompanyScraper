import json
import math
from kncompanyscraper.analysis.agent.output_schema import (
    AssessmentClaim,
    BusinessModelProfile,
    CompanyFact,
    CompanyFactLedger,
    EvidenceCitation,
    ManagementClaimAssessment,
    ManagementCredibilityCoverage,
    MarginExpansionCase,
    RevenueResilience,
    STOCK_ANALYSIS_OUTPUT_CONTRACT,
    StockAnalysisResult,
    ThesisCatalyst,
    TimingAssessment,
    THESIS_UPDATE_OUTPUT_CONTRACT,
    ThesisUpdateResult,
)
from kncompanyscraper.analysis.valuation.forward_scenario import (
    NetDebtChangeAssumption,
    ScenarioBundle,
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
        _normalize_management_ledger_contract(payload)
        _validate_value(payload, contract, "result")
    except (json.JSONDecodeError, StockAnalysisValidationError) as exc:
        raise StockAnalysisValidationError(f"Invalid {label} JSON: {exc}") from exc
    return payload


def _normalize_management_ledger_contract(payload: dict) -> None:
    ledger = payload.get("management_credibility_ledger")
    if not isinstance(ledger, list):
        return
    for assessment in ledger:
        if not isinstance(assessment, dict):
            continue
        source_ids = list(assessment.get("source_ids", []))
        if not assessment.get("claim_source_ids") and source_ids:
            assessment["claim_source_ids"] = source_ids
        else:
            assessment.setdefault("claim_source_ids", source_ids)
        assessment.setdefault("outcome_source_ids", [])
        assessment["source_ids"] = list(
            dict.fromkeys(
                [
                    *assessment["claim_source_ids"],
                    *assessment["outcome_source_ids"],
                ]
            )
        )
    if "management_credibility_coverage" not in payload:
        assessed = sum(
            assessment.get("result") in {"kept", "delayed", "missed", "changed"}
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


def _stock_analysis_from_payload(payload: dict) -> StockAnalysisResult:
    result_data = dict(payload)
    result_data["business_model_profile"] = BusinessModelProfile(
        **payload["business_model_profile"]
    )
    result_data["margin_expansion_case"] = MarginExpansionCase(
        **payload["margin_expansion_case"]
    )
    result_data["revenue_resilience"] = RevenueResilience(
        **payload["revenue_resilience"]
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
    result_data["scenario_bundles"] = [
        ScenarioBundle(
            case=bundle["case"],
            horizon_months=bundle["horizon_months"],
            revenue_cagr=_sourced_assumption(bundle["revenue_cagr"]),
            ebit_margin=_sourced_assumption(bundle["ebit_margin"]),
            terminal_ev_ebit_low=_sourced_assumption(
                bundle["terminal_ev_ebit_low"]
            ),
            terminal_ev_ebit_high=_sourced_assumption(
                bundle["terminal_ev_ebit_high"]
            ),
            net_debt_change=_net_debt_change_assumption(
                bundle["net_debt_change"]
            ),
            share_count_growth=_sourced_assumption(bundle["share_count_growth"]),
            distributions_per_share=_sourced_assumption(
                bundle["distributions_per_share"]
            ),
            mechanism=bundle["mechanism"],
        )
        for bundle in payload["scenario_bundles"]
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


def _sourced_assumption(payload: dict) -> SourcedAssumption:
    return SourcedAssumption(
        value=payload["value"],
        source_ids=tuple(payload["source_ids"]),
        rationale=payload["rationale"],
        mechanism=payload["mechanism"],
        guardrail_exception=payload["guardrail_exception"],
    )


def _net_debt_change_assumption(payload: dict) -> NetDebtChangeAssumption:
    return NetDebtChangeAssumption(
        value=payload["value"],
        source_ids=tuple(payload["source_ids"]),
        rationale=payload["rationale"],
        mechanism=payload["mechanism"],
        provenance_type=payload["provenance_type"],
        guardrail_exception=payload["guardrail_exception"],
    )


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
