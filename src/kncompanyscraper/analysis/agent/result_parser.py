import json
import math
import re
from datetime import date
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
    ManagementCredibilitySpecialistOutput,
    ManagementLedgerRow,
    BusinessModelSpecialistOutput,
    GrowthValuationSpecialistOutput,
    InsiderOwnershipSpecialistOutput,
    MarginSpecialistOutput,
    SellConditionsSpecialistOutput,
    SellConditionAssessment,
    SellConditionActivationBlocker,
    SellConditionStatus,
    ManagementCoverageState,
    ManagementCoverageTier,
    ManagementDataSourceType,
    ManagementLedgerResult,
    ManagementPatternState,
    SpecialistAgentName,
    SpecialistClaim,
    SpecialistClaimDirection,
    SpecialistConfidence,
    SpecialistMissingInformation,
    SpecialistOutput,
    SpecialistStatus,
    THESIS_BREAK_TYPES,
    _SPECIALIST_DOMAIN_CONTRACTS,
    _specialist_envelope_contract,
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
    contract = _contract_for_payload(raw_response)
    payload = _parse_contract(raw_response, contract, "stock-analysis")
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


def parse_specialist_output(raw_response: str) -> SpecialistOutput:
    """Parse and semantically validate one non-authoritative specialist output."""
    try:
        initial = json.loads(
            raw_response, object_pairs_hook=_object_without_duplicates
        )
        agent_name = SpecialistAgentName(initial.get("agent_name"))
        status = SpecialistStatus(initial.get("status"))
    except (
        json.JSONDecodeError,
        StockAnalysisValidationError,
        ValueError,
        TypeError,
        AttributeError,
    ) as exc:
        raise StockAnalysisValidationError(
            f"Invalid specialist-output JSON: {exc}"
        ) from exc
    contract = _specialist_envelope_contract()
    domain_name = agent_name.value
    if status is SpecialistStatus.COMPLETE and domain_name not in initial:
        raise StockAnalysisValidationError(
            f"complete specialist output requires {domain_name} payload"
        )
    if domain_name in initial:
        contract[domain_name] = _SPECIALIST_DOMAIN_CONTRACTS[domain_name]
    payload = _parse_contract(raw_response, contract, "specialist-output")
    _validate_specialist_output(payload, agent_name)

    domain = {}
    if "business_model" in payload:
        business = payload["business_model"]
        domain["business_model"] = BusinessModelSpecialistOutput(
            **{
                **business,
                "claims": [_specialist_claim(item) for item in business["claims"]],
            }
        )
    if "management_credibility" in payload:
        management = payload["management_credibility"]
        coverage_payload = {
            **management["coverage"],
            "coverage_tier": ManagementCoverageTier(
                management["coverage"]["coverage_tier"]
            ),
            "coverage_state": ManagementCoverageState(
                management["coverage"]["coverage_state"]
            ),
            "data_source_type": ManagementDataSourceType(
                management["coverage"]["data_source_type"]
            ),
            "confidence_cap": SpecialistConfidence(
                management["coverage"]["confidence_cap"]
            ),
        }
        coverage = ManagementCredibilityCoverage(**coverage_payload)
        domain["management_credibility"] = ManagementCredibilitySpecialistOutput(
            coverage=coverage,
            pattern_state=ManagementPatternState(management["pattern_state"]),
            ledger=[
                ManagementLedgerRow(
                    **row, result=ManagementLedgerResult(row["result"])
                )
                for row in management["ledger"]
            ],
            claims=[_specialist_claim(item) for item in management["claims"]],
        )
    if "margin" in payload:
        domain["margin"] = MarginSpecialistOutput(**payload["margin"])
    if "insider_ownership" in payload:
        insider = payload["insider_ownership"]
        domain["insider_ownership"] = InsiderOwnershipSpecialistOutput(
            **{
                **insider,
                "event_claims": [
                    _specialist_claim(item) for item in insider["event_claims"]
                ],
            }
        )
    if "growth_valuation" in payload:
        growth = payload["growth_valuation"]
        domain["growth_valuation"] = GrowthValuationSpecialistOutput(
            **{
                **growth,
                "claims": [_specialist_claim(item) for item in growth["claims"]],
            }
        )
    if "sell_conditions" in payload:
        sell = payload["sell_conditions"]
        domain["sell_conditions"] = SellConditionsSpecialistOutput(
            tests=[
                SellConditionAssessment(
                    **{
                        **test,
                        "current_break_status": SellConditionStatus(
                            test["current_break_status"]
                        ),
                    }
                )
                for test in sell["tests"]
            ],
            current_break_status=SellConditionStatus(sell["current_break_status"]),
            activation_blockers=[
                SellConditionActivationBlocker(**blocker)
                for blocker in sell["activation_blockers"]
            ],
        )
    return SpecialistOutput(
        schema_version=payload["schema_version"],
        run_id=payload["run_id"],
        agent_name=agent_name,
        company_id=payload["company_id"],
        ticker=payload["ticker"],
        evidence_as_of=payload["evidence_as_of"],
        status=SpecialistStatus(payload["status"]),
        confidence=SpecialistConfidence(payload["confidence"]),
        confidence_cap=SpecialistConfidence(payload["confidence_cap"]),
        claims=[_specialist_claim(item) for item in payload["claims"]],
        missing_information=[
            SpecialistMissingInformation(**item)
            for item in payload["missing_information"]
        ],
        packet_hash=payload["packet_hash"],
        **domain,
    )


