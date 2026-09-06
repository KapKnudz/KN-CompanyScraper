import json
import math
import re
from kncompanyscraper.analysis.agent.output_schema import (
    AssessmentClaim,
    OwnershipClaim,
    OwnershipBinding,
    _NullableObjectContract,
    BusinessModelProfile,
    CompanyFact,
    CompanyFactLedger,
    DecisiveEvidence,
    EvidenceCitation,
    FalsifiableCase,
    ManagementClaimAssessment,
    ManagementCredibilityCoverage,
    MarginExpansionCase,
    ActivationTriggerEvidence,
    ActivationTriggerSpec,
    MissingInformationItem,
    RevenueResilience,
    STOCK_ANALYSIS_OUTPUT_CONTRACT,
    V3_STOCK_ANALYSIS_OUTPUT_CONTRACT,
    V3_QUALITATIVE_STOCK_ANALYSIS_OUTPUT_CONTRACT,
    QUALITATIVE_STOCK_ANALYSIS_OUTPUT_CONTRACT,
    SCENARIO_AUTHORING_OUTPUT_CONTRACT,
    StockAnalysisResult,
    StructuredConclusions,
    ThesisCatalyst,
    ThesisBreakTest,
    TimingAssessment,
    THESIS_UPDATE_OUTPUT_CONTRACT,
    V3_QUALITATIVE_THESIS_UPDATE_OUTPUT_CONTRACT,
    ThesisUpdateResult,
)
from kncompanyscraper.analysis.agent.conclusion_contract import (
    project_structured_conclusions,
)
from kncompanyscraper.analysis.valuation.forward_scenario import (
    NetDebtChangeAssumption,
    ScenarioBundle,
    SourcedAssumption,
)


class StockAnalysisValidationError(ValueError):
    pass


def parse_stock_analysis_result(raw_response: str) -> StockAnalysisResult:
    raw_response = _normalize_missing_scenario_fields(raw_response)
    payload = _parse_contract(raw_response, STOCK_ANALYSIS_OUTPUT_CONTRACT, "stock-analysis")
    return _stock_analysis_from_payload(payload)


def _normalize_missing_scenario_fields(raw_response: str) -> str:
    """Supply deterministic fields that are never authored by the thesis model."""
    try:
        payload = json.loads(
            raw_response, object_pairs_hook=_object_without_duplicates
        )
    except (json.JSONDecodeError, StockAnalysisValidationError):
        return raw_response
    if not isinstance(payload, dict):
        return raw_response
    payload.setdefault("scenario_bundles", [])
    payload.setdefault("forward_scenario_analysis", None)
    payload.setdefault("historical_forecast_table", None)
    payload.setdefault("peak_margin_bridge", None)
    payload.setdefault("scenario_driver_attribution", None)
    return json.dumps(payload, ensure_ascii=False)


def parse_qualitative_stock_analysis_result(
    raw_response: str,
) -> StockAnalysisResult:
    raw_response = _normalize_qualitative_response(raw_response)
    contract = _contract_for_payload(raw_response, qualitative=True)
    payload = _parse_contract(
        raw_response,
        contract,
        "qualitative-stock-analysis",
    )
    payload["scenario_bundles"] = []
    return _stock_analysis_from_payload(payload)


def _normalize_qualitative_response(raw_response: str) -> str:
    """Remove fields owned by deterministic post-processing stages."""
    try:
        payload = json.loads(
            raw_response, object_pairs_hook=_object_without_duplicates
        )
    except (json.JSONDecodeError, StockAnalysisValidationError):
        return raw_response
    if isinstance(payload, dict):
        payload.pop("scenario_bundles", None)
        payload.pop("forward_scenario_analysis", None)
        payload.pop("historical_forecast_table", None)
        payload.pop("peak_margin_bridge", None)
        payload.pop("scenario_driver_attribution", None)
    return json.dumps(payload, ensure_ascii=False)

