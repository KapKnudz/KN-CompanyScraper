"""Closed, code-owned bindings for deterministic ownership conclusions.

The model can select a measure, but it cannot select where that measure is
rendered or broaden the source scope.  This registry is deliberately small and
is generated from the ownership/liquidity packet contract.
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class TypedClaim:
    claim_id: str
    domain: str
    predicate: str
    value: int | float | str | bool | None
    source_ids: tuple[str, ...]
    limitation_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class TypedFact:
    claim_id: str
    fact_code: str
    domain: str
    predicate: str
    value: int | float | str | bool | None
    source_ids: tuple[str, ...]
    limitation_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class TypedTrigger:
    claim_id: str
    trigger_type: str
    unresolved_claim_code: str
    observable_metric_code: str
    threshold_code: str
    evidence_window: str
    single_observation_sufficient: bool
    observation_requirement: str
    source_ids: tuple[str, ...]
    limitation_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class TypedDecisiveEvidence:
    claim: TypedClaim
    relevance_code: str


@dataclass(frozen=True)
class TypedBreakTest:
    break_type: str
    condition_code: str
    observable_metric_code: str
    threshold_code: str
    response: str
    source_ids: tuple[str, ...]
    limitation_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class TypedMissingInformation:
    item_code: str
    limitation_class: str
    impact_code: str


@dataclass(frozen=True)
class TypedTriggerEvidence:
    claim: TypedClaim
    status: str
    rationale_code: str


@dataclass(frozen=True)
class TypedReconsiderationTrigger:
    trigger_code: str
    source_ids: tuple[str, ...]
    limitation_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class FalsifiableCaseComponent:
    case_ref: str
    horizon_months: int
    baseline_refs: tuple[str, ...]
    falsification: TypedClaim


@dataclass(frozen=True)
class HeadlineCase:
    case_ref: str
    horizon_months: int
    revenue_mechanism: str
    profitability_state: str
    expectation_refs: tuple[str, ...]
    break_condition: TypedClaim


@dataclass(frozen=True)
class StructuredConclusions:
    headline_case: HeadlineCase
    falsifiable_case: FalsifiableCaseComponent
    evidence_claims: tuple[TypedClaim, ...]
    break_tests: tuple[TypedClaim, ...]
    management_claims: tuple[TypedFact, ...]
    management_ledger: tuple[TypedFact, ...]
    company_facts: tuple[TypedFact, ...]
    insider_claims: tuple[TypedClaim, ...]
    business_model_facts: tuple[TypedClaim, ...]
    margin_facts: tuple[TypedClaim, ...]
    timing_facts: tuple[TypedClaim, ...]
    strongest_confirming_evidence: TypedDecisiveEvidence | None
    strongest_disconfirming_evidence: TypedDecisiveEvidence | None
    thesis_break_tests: tuple[TypedBreakTest, ...]
    missing_information_details: tuple[TypedMissingInformation, ...]
    reconsideration_trigger: TypedReconsiderationTrigger | None
    trigger_evidence: tuple[TypedTriggerEvidence, ...]
    limitation_codes: tuple[str, ...]
    trigger: TypedTrigger | None
    revenue_resilience: TypedClaim
    reverse_dcf_assessment: str


@dataclass(frozen=True)
class OwnershipField:
    claim_kind: str
    subject_role: str
    measure: str
    deterministic_field: str
    asserted_unit: str
    renderer_key: str = "ownership_and_flow_assessment"


_FIELDS = (
    OwnershipField("listing", "company", "market_id", "research_evidence.ownership_liquidity.listing.market_id", "identifier"),
    OwnershipField("listing", "company", "venue", "research_evidence.ownership_liquidity.listing.venue", "identifier"),
    OwnershipField("listing", "company", "listing_date", "research_evidence.ownership_liquidity.listing.listing_date", "date"),
    *(OwnershipField("liquidity", "market", measure, f"research_evidence.ownership_liquidity.liquidity.{measure}", unit)
      for measure, unit in (("adtv_20", "currency"), ("adtv_60", "currency"), ("adtv_120", "currency"),
                            ("observed_days_20", "days"), ("observed_days_60", "days"),
                            ("observed_days_120", "days"), ("zero_volume_days_120", "days"))),
    *(OwnershipField("buyback", "company", measure, f"research_evidence.ownership_liquidity.flow_signals.buybacks.{measure}", unit)
      for measure, unit in (("latest_event_date", "date"), ("trailing_3_month_change_shares_raw", "shares"),
                            ("trailing_12_month_change_shares_raw", "shares"), ("latest_treasury_shares", "shares"),
                            ("latest_treasury_shares_pct_raw", "raw"))),
    *(OwnershipField("short_interest", "short_position", measure, f"research_evidence.ownership_liquidity.flow_signals.shorts.{measure}", unit)
      for measure, unit in (("observation_date", "date"), ("snapshot_age_days", "days"), ("short_pct_raw", "raw"),
                            ("reported_holder_count_raw", "raw"), ("average_short_pct_raw", "raw"),
                            ("short_value_millions_raw", "raw"))),
    *(OwnershipField("long_holder_ownership", "long_holder", measure, f"research_evidence.ownership_liquidity.ownership.{measure}", unit)
      for measure, unit in (("free_float_pct", "percent"), ("free_float_shares", "shares"),
                            ("free_float_market_cap", "currency"), ("institutional_pct", "percent"),
                            ("top_1_capital_pct", "percent"), ("top_3_capital_pct", "percent"),
                            ("top_10_capital_pct", "percent"), ("top_1_voting_pct", "percent"),
                            ("index_eligibility", "status"))),
)

OWNERSHIP_FIELD_REGISTRY = MappingProxyType({field.measure: field for field in _FIELDS})
OWNERSHIP_MEASURES = tuple(OWNERSHIP_FIELD_REGISTRY)
NO_OWNERSHIP_LIQUIDITY_ASSESSMENT = (
    "Ownership and liquidity evidence are unavailable. "
    "No inference can be made from their absence."
)

STRUCTURED_CASE_REFS = (
    "fundamental_case",
    "revenue_growth_case",
    "margin_expansion_case",
    "unassessable_case",
)

V3_PROJECTION_FIELDS = (
    "one_sentence_thesis",
    "falsifiable_case",
    "business_model_profile",
    "margin_expansion_case",
    "timing_assessment",
    "confidence_limitations",
    "company_fact_ledger",
    "reconsideration_trigger",
    "activation_trigger",
    "latent_case_type",
    "activation_trigger_spec",
    "activation_trigger_evidence",
    "reverse_dcf_expectation_rationale",
    "revenue_resilience",
    "peak_margin_evidence",
    "management_assessment",
    "management_claims",
    "management_credibility_ledger",
    "management_credibility_coverage",
    "ownership_and_flow_assessment",
    "insider_assessment",
    "insider_claims",
    "confirming_evidence",
    "disconfirming_evidence",
    "thesis_break_conditions",
    "strongest_confirming_evidence",
    "strongest_disconfirming_evidence",
    "thesis_break_tests",
    "missing_information",
    "missing_information_details",
    "citations",
)


def ownership_field(measure: str) -> OwnershipField:
    try:
        return OWNERSHIP_FIELD_REGISTRY[measure]
    except KeyError as exc:
        raise ValueError(f"unknown ownership measure: {measure}") from exc


def ownership_source_ids_for_measure(packet: dict, measure: str) -> tuple[str, ...]:
    """Return the packet-generated exact source set; never infer by prefix."""
    source_map = packet.get("source_ids_by_measure") or {}
    source_ids = source_map.get(measure, ())
    return tuple(source_ids) if isinstance(source_ids, (list, tuple)) else ()


def packet_value(packet: dict, field: OwnershipField) -> Any:
    value: Any = packet
    for part in field.deterministic_field.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def render_structured_headline(conclusions: dict) -> str:
    headline = conclusions["headline_case"]
    case_label = {
        "fundamental_case": "Fundamental case",
        "revenue_growth_case": "Revenue-growth case",
        "margin_expansion_case": "Margin-expansion case",
        "unassessable_case": "Unassessable case",
    }[headline["case_ref"]]
    expectation_refs = ", ".join(
        reference for reference in headline["expectation_refs"]
    ) or "none"
    return (
        f"{case_label} over {headline['horizon_months']} months; "
        f"mechanism={headline['revenue_mechanism']}; "
        f"profitability={headline['profitability_state']}; "
        f"expectations={expectation_refs}; "
        f"break={_claim_text(headline['break_condition'])}."
    )


def _management_ledger_result(value: object) -> str:
    return {
        "confirmed": "kept",
        "positive": "kept",
        "improving": "kept",
        "observed": "kept",
        "supported": "kept",
        "unchanged": "kept",
        "negative": "missed",
        "deteriorating": "changed",
    }.get(value, "unverifiable")


def project_structured_conclusions(
    conclusions: dict, ownership_claims: list[dict] | None = None
) -> dict:
    headline = conclusions["headline_case"]
    falsifiable = conclusions["falsifiable_case"]
    management_claims = [
        _project_claim(claim, "management_claim")
        for claim in conclusions["management_claims"]
    ]
    management_ledger = [
        {
            "date": "",
            "claim": _claim_text(claim),
            "expected_timing": None,
            "observed_outcome": (
                _claim_text(claim)
                if _management_ledger_result(claim["value"]) != "unverifiable"
                else None
            ),
            "result": _management_ledger_result(claim["value"]),
            "source_ids": list(claim["source_ids"]),
            "claim_source_ids": list(claim["source_ids"]),
            "outcome_source_ids": (
                list(claim["source_ids"])
                if _management_ledger_result(claim["value"]) != "unverifiable"
                else []
            ),
        }
        for claim in conclusions["management_ledger"]
    ]
    insider_claims = [
        _project_claim(claim, "fact")
        for claim in conclusions["insider_claims"]
    ]
    company_fact_ledger = {
        "business_model": _project_facts(conclusions["business_model_facts"]),
        "revenue_drivers": _project_facts(conclusions["timing_facts"]),
        "margins_and_operating_leverage": _project_facts(
            conclusions["margin_facts"]
        ),
        "balance_sheet_and_capital_allocation": _project_facts(
            conclusions["company_facts"]
        ),
        "management_and_execution": [],
        "ownership_and_insiders": [],
        "valuation_expectations": [],
        "risks_and_disconfirming_evidence": [],
    }
    strongest_confirming_evidence = _project_decisive_evidence(
        conclusions.get("strongest_confirming_evidence"), "confirming"
    )
    strongest_disconfirming_evidence = _project_decisive_evidence(
        conclusions.get("strongest_disconfirming_evidence"), "disconfirming"
    )
    thesis_break_tests = [
        _project_break_test(test) for test in conclusions["thesis_break_tests"]
    ]
    missing_information_details = [
        _project_missing_information(detail)
        for detail in conclusions["missing_information_details"]
    ]
    reconsideration_trigger = _project_reconsideration_trigger(
        conclusions.get("reconsideration_trigger")
    )
    trigger_evidence = [
        _project_trigger_evidence(entry)
        for entry in conclusions["trigger_evidence"]
    ]
    business_model_summary, business_model_source_ids, business_model_limitations = (
        _project_claim_bundle(conclusions["business_model_facts"])
    )
    margin_summary, margin_source_ids, margin_limitations = _project_claim_bundle(
        conclusions["margin_facts"]
    )
    timing_summary, timing_source_ids, timing_limitations = _project_claim_bundle(
        conclusions["timing_facts"]
    )
    resilience = conclusions["revenue_resilience"]
    trigger = conclusions.get("trigger")
    trigger_projection = _project_trigger(trigger) if trigger is not None else {
        "activation_trigger": None,
        "latent_case_type": None,
        "activation_trigger_spec": None,
    }
    return {
        "one_sentence_thesis": render_structured_headline(conclusions),
        "case_horizon_months": headline["horizon_months"],
        "reverse_dcf_expectation_assessment": conclusions["reverse_dcf_assessment"],
        "falsifiable_case": {
            "statement": render_structured_headline(conclusions),
            "falsification_test": (
                "Typed falsification condition: "
                + _claim_text(falsifiable["falsification"])
            ),
            "horizon_months": falsifiable["horizon_months"],
            "source_ids": falsifiable["baseline_refs"]
            or falsifiable["falsification"].get("source_ids", []),
        },
        "business_model_profile": {
            "summary": business_model_summary,
            "customer_and_need": "",
            "offering": "",
            "revenue_mechanics": business_model_summary,
            "sales_and_distribution": "",
            "cost_structure": "",
            "reinvestment_requirements": "",
            "competitive_position": "",
            "key_dependencies": "",
            "revenue_model_types": [],
            "customer_types": [],
            "recurring_revenue_profile": "unassessable",
            "pricing_power": "unassessable",
            "capital_intensity": "unassessable",
            "operating_leverage": "unassessable",
            "circle_of_competence": "unassessable",
            "source_ids": business_model_source_ids,
            "limitations": business_model_limitations,
        },
        "margin_expansion_case": {
            "status": "early_evidence" if margin_summary else "unassessable",
            "mechanism": margin_summary,
            "required_operating_changes": [],
            "source_ids": margin_source_ids,
            "contrary_source_ids": [],
            "limitations": margin_limitations,
        },
        "timing_assessment": {
            "horizon_months": headline["horizon_months"],
            "why_now": timing_summary,
            "confidence": "medium" if timing_summary else "low",
            "catalysts": [],
            "source_ids": timing_source_ids,
            "limitations": timing_limitations,
        },
        "confidence_limitations": list(conclusions["limitation_codes"]),
        "company_fact_ledger": company_fact_ledger,
        "reconsideration_trigger": reconsideration_trigger,
        **trigger_projection,
        "activation_trigger_evidence": trigger_evidence,
        "reverse_dcf_expectation_rationale": (
            "Typed reverse-DCF assessment: "
            + conclusions["reverse_dcf_assessment"]
        ),
        "revenue_resilience": {
            "assessment": resilience["value"],
            "recurring_driver": "",
            "variable_driver": "",
            "cash_flow_observation": "",
            "source_ids": list(resilience["source_ids"]),
            "recurring_source_ids": [],
            "variable_source_ids": [],
            "limitations": list(
                dict.fromkeys(
                    [
                        *conclusions["limitation_codes"],
                        *resilience["limitation_codes"],
                    ]
                )
            ),
        },
        "peak_margin_evidence": [],
        "management_assessment": (
            management_claims[0]["statement"] if management_claims else ""
        ),
        "management_claims": management_claims,
        "management_credibility_ledger": management_ledger,
        "management_credibility_coverage": {
            "eligible_claim_count": len(management_ledger),
            "assessed_claim_count": 0,
            "pending_claim_count": len(management_ledger),
            "omitted_claim_count": 0,
            "omission_reasons": [],
        },
        "ownership_and_flow_assessment": render_ownership_claims(
            ownership_claims or []
        ),
        "insider_assessment": (
            insider_claims[0]["statement"] if insider_claims else ""
        ),
        "insider_claims": insider_claims,
        "confirming_evidence": [
            _claim_text(claim) for claim in conclusions["evidence_claims"]
        ],
        "disconfirming_evidence": [
            _claim_text(claim) for claim in conclusions["break_tests"]
        ],
        "thesis_break_conditions": [
            _claim_text(claim) for claim in conclusions["break_tests"]
        ],
        "strongest_confirming_evidence": strongest_confirming_evidence,
        "strongest_disconfirming_evidence": strongest_disconfirming_evidence,
        "thesis_break_tests": thesis_break_tests,
        "missing_information": [
            detail["item"] for detail in missing_information_details
        ],
        "missing_information_details": missing_information_details,
        "citations": [],
    }


def _claim_text(claim: dict) -> str:
    value = "unavailable" if claim["value"] is None else claim["value"]
    subject = claim.get("fact_code", claim["predicate"]).replace("_", " ")
    return f"{claim['domain']} {subject}: {value}"


def _project_trigger(trigger: dict) -> dict:
    unresolved_claim = _code_text(trigger["unresolved_claim_code"])
    observable_metric = _code_text(trigger["observable_metric_code"])
    threshold = _code_text(trigger["threshold_code"])
    evidence_window = {
        "0_12m": "0-12 months",
        "12_24m": "12-24 months",
        "24_48m": "24-48 months",
        "uncertain": "uncertain",
    }[trigger["evidence_window"]]
    observation_requirement = {
        "single_observation": "single observation",
        "repeated_observations": "repeated observations",
    }[trigger["observation_requirement"]]
    return {
        "activation_trigger": (
            f"Resolve {unresolved_claim} when {observable_metric} {threshold}."
        ),
        "latent_case_type": trigger["trigger_type"],
        "activation_trigger_spec": {
            "unresolved_claim": unresolved_claim,
            "observable_metric_or_event": observable_metric,
            "threshold_or_direction": threshold,
            "evidence_window": evidence_window,
            "single_observation_sufficient": trigger[
                "single_observation_sufficient"
            ],
            "observation_requirement": observation_requirement,
        },
    }


def _code_text(value: str) -> str:
    return value.replace("_", " ").replace("-", " ")


def _project_decisive_evidence(evidence: dict | None, side: str) -> dict | None:
    if evidence is None:
        return None
    relevance = {
        "baseline_support": "It establishes the current baseline for the case.",
        "mechanism_support": "It supports the stated business mechanism.",
        "downside_exposure": "It identifies a decision-relevant downside exposure.",
        "thesis_break_signal": "It is a decision-relevant signal against the thesis.",
        "evidence_quality": "It is decision-relevant because it improves evidence quality.",
    }[evidence["relevance_code"]]
    claim = evidence["claim"]
    return {
        "statement": _claim_text(claim),
        "why_it_matters": relevance,
        "source_ids": list(claim["source_ids"]),
    }


def _project_break_test(test: dict) -> dict:
    return {
        "break_type": test["break_type"],
        "condition": _code_text(test["condition_code"]),
        "observable_metric_or_event": _code_text(test["observable_metric_code"]),
        "threshold_or_direction": _code_text(test["threshold_code"]),
        "response": test["response"],
        "source_ids": list(test["source_ids"]),
    }


def _project_missing_information(detail: dict) -> dict:
    item = _code_text(detail["item_code"])
    impact = {
        "conclusion_limited": "This missing input can affect the fundamental company conclusion.",
        "context_limited": "This missing input limits context but does not by itself establish a broken fundamental case.",
    }[detail["impact_code"]]
    return {
        "item": item,
        "limitation_class": detail["limitation_class"],
        "impact": impact,
    }


def _project_reconsideration_trigger(trigger: dict | None) -> str | None:
    if trigger is None:
        return None
    return _code_text(trigger["trigger_code"])


def _project_trigger_evidence(entry: dict) -> dict:
    rationale = {
        "metric_met": "The observation meets the named trigger condition.",
        "metric_missed": "The observation does not meet the named trigger condition.",
        "inconclusive": "The observation is relevant but does not resolve the trigger.",
        "persistence_unresolved": "The observation leaves the stated persistence risk unresolved.",
    }[entry["rationale_code"]]
    claim = entry["claim"]
    return {
        "evidence_item": _claim_text(claim),
        "status": entry["status"],
        "rationale": rationale,
        "source_ids": list(claim["source_ids"]),
    }


def _project_claim(claim: dict, evidence_kind: str) -> dict:
    return {
        "statement": _claim_text(claim),
        "evidence_kind": evidence_kind,
        "source_ids": list(claim["source_ids"]),
        "limitations": list(claim["limitation_codes"]),
    }


def _project_facts(claims: list[dict]) -> list[dict]:
    return [
        {
            "statement": _claim_text(claim),
            "evidence_kind": "fact",
            "source_ids": list(claim["source_ids"]),
            "source_date": None,
            "reporting_period": None,
        }
        for claim in claims
    ]


def _project_claim_bundle(claims: list[dict]) -> tuple[str, list[str], list[str]]:
    statements = [_claim_text(claim) for claim in claims]
    source_ids = list(dict.fromkeys(
        source_id for claim in claims for source_id in claim["source_ids"]
    ))
    limitations = list(dict.fromkeys(
        code for claim in claims for code in claim["limitation_codes"]
    ))
    return "; ".join(statements), source_ids, limitations


def render_ownership_claims(claims: list[dict]) -> str:
    """Render only validated typed claims into the fixed ownership destination."""
    if not claims or any("measure" not in claim for claim in claims):
        return NO_OWNERSHIP_LIQUIDITY_ASSESSMENT
    rendered = []
    for claim in claims:
        field = ownership_field(claim["measure"])
        value = claim["binding"]["asserted_value"]
        rendered.append(f"{field.measure.replace('_', ' ')}: {value}")
    return "Ownership and liquidity evidence: " + "; ".join(rendered) + "."