def validate_specialist_output(raw_response: str) -> SpecialistOutput:
    """Validate a specialist response without routing or persisting it."""
    return parse_specialist_output(raw_response)


def _specialist_claim(value: dict) -> SpecialistClaim:
    return SpecialistClaim(
        claim_id=value["claim_id"],
        domain=value["domain"],
        predicate=value["predicate"],
        value=value["value"],
        direction=SpecialistClaimDirection(value["direction"]),
        source_ids=list(value["source_ids"]),
        limitation_codes=list(value["limitation_codes"]),
        depends_on_claim_ids=list(value["depends_on_claim_ids"]),
    )


def _validate_specialist_output(payload: dict, agent_name: SpecialistAgentName) -> None:
    confidence_rank = {"low": 0, "medium": 1, "high": 2}
    if confidence_rank[payload["confidence"]] > confidence_rank[payload["confidence_cap"]]:
        raise StockAnalysisValidationError(
            "specialist confidence cannot exceed confidence_cap"
        )
    try:
        date.fromisoformat(payload["evidence_as_of"])
    except ValueError as exc:
        raise StockAnalysisValidationError(
            "specialist evidence_as_of must be an ISO date"
        ) from exc

    claim_ids = []
    claims = list(payload["claims"])
    domain = payload.get(agent_name.value) or {}
    for claim in claims + list(domain.get("claims", [])) + list(
        domain.get("event_claims", [])
    ):
        claim_id = claim["claim_id"]
        if not _SPECIALIST_CLAIM_ID.fullmatch(claim_id):
            raise StockAnalysisValidationError(
                f"specialist claim ID must be a code identifier: {claim_id!r}"
            )
        if claim_id in claim_ids:
            raise StockAnalysisValidationError(
                f"duplicate specialist claim ID: {claim_id}"
            )
        claim_ids.append(claim_id)
        if claim["direction"] != "unassessable" and not claim["source_ids"]:
            raise StockAnalysisValidationError(
                f"specialist claim {claim_id} requires source_ids unless unassessable"
            )
        if len(claim["source_ids"]) != len(set(claim["source_ids"])):
            raise StockAnalysisValidationError(
                f"specialist claim {claim_id} contains duplicate source IDs"
            )

    if agent_name == SpecialistAgentName.MANAGEMENT_CREDIBILITY:
        _validate_specialist_management(payload, claim_ids)
        coverage = payload.get("management_credibility", {}).get("coverage")
        if coverage is not None and confidence_rank[coverage["confidence_cap"]] > confidence_rank[payload["confidence_cap"]]:
            raise StockAnalysisValidationError(
                "management coverage confidence_cap cannot exceed envelope confidence_cap"
            )
        if coverage is not None and confidence_rank[payload["confidence"]] > confidence_rank[coverage["confidence_cap"]]:
            raise StockAnalysisValidationError(
                "specialist confidence cannot exceed management coverage confidence_cap"
            )
    if agent_name == SpecialistAgentName.SELL_CONDITIONS:
        _validate_specialist_sell_conditions(payload)