def _contract_for_payload(raw_response: str, *, qualitative: bool = False) -> dict:
    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError:
        return QUALITATIVE_STOCK_ANALYSIS_OUTPUT_CONTRACT if qualitative else STOCK_ANALYSIS_OUTPUT_CONTRACT
    if isinstance(payload, dict) and payload.get("thesis_card_version") == "individual-thesis-card-v3-structured-conclusions":
        return V3_QUALITATIVE_STOCK_ANALYSIS_OUTPUT_CONTRACT if qualitative else V3_STOCK_ANALYSIS_OUTPUT_CONTRACT
    return QUALITATIVE_STOCK_ANALYSIS_OUTPUT_CONTRACT if qualitative else STOCK_ANALYSIS_OUTPUT_CONTRACT


def parse_thesis_update_result(raw_response: str) -> ThesisUpdateResult:
    raw_response = _normalize_qualitative_update_response(raw_response)
    try:
        update_payload = json.loads(raw_response)
    except json.JSONDecodeError:
        update_payload = {}
    update_contract = (
        V3_QUALITATIVE_THESIS_UPDATE_OUTPUT_CONTRACT
        if isinstance(update_payload, dict)
        and isinstance(update_payload.get("thesis"), dict)
        and update_payload["thesis"].get("thesis_card_version")
        == "individual-thesis-card-v3-structured-conclusions"
        else THESIS_UPDATE_OUTPUT_CONTRACT
    )
    payload = _parse_contract(raw_response, update_contract, "thesis-update")
    return ThesisUpdateResult(
        impact=payload["impact"],
        summary=payload["summary"],
        changed_sections=payload["changed_sections"],
        thesis=_stock_analysis_from_payload(payload["thesis"]),
    )


def _normalize_qualitative_update_response(raw_response: str) -> str:
    """Accept the separate qualitative contract while tolerating old raw retries."""
    try:
        payload = json.loads(
            raw_response, object_pairs_hook=_object_without_duplicates
        )
    except (json.JSONDecodeError, StockAnalysisValidationError):
        return raw_response
    thesis = payload.get("thesis") if isinstance(payload, dict) else None
    if isinstance(thesis, dict):
        thesis.pop("scenario_bundles", None)
        thesis.pop("forward_scenario_analysis", None)
        thesis.pop("historical_forecast_table", None)
        thesis.pop("peak_margin_bridge", None)
        thesis.pop("scenario_driver_attribution", None)
        if thesis.get("thesis_card_version") != "individual-thesis-card-v3-structured-conclusions":
            thesis["scenario_bundles"] = []
            thesis["forward_scenario_analysis"] = None
            thesis["historical_forecast_table"] = None
            thesis["peak_margin_bridge"] = None
            thesis["scenario_driver_attribution"] = None
    return json.dumps(payload, ensure_ascii=False)


def parse_scenario_authoring_result(raw_response: str):
    payload = _parse_contract(
        raw_response,
        SCENARIO_AUTHORING_OUTPUT_CONTRACT,
        "scenario-authoring",
    )
    return {
        "case_horizon_months": payload["case_horizon_months"],
        "scenario_bundles": [
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
                share_count_growth=_sourced_assumption(
                    bundle["share_count_growth"]
                ),
                distributions_per_share=_sourced_assumption(
                    bundle["distributions_per_share"]
                ),
                mechanism=bundle["mechanism"],
            )
            for bundle in payload["scenario_bundles"]
        ],
    }


def _parse_contract(raw_response: str, contract: dict, label: str) -> dict:
    try:
        payload = json.loads(raw_response, object_pairs_hook=_object_without_duplicates)
        _normalize_thesis_card_fields(payload)
        _normalize_management_ledger_contract(payload)
        _normalize_ownership_claim_contract(payload, contract)
        _validate_value(payload, contract, "result")
        if payload.get("thesis_card_version") == "individual-thesis-card-v3-structured-conclusions":
            _validate_structured_claim_identifiers(payload["structured_conclusions"])
        elif isinstance(payload.get("thesis"), dict) and payload["thesis"].get(
            "thesis_card_version"
        ) == "individual-thesis-card-v3-structured-conclusions":
            _validate_structured_claim_identifiers(
                payload["thesis"]["structured_conclusions"]
            )
    except (json.JSONDecodeError, StockAnalysisValidationError) as exc:
        raise StockAnalysisValidationError(f"Invalid {label} JSON: {exc}") from exc
    return payload


_STRUCTURED_CLAIM_ID = re.compile(r"^[a-z][a-z0-9_:-]*$")


def _validate_structured_claim_identifiers(value) -> None:
    if isinstance(value, dict):
        claim_id = value.get("claim_id")
        if claim_id is not None and not _STRUCTURED_CLAIM_ID.fullmatch(claim_id):
            raise StockAnalysisValidationError(
                f"structured claim ID must be a code identifier: {claim_id!r}"
            )
        for limitation_code in value.get("limitation_codes", []):
            if not _STRUCTURED_CLAIM_ID.fullmatch(limitation_code):
                raise StockAnalysisValidationError(
                    "structured limitation codes must be code identifiers"
                )
        for child in value.values():
            _validate_structured_claim_identifiers(child)
    elif isinstance(value, list):
        for child in value:
            _validate_structured_claim_identifiers(child)


def _normalize_thesis_card_fields(payload: dict) -> None:
    """Supply fields introduced after v2 without rewriting historical cards."""
    cards = [payload]
    thesis = payload.get("thesis") if isinstance(payload, dict) else None
    if isinstance(thesis, dict):
        cards.append(thesis)
    for card in cards:
        if (
            not isinstance(card, dict)
            or "verdict" not in card
            or "company_id" not in card
        ):
            continue
        if card.get("thesis_card_version") == "individual-thesis-card-v3-structured-conclusions":
            continue
        card.setdefault("latent_case_type", None)
        card.setdefault("activation_trigger_spec", None)
        card.setdefault("activation_trigger_evidence", [])
        card.setdefault("missing_information_details", [])
        card.setdefault(
            "falsifiable_case",
            {
                "statement": card.get("one_sentence_thesis", ""),
                "falsification_test": "",
                "horizon_months": card.get("case_horizon_months"),
                "source_ids": [],
            },
        )
        card.setdefault("strongest_confirming_evidence", None)
        card.setdefault("strongest_disconfirming_evidence", None)
        card.setdefault("thesis_break_tests", [])
        resilience = card.get("revenue_resilience")
        if isinstance(resilience, dict):
            resilience.setdefault("recurring_source_ids", [])
            resilience.setdefault("variable_source_ids", [])


def _typed_claim(value: dict) -> "TypedClaim":
    from kncompanyscraper.analysis.agent.conclusion_contract import TypedClaim
    return TypedClaim(
        claim_id=value["claim_id"], domain=value["domain"], predicate=value["predicate"],
        value=value["value"], source_ids=tuple(value["source_ids"]),
        limitation_codes=tuple(value["limitation_codes"]),
    )


def _structured_conclusions_from_payload(value: dict) -> StructuredConclusions:
    from kncompanyscraper.analysis.agent.conclusion_contract import (
        FalsifiableCaseComponent, HeadlineCase,
    )
    headline = value["headline_case"]
    falsifiable = value["falsifiable_case"]
    return StructuredConclusions(
        headline_case=HeadlineCase(
            case_ref=headline["case_ref"], horizon_months=headline["horizon_months"],
            revenue_mechanism=headline["revenue_mechanism"],
            profitability_state=headline["profitability_state"],
            expectation_refs=tuple(headline["expectation_refs"]),
            break_condition=_typed_claim(headline["break_condition"]),
        ),
        falsifiable_case=FalsifiableCaseComponent(
            case_ref=falsifiable["case_ref"], horizon_months=falsifiable["horizon_months"],
            baseline_refs=tuple(falsifiable["baseline_refs"]),
            falsification=_typed_claim(falsifiable["falsification"]),
        ),
        evidence_claims=tuple(_typed_claim(item) for item in value["evidence_claims"]),
        break_tests=tuple(_typed_claim(item) for item in value["break_tests"]),
        management_claims=tuple(_typed_claim(item) for item in value["management_claims"]),
        management_ledger=tuple(_typed_claim(item) for item in value["management_ledger"]),
        company_facts=tuple(_typed_claim(item) for item in value["company_facts"]),
        business_model_facts=tuple(_typed_claim(item) for item in value["business_model_facts"]),
        margin_facts=tuple(_typed_claim(item) for item in value["margin_facts"]),
        timing_facts=tuple(_typed_claim(item) for item in value["timing_facts"]),
        limitation_codes=tuple(value["limitation_codes"]),
        trigger=_typed_claim(value["trigger"]) if value["trigger"] is not None else None,
        revenue_resilience=_typed_claim(value["revenue_resilience"]),
        reverse_dcf_assessment=value["reverse_dcf_assessment"],
    )


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