def _validate_specialist_sell_conditions(payload: dict) -> None:
    sell = payload.get("sell_conditions")
    if sell is None:
        return
    required_types = set(THESIS_BREAK_TYPES)
    actual_types = [test["break_type"] for test in sell["tests"]]
    if set(actual_types) != required_types or len(actual_types) != len(required_types):
        raise StockAnalysisValidationError(
            "sell conditions must contain exactly one test for each thesis break type"
        )
    for test in sell["tests"]:
        status = test["current_break_status"]
        if len(test["source_ids"]) != len(set(test["source_ids"])):
            raise StockAnalysisValidationError(
                f"sell condition {test['break_type']} contains duplicate source IDs"
            )
        if len(test["claim_ids"]) != len(set(test["claim_ids"])):
            raise StockAnalysisValidationError(
                f"sell condition {test['break_type']} contains duplicate claim IDs"
            )
        for claim_id in test["claim_ids"]:
            if not _SPECIALIST_CLAIM_ID.fullmatch(claim_id):
                raise StockAnalysisValidationError(
                    f"sell condition claim ID must be a code identifier: {claim_id!r}"
                )
        if status != "unassessable" and not test["source_ids"]:
            raise StockAnalysisValidationError(
                "assessable sell conditions require source_ids"
            )
        if status != "unassessable" and not test["claim_ids"]:
            raise StockAnalysisValidationError(
                "assessable sell conditions require claim_ids"
            )
        _validate_causal_sell_condition(test)

    for blocker in sell["activation_blockers"]:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", blocker["blocker_code"]):
            raise StockAnalysisValidationError(
                f"sell activation blocker code must be stable: {blocker['blocker_code']!r}"
            )
        for field_name in ("source_ids", "claim_ids"):
            values = blocker[field_name]
            if len(values) != len(set(values)):
                raise StockAnalysisValidationError(
                    f"sell activation blocker contains duplicate {field_name}"
                )
        for claim_id in blocker["claim_ids"]:
            if not _SPECIALIST_CLAIM_ID.fullmatch(claim_id):
                raise StockAnalysisValidationError(
                    f"sell activation blocker claim ID must be a code identifier: {claim_id!r}"
                )


def _validate_causal_sell_condition(test: dict) -> None:
    if test["current_break_status"] != "triggered":
        return
    price_observables = {"price", "share price", "stock price", "market price"}
    observable = test["observable_metric_or_event"].strip().casefold()
    if test["break_type"] != "valuation_overshoot" and observable in price_observables:
        raise StockAnalysisValidationError(
            "triggered sell conditions must identify a causal thesis break, not price alone"
        )


def _validate_specialist_management(payload: dict, claim_ids: list[str]) -> None:
    management = payload.get("management_credibility")
    if management is None:
        return
    coverage = management["coverage"]
    quarters = coverage["quarters_covered"]
    if quarters < 0:
        raise StockAnalysisValidationError(
            "management quarters_covered must be non-negative"
        )
    tier_by_quarters = (
        (3, "no_ledger", "insufficient_for_pattern_recognition", "low"),
        (7, "partial_coverage", "partial_coverage", None),
    )
    for maximum, expected_tier, expected_state, expected_cap in tier_by_quarters:
        if quarters <= maximum:
            if coverage["coverage_tier"] != expected_tier:
                raise StockAnalysisValidationError(
                    f"management coverage tier for {quarters} quarters must be {expected_tier}"
                )
            if coverage["coverage_state"] != expected_state:
                raise StockAnalysisValidationError(
                    f"management coverage state for {quarters} quarters must be {expected_state}"
                )
            if expected_cap and coverage["confidence_cap"] != expected_cap:
                raise StockAnalysisValidationError(
                    "management coverage from 0-3 quarters must cap confidence at low"
                )
            if quarters >= 4 and coverage["confidence_cap"] == "high":
                raise StockAnalysisValidationError(
                    "management coverage from 4-7 quarters cannot cap confidence at high"
                )
            break
    else:
        if coverage["coverage_tier"] != "full_coverage":
            raise StockAnalysisValidationError(
                "management coverage from 8 or more quarters must be full_coverage"
            )
        if coverage["coverage_state"] != "full_coverage":
            raise StockAnalysisValidationError(
                "management coverage from 8 or more quarters must be full_coverage state"
            )

    count_fields = (
        "eligible_claim_count",
        "assessed_claim_count",
        "pending_claim_count",
        "omitted_claim_count",
    )
    if any(coverage[field] < 0 for field in count_fields):
        raise StockAnalysisValidationError(
            "management claim counts must be non-negative"
        )
    counts = coverage["assessed_claim_count"] + coverage["pending_claim_count"]
    counts += coverage["omitted_claim_count"]
    if coverage["eligible_claim_count"] != counts:
        raise StockAnalysisValidationError(
            "management eligible_claim_count must equal assessed, pending, and omitted counts"
        )
    assessed_results = {"kept", "delayed", "missed", "external_shock"}
    pending_results = {"unverifiable", "too_vague_to_test"}
    assessed_count = sum(
        row["result"] in assessed_results for row in management["ledger"]
    )
    pending_count = sum(
        row["result"] in pending_results for row in management["ledger"]
    )
    if coverage["assessed_claim_count"] != assessed_count:
        raise StockAnalysisValidationError(
            "management assessed_claim_count must match ledger rows"
        )
    if coverage["pending_claim_count"] != pending_count:
        raise StockAnalysisValidationError(
            "management pending_claim_count must match ledger rows"
        )
    if coverage["omitted_claim_count"] and not coverage["omission_reasons"]:
        raise StockAnalysisValidationError(
            "omitted management claims require omission_reasons"
        )
    if not coverage["omitted_claim_count"] and coverage["omission_reasons"]:
        raise StockAnalysisValidationError(
            "management omission_reasons require omitted claims"
        )
    if any(not reason.strip() for reason in coverage["omission_reasons"]):
        raise StockAnalysisValidationError(
            "management omission reasons cannot be empty"
        )

    for row in management["ledger"]:
        if not row["claim"].strip():
            raise StockAnalysisValidationError(
                f"management ledger claim {row['claim_id']} cannot be empty"
            )
        if not re.fullmatch(r"\d{4}-Q[1-4]", row["quarter"]):
            raise StockAnalysisValidationError(
                f"invalid management ledger quarter: {row['quarter']!r}"
            )
        row_id = row["claim_id"]
        if not _SPECIALIST_CLAIM_ID.fullmatch(row_id):
            raise StockAnalysisValidationError(
                f"specialist claim ID must be a code identifier: {row_id!r}"
            )
        if row_id in claim_ids:
            raise StockAnalysisValidationError(
                f"duplicate specialist claim ID: {row_id}"
            )
        claim_ids.append(row_id)
        for source_ids in (row["claim_source_ids"], row["outcome_source_ids"]):
            if len(source_ids) != len(set(source_ids)):
                raise StockAnalysisValidationError(
                    f"management ledger claim contains duplicate source IDs: {row_id}"
                )
        union = list(dict.fromkeys(row["claim_source_ids"] + row["outcome_source_ids"]))
        if row["source_ids"] != union:
            raise StockAnalysisValidationError(
                f"management ledger source_ids must be the claim/outcome union: {row_id}"
            )
        if row["result"] not in {"unverifiable", "too_vague_to_test"} and not union:
            raise StockAnalysisValidationError(
                f"management ledger claim {row_id} requires source IDs"
            )
        if row["result"] in {
            "kept", "delayed", "missed", "external_shock"
        } and (not row["claim_source_ids"] or not row["outcome_source_ids"]):
            raise StockAnalysisValidationError(
                f"assessed management ledger claim {row_id} requires claim and outcome source IDs"
            )
        if row["result"] in assessed_results and (
            not row["observed_outcome"] or not row["observed_outcome"].strip()
        ):
            raise StockAnalysisValidationError(
                f"assessed management ledger claim {row_id} requires observed_outcome"
            )
        if row["result"] in pending_results and row["observed_outcome"] is not None:
            raise StockAnalysisValidationError(
                f"non-assessable management ledger claim {row_id} cannot retain observed_outcome"
            )
        if row["result"] in pending_results and row["outcome_source_ids"]:
            raise StockAnalysisValidationError(
                f"non-assessable management ledger claim {row_id} cannot retain outcome_source_ids"
            )