def _normalize_ownership_claim_contract(payload: dict, contract: dict) -> None:
    thesis = payload.get("thesis")
    thesis_contract = contract.get("thesis")
    if isinstance(thesis, dict) and isinstance(thesis_contract, dict):
        if "ownership_claims" in thesis_contract:
            thesis.setdefault("ownership_claims", [])
    elif "ownership_claims" in contract:
        payload.setdefault("ownership_claims", [])


def _stock_analysis_from_payload(payload: dict) -> StockAnalysisResult:
    result_data = dict(payload)
    if payload.get("thesis_card_version") == "individual-thesis-card-v3-structured-conclusions":
        result_data.update(
            project_structured_conclusions(
                payload["structured_conclusions"],
                payload.get("ownership_claims", []),
            )
        )
        result_data["structured_conclusions"] = _structured_conclusions_from_payload(
            payload["structured_conclusions"]
        )
        payload = result_data
    result_data["falsifiable_case"] = FalsifiableCase(
        **payload["falsifiable_case"]
    )
    result_data["business_model_profile"] = BusinessModelProfile(
        **payload["business_model_profile"]
    )
    result_data["margin_expansion_case"] = MarginExpansionCase(
        **payload["margin_expansion_case"]
    )
    result_data["revenue_resilience"] = RevenueResilience(
        **payload["revenue_resilience"]
    )
    trigger_spec = payload.get("activation_trigger_spec")
    result_data["activation_trigger_spec"] = (
        ActivationTriggerSpec(**trigger_spec) if trigger_spec is not None else None
    )
    result_data["activation_trigger_evidence"] = [
        ActivationTriggerEvidence(**item)
        for item in payload.get("activation_trigger_evidence", [])
    ]
    result_data["missing_information_details"] = [
        MissingInformationItem(**item)
        for item in payload.get("missing_information_details", [])
    ]
    for field_name in (
        "strongest_confirming_evidence",
        "strongest_disconfirming_evidence",
    ):
        evidence = payload.get(field_name)
        result_data[field_name] = (
            DecisiveEvidence(**evidence) if evidence is not None else None
        )
    result_data["thesis_break_tests"] = [
        ThesisBreakTest(**item) for item in payload.get("thesis_break_tests", [])
    ]
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
        for bundle in payload.get("scenario_bundles", [])
    ]
    result_data["management_credibility_ledger"] = [
        ManagementClaimAssessment(**assessment)
        for assessment in payload.get("management_credibility_ledger", [])
    ]
    result_data["management_credibility_coverage"] = ManagementCredibilityCoverage(
        **payload["management_credibility_coverage"]
    )
    result_data["management_claims"] = [
        AssessmentClaim(**claim) for claim in payload["management_claims"]
    ]
    result_data["ownership_claims"] = [
        (
            OwnershipClaim(
                claim_kind=claim["claim_kind"],
                subject_role=claim["subject_role"],
                measure=claim["measure"],
                binding=OwnershipBinding(**claim["binding"]),
                limitation_codes=claim["limitation_codes"],
            )
            if "claim_kind" in claim
            else AssessmentClaim(**claim)
        )
        for claim in payload["ownership_claims"]
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
    )


def _net_debt_change_assumption(payload: dict) -> NetDebtChangeAssumption:
    return NetDebtChangeAssumption(
        value=payload["value"],
        source_ids=tuple(payload["source_ids"]),
        rationale=payload["rationale"],
        mechanism=payload["mechanism"],
        provenance_type=payload["provenance_type"],
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
        if value is None and isinstance(specification, _NullableObjectContract):
            return
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
    if option == "boolean":
        return isinstance(value, bool)
    return value == option