def _parse_contract(raw_response: str, contract: dict, label: str) -> dict:
    try:
        payload = json.loads(raw_response, object_pairs_hook=_object_without_duplicates)
        _normalize_thesis_card_fields(payload)
        _normalize_management_ledger_contract(payload)
        _normalize_ownership_claim_contract(payload, contract)
        _reject_v3_legacy_ownership_claims(payload, contract)
        _validate_value(payload, contract, "result")
        _validate_ownership_claim_identifiers(payload)
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
_SPECIALIST_CLAIM_ID = re.compile(r"^[a-z][a-z0-9_.:-]*$")


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
        for field_name in (
            "fact_code",
            "unresolved_claim_code",
            "observable_metric_code",
            "threshold_code",
        ):
            code = value.get(field_name)
            if code is not None and not _STRUCTURED_CLAIM_ID.fullmatch(code):
                raise StockAnalysisValidationError(
                    f"structured {field_name} must be a code identifier"
                )
        for reference in value.get("expectation_refs", []):
            if not re.fullmatch(r"^[a-z][a-z0-9_.:-]*$", reference):
                raise StockAnalysisValidationError(
                    "structured expectation references must be code identifiers"
                )
            if not reference.startswith("valuation:reverse_dcf:"):
                raise StockAnalysisValidationError(
                    "structured expectation references must use the valuation:reverse_dcf namespace"
                )
        for child in value.values():
            _validate_structured_claim_identifiers(child)
    elif isinstance(value, list):
        for child in value:
            _validate_structured_claim_identifiers(child)


def _validate_ownership_claim_identifiers(payload: dict) -> None:
    cards = [payload]
    thesis = payload.get("thesis") if isinstance(payload, dict) else None
    if isinstance(thesis, dict):
        cards.append(thesis)
    for card in cards:
        if card.get("thesis_card_version") != (
            "individual-thesis-card-v3-structured-conclusions"
        ):
            continue
        for claim in card.get("ownership_claims") or []:
            for limitation_code in claim.get("limitation_codes", []):
                if not _STRUCTURED_CLAIM_ID.fullmatch(limitation_code):
                    raise StockAnalysisValidationError(
                        "ownership limitation codes must be code identifiers"
                    )


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


def _typed_fact(value: dict):
    from kncompanyscraper.analysis.agent.conclusion_contract import TypedFact
    return TypedFact(
        claim_id=value["claim_id"], fact_code=value["fact_code"],
        domain=value["domain"], predicate=value["predicate"], value=value["value"],
        source_ids=tuple(value["source_ids"]),
        limitation_codes=tuple(value["limitation_codes"]),
    )


def _typed_trigger(value: dict):
    from kncompanyscraper.analysis.agent.conclusion_contract import TypedTrigger
    return TypedTrigger(
        claim_id=value["claim_id"], trigger_type=value["trigger_type"],
        unresolved_claim_code=value["unresolved_claim_code"],
        observable_metric_code=value["observable_metric_code"],
        threshold_code=value["threshold_code"],
        evidence_window=value["evidence_window"],
        single_observation_sufficient=value["single_observation_sufficient"],
        observation_requirement=value["observation_requirement"],
        source_ids=tuple(value["source_ids"]),
        limitation_codes=tuple(value["limitation_codes"]),
    )


def _structured_conclusions_from_payload(value: dict) -> StructuredConclusions:
    from kncompanyscraper.analysis.agent.conclusion_contract import (
        FalsifiableCaseComponent,
        HeadlineCase,
        TypedBreakTest,
        TypedDecisiveEvidence,
        TypedMissingInformation,
        TypedReconsiderationTrigger,
        TypedTriggerEvidence,
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
        management_claims=tuple(_typed_fact(item) for item in value["management_claims"]),
        management_ledger=tuple(_typed_fact(item) for item in value["management_ledger"]),
        company_facts=tuple(_typed_fact(item) for item in value["company_facts"]),
        insider_claims=tuple(_typed_claim(item) for item in value["insider_claims"]),
        business_model_facts=tuple(_typed_claim(item) for item in value["business_model_facts"]),
        margin_facts=tuple(_typed_claim(item) for item in value["margin_facts"]),
        timing_facts=tuple(_typed_claim(item) for item in value["timing_facts"]),
        strongest_confirming_evidence=(
            TypedDecisiveEvidence(
                claim=_typed_claim(value["strongest_confirming_evidence"]["claim"]),
                relevance_code=value["strongest_confirming_evidence"]["relevance_code"],
            )
            if value["strongest_confirming_evidence"] is not None
            else None
        ),
        strongest_disconfirming_evidence=(
            TypedDecisiveEvidence(
                claim=_typed_claim(value["strongest_disconfirming_evidence"]["claim"]),
                relevance_code=value["strongest_disconfirming_evidence"]["relevance_code"],
            )
            if value["strongest_disconfirming_evidence"] is not None
            else None
        ),
        thesis_break_tests=tuple(
            TypedBreakTest(
                break_type=item["break_type"],
                condition_code=item["condition_code"],
                observable_metric_code=item["observable_metric_code"],
                threshold_code=item["threshold_code"],
                response=item["response"],
                source_ids=tuple(item["source_ids"]),
                limitation_codes=tuple(item["limitation_codes"]),
            )
            for item in value["thesis_break_tests"]
        ),
        missing_information_details=tuple(
            TypedMissingInformation(
                item_code=item["item_code"],
                limitation_class=item["limitation_class"],
                impact_code=item["impact_code"],
            )
            for item in value["missing_information_details"]
        ),
        reconsideration_trigger=(
            TypedReconsiderationTrigger(
                trigger_code=value["reconsideration_trigger"]["trigger_code"],
                source_ids=tuple(value["reconsideration_trigger"]["source_ids"]),
                limitation_codes=tuple(
                    value["reconsideration_trigger"]["limitation_codes"]
                ),
            )
            if value["reconsideration_trigger"] is not None
            else None
        ),
        trigger_evidence=tuple(
            TypedTriggerEvidence(
                claim=_typed_claim(item["claim"]),
                status=item["status"],
                rationale_code=item["rationale_code"],
            )
            for item in value["trigger_evidence"]
        ),
        limitation_codes=tuple(value["limitation_codes"]),
        trigger=_typed_trigger(value["trigger"]) if value["trigger"] is not None else None,
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
    coverage = payload.get("management_credibility_coverage")
    if isinstance(coverage, dict):
        coverage.setdefault("coverage_tier", "no_ledger")
        coverage.setdefault(
            "coverage_state", "insufficient_for_pattern_recognition"
        )
        coverage.setdefault("quarters_covered", 0)
        coverage.setdefault("data_source_type", "none")
        coverage.setdefault("confidence_cap", "low")
    if "management_credibility_coverage" not in payload:
        assessed = sum(
            assessment.get("result") in {
                "kept", "delayed", "missed", "changed", "external_shock"
            }
            for assessment in ledger
            if isinstance(assessment, dict)
        )
        pending = sum(
            assessment.get("result") in {"unverifiable", "too_vague_to_test"}
            for assessment in ledger
            if isinstance(assessment, dict)
        )
        payload["management_credibility_coverage"] = {
            "coverage_tier": "no_ledger",
            "coverage_state": "insufficient_for_pattern_recognition",
            "quarters_covered": 0,
            "data_source_type": "none",
            "eligible_claim_count": assessed + pending,
            "assessed_claim_count": assessed,
            "pending_claim_count": pending,
            "omitted_claim_count": 0,
            "omission_reasons": [],
            "confidence_cap": "low",
        }


def _normalize_ownership_claim_contract(payload: dict, contract: dict) -> None:
    thesis = payload.get("thesis")
    thesis_contract = contract.get("thesis")
    if isinstance(thesis, dict) and isinstance(thesis_contract, dict):
        if "ownership_claims" in thesis_contract:
            thesis.setdefault("ownership_claims", [])
    elif "ownership_claims" in contract:
        payload.setdefault("ownership_claims", [])


def _reject_v3_legacy_ownership_claims(payload: dict, contract: dict) -> None:
    cards = []
    if contract.get("thesis_card_version") == "individual-thesis-card-v3-structured-conclusions":
        cards.append(payload)
    thesis = payload.get("thesis")
    if (
        isinstance(thesis, dict)
        and thesis.get("thesis_card_version")
        == "individual-thesis-card-v3-structured-conclusions"
    ):
        cards.append(thesis)
    for card in cards:
        for claim in card.get("ownership_claims") or []:
            if isinstance(claim, dict) and "statement" in claim:
                statement = claim.get("statement", "")
                raise StockAnalysisValidationError(
                    f'ownership claim offending statement {statement!r} requires an approved '
                    "ownership/liquidity source; changing a documentary citation into an "
                    "ownership citation is not permitted; omit the claim."
                )


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
    if option == "array":
        return isinstance(value, list)
    if option == "object":
        return isinstance(value, dict)
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
