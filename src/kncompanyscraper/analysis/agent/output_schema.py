from dataclasses import asdict, dataclass, field
from typing import Literal

from kncompanyscraper.analysis.valuation.forward_scenario import (
    ForwardScenarioAnalysis,
    ScenarioBundle,
)
from kncompanyscraper.analysis.agent.conclusion_contract import (
    OWNERSHIP_MEASURES,
    OWNERSHIP_FIELD_REGISTRY,
    STRUCTURED_CASE_REFS,
    V3_PROJECTION_FIELDS,
    StructuredConclusions,
)


AnalysisVerdict = Literal["reject", "watch", "latent_case", "activated_case"]
AnalysisStatus = Literal["complete"]
Confidence = Literal["low", "medium", "high"]
FactEvidenceKind = Literal["fact", "management_claim", "analyst_inference"]
PortfolioEligibility = Literal["investable", "not_investable"]
PortfolioReasonCode = Literal[
    "investable",
    "valuation_only",
    "business_quality",
    "evidence_insufficient",
    "thesis_not_activated",
    "liquidity",
    "balance_sheet",
    "other",
]
ClaimResult = Literal["kept", "delayed", "missed", "changed", "unverifiable"]
RevenueResilienceAssessment = Literal[
    "resilient",
    "mixed",
    "variable",
    "unassessable",
]
ReverseDcfExpectationAssessment = Literal[
    "plausible",
    "demanding",
    "unsupported",
    "unassessable",
]
LimitationClass = Literal["core", "supplemental"]
ThesisBreakType = Literal[
    "revenue_or_demand",
    "margin_or_execution",
    "balance_sheet_or_dilution",
    "management_credibility",
    "valuation_overshoot",
    "superior_evidence_or_opportunity",
]
ThesisBreakResponse = Literal["reassess", "reduce", "sell"]
LatentCaseType = Literal["price", "operating"]
ActivationTriggerEvidenceStatus = Literal[
    "confirms",
    "weakens",
    "unresolved",
]
ThesisUpdateImpact = Literal[
    "no_material_change",
    "thesis_strengthened",
    "thesis_weakened",
    "activation_trigger_reached",
    "thesis_break_triggered",
    "full_reassessment_required",
]
RevenueModelType = Literal[
    "subscription",
    "transaction",
    "usage",
    "product_sales",
    "service",
    "project",
    "licensing",
    "advertising",
    "interest_spread",
    "rental",
    "hybrid",
    "unclassified",
]


@dataclass
class ManagementClaimAssessment:
    date: str
    claim: str
    expected_timing: str | None
    observed_outcome: str | None
    result: ClaimResult
    source_ids: list[str] = field(default_factory=list)
    claim_source_ids: list[str] = field(default_factory=list)
    outcome_source_ids: list[str] = field(default_factory=list)


@dataclass
class ManagementCredibilityCoverage:
    eligible_claim_count: int = 0
    assessed_claim_count: int = 0
    pending_claim_count: int = 0
    omitted_claim_count: int = 0
    omission_reasons: list[str] = field(default_factory=list)


@dataclass
class AssessmentClaim:
    statement: str
    evidence_kind: FactEvidenceKind
    source_ids: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass
class OwnershipBinding:
    source_ids: list[str]
    deterministic_field: str
    asserted_value: int | float | str | bool | None
    asserted_unit: str


@dataclass
class OwnershipClaim:
    claim_kind: str
    subject_role: str
    measure: str
    binding: OwnershipBinding
    limitation_codes: list[str] = field(default_factory=list)


@dataclass
class EvidenceCitation:
    source_id: str
    claim: str


@dataclass
class FalsifiableCase:
    statement: str = ""
    falsification_test: str = ""
    horizon_months: int | None = None
    source_ids: list[str] = field(default_factory=list)


@dataclass
class DecisiveEvidence:
    statement: str
    why_it_matters: str
    source_ids: list[str] = field(default_factory=list)


@dataclass
class ThesisBreakTest:
    break_type: ThesisBreakType
    condition: str
    observable_metric_or_event: str
    threshold_or_direction: str
    response: ThesisBreakResponse
    source_ids: list[str] = field(default_factory=list)


@dataclass
class CompanyFact:
    statement: str
    evidence_kind: FactEvidenceKind
    source_ids: list[str] = field(default_factory=list)
    source_date: str | None = None
    reporting_period: str | None = None


@dataclass
class CompanyFactLedger:
    business_model: list[CompanyFact] = field(default_factory=list)
    revenue_drivers: list[CompanyFact] = field(default_factory=list)
    margins_and_operating_leverage: list[CompanyFact] = field(default_factory=list)
    balance_sheet_and_capital_allocation: list[CompanyFact] = field(default_factory=list)
    management_and_execution: list[CompanyFact] = field(default_factory=list)
    ownership_and_insiders: list[CompanyFact] = field(default_factory=list)
    valuation_expectations: list[CompanyFact] = field(default_factory=list)
    risks_and_disconfirming_evidence: list[CompanyFact] = field(default_factory=list)


@dataclass
class BusinessModelProfile:
    summary: str = ""
    customer_and_need: str = ""
    offering: str = ""
    revenue_mechanics: str = ""
    sales_and_distribution: str = ""
    cost_structure: str = ""
    reinvestment_requirements: str = ""
    competitive_position: str = ""
    key_dependencies: str = ""
    revenue_model_types: list[RevenueModelType] = field(default_factory=list)
    customer_types: list[str] = field(default_factory=list)
    recurring_revenue_profile: str = "unassessable"
    pricing_power: str = "unassessable"
    capital_intensity: str = "unassessable"
    operating_leverage: str = "unassessable"
    circle_of_competence: str = "unassessable"
    source_ids: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass
class RevenueResilience:
    assessment: RevenueResilienceAssessment = "unassessable"
    recurring_driver: str = ""
    variable_driver: str = ""
    cash_flow_observation: str = ""
    source_ids: list[str] = field(default_factory=list)
    recurring_source_ids: list[str] = field(default_factory=list)
    variable_source_ids: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass
class MarginExpansionCase:
    status: str = "unassessable"
    mechanism: str = ""
    required_operating_changes: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    contrary_source_ids: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass
class ThesisCatalyst:
    description: str
    timing_window: str
    observable_confirmation: str
    status: str
    source_ids: list[str] = field(default_factory=list)


@dataclass
class TimingAssessment:
    horizon_months: int | None = None
    why_now: str = ""
    confidence: Confidence = "low"
    catalysts: list[ThesisCatalyst] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass
class MissingInformationItem:
    item: str
    limitation_class: LimitationClass
    impact: str


@dataclass
class ActivationTriggerSpec:
    unresolved_claim: str
    observable_metric_or_event: str
    threshold_or_direction: str
    evidence_window: str
    single_observation_sufficient: bool
    observation_requirement: str


@dataclass
class ActivationTriggerEvidence:
    evidence_item: str
    status: ActivationTriggerEvidenceStatus
    rationale: str
    source_ids: list[str] = field(default_factory=list)


@dataclass
class StockAnalysisResult:
    company_id: int
    ticker: str
    company_name: str
    verdict: AnalysisVerdict
    confidence: Confidence
    one_sentence_thesis: str
    falsifiable_case: FalsifiableCase = field(default_factory=FalsifiableCase)
    analysis_status: AnalysisStatus = "complete"
    thesis_card_version: str = "individual-thesis-card-v2"
    evidence_as_of: str | None = None
    business_model_profile: BusinessModelProfile = field(
        default_factory=BusinessModelProfile
    )
    margin_expansion_case: MarginExpansionCase = field(
        default_factory=MarginExpansionCase
    )
    timing_assessment: TimingAssessment = field(default_factory=TimingAssessment)
    confidence_limitations: list[str] = field(default_factory=list)
    company_fact_ledger: CompanyFactLedger = field(default_factory=CompanyFactLedger)
    portfolio_eligibility: PortfolioEligibility = "not_investable"
    portfolio_reason_code: PortfolioReasonCode = "evidence_insufficient"
    reconsideration_trigger: str | None = None

    case_horizon_months: int | None = None
    activation_trigger: str | None = None
    latent_case_type: LatentCaseType | None = None
    activation_trigger_spec: ActivationTriggerSpec | None = None
    activation_trigger_evidence: list[ActivationTriggerEvidence] = field(
        default_factory=list
    )
    reverse_dcf_expectation_assessment: ReverseDcfExpectationAssessment = "unassessable"
    reverse_dcf_expectation_rationale: str = ""
    revenue_resilience: RevenueResilience = field(default_factory=RevenueResilience)
    current_ebit_margin: float | None = None
    defensible_peak_ebit_margin: float | None = None
    peak_margin_evidence: list[str] = field(default_factory=list)
    scenario_bundles: list[ScenarioBundle] = field(default_factory=list)
    forward_scenario_analysis: ForwardScenarioAnalysis | None = None
    historical_forecast_table: dict | None = None
    peak_margin_bridge: dict | None = None
    scenario_driver_attribution: dict | None = None
    management_assessment: str = ""
    management_claims: list[AssessmentClaim] = field(default_factory=list)
    management_credibility_ledger: list[ManagementClaimAssessment] = field(default_factory=list)
    management_credibility_coverage: ManagementCredibilityCoverage = field(
        default_factory=ManagementCredibilityCoverage
    )
    ownership_and_flow_assessment: str = ""
    ownership_claims: list[AssessmentClaim | OwnershipClaim] = field(default_factory=list)
    insider_assessment: str = ""
    insider_claims: list[AssessmentClaim] = field(default_factory=list)
    confirming_evidence: list[str] = field(default_factory=list)
    disconfirming_evidence: list[str] = field(default_factory=list)
    thesis_break_conditions: list[str] = field(default_factory=list)
    strongest_confirming_evidence: DecisiveEvidence | None = None
    strongest_disconfirming_evidence: DecisiveEvidence | None = None
    thesis_break_tests: list[ThesisBreakTest] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    missing_information_details: list[MissingInformationItem] = field(
        default_factory=list
    )
    citations: list[EvidenceCitation] = field(default_factory=list)
    # v3 authoritative input graph. Legacy display fields are projections only.
    structured_conclusions: StructuredConclusions | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        if self.thesis_card_version == "individual-thesis-card-v3-structured-conclusions":
            for field_name in V3_PROJECTION_FIELDS:
                data.pop(field_name, None)
        return data


@dataclass
class ThesisUpdateResult:
    impact: ThesisUpdateImpact
    summary: str
    changed_sections: list[str]
    thesis: StockAnalysisResult

    def to_dict(self) -> dict:
        return asdict(self)


class _NullableObjectContract(dict):
    """Contract mapping that accepts either its object shape or null."""


def _nullable_object_contract(properties: dict) -> _NullableObjectContract:
    return _NullableObjectContract(properties)


def _scenario_bundle_contract() -> dict:
    sourced_assumption = {
        "value": "number",
        "source_ids": ["string"],
        "rationale": "string",
        "mechanism": "string | null",
    }
    net_debt_change = {
        **sourced_assumption,
        "mechanism": "string",
        "provenance_type": (
            "source_backed | analyst_sensitivity | not_applicable"
        ),
    }
    return {
        "case": "bear | base | bull",
        "horizon_months": "integer",
        "revenue_cagr": sourced_assumption,
        "ebit_margin": sourced_assumption,
        "terminal_ev_ebit_low": sourced_assumption,
        "terminal_ev_ebit_high": sourced_assumption,
        "net_debt_change": net_debt_change,
        "share_count_growth": sourced_assumption,
        "distributions_per_share": sourced_assumption,
        "mechanism": "string",
    }


STOCK_ANALYSIS_OUTPUT_CONTRACT = {
    "company_id": "integer",
    "ticker": "string",
    "company_name": "string",
    "analysis_status": "complete",
    "verdict": "reject | watch | latent_case | activated_case",
    "confidence": "low | medium | high",
    "one_sentence_thesis": "string",
    "falsifiable_case": {
        "statement": "string",
        "falsification_test": "string",
        "horizon_months": "integer | null",
        "source_ids": ["string"],
    },
    "thesis_card_version": "individual-thesis-card-v2",
    "evidence_as_of": "string | null",
    "business_model_profile": {
        "summary": "string",
        "customer_and_need": "string",
        "offering": "string",
        "revenue_mechanics": "string",
        "sales_and_distribution": "string",
        "cost_structure": "string",
        "reinvestment_requirements": "string",
        "competitive_position": "string",
        "key_dependencies": "string",
        "revenue_model_types": [
            "subscription | transaction | usage | product_sales | service | project | "
            "licensing | advertising | interest_spread | rental | hybrid | unclassified"
        ],
        "customer_types": [
            "business | consumer | government | financial_institution | mixed | unclassified"
        ],
        "recurring_revenue_profile": "none | partial | majority | unassessable",
        "pricing_power": "weak | mixed | strong | unassessable",
        "capital_intensity": "low | moderate | high | unassessable",
        "operating_leverage": "absent | limited | credible | demonstrated | unassessable",
        "circle_of_competence": "inside | borderline | outside | unassessable",
        "source_ids": ["string"],
        "limitations": ["string"],
    },
    "margin_expansion_case": {
        "status": "not_applicable | latent | early_evidence | active | stalled | invalidated | unassessable",
        "mechanism": "string",
        "required_operating_changes": ["string"],
        "source_ids": ["string"],
        "contrary_source_ids": ["string"],
        "limitations": ["string"],
    },
    "timing_assessment": {
        "horizon_months": "integer | null",
        "why_now": "string",
        "confidence": "low | medium | high",
        "catalysts": [
            {
                "description": "string",
                "timing_window": "0_12m | 12_24m | 24_48m | uncertain",
                "observable_confirmation": "string",
                "status": "expected | in_progress | achieved | delayed | unverified",
                "source_ids": ["string"],
            }
        ],
        "source_ids": ["string"],
        "limitations": ["string"],
    },
    "confidence_limitations": ["string"],
    "company_fact_ledger": {
        heading: [
            {
                "statement": "string",
                "evidence_kind": "fact | management_claim | analyst_inference",
                "source_ids": ["string"],
                "source_date": "string | null",
                "reporting_period": "string | null",
            }
        ]
        for heading in (
            "business_model",
            "revenue_drivers",
            "margins_and_operating_leverage",
            "balance_sheet_and_capital_allocation",
            "management_and_execution",
            "ownership_and_insiders",
            "valuation_expectations",
            "risks_and_disconfirming_evidence",
        )
    },
    "portfolio_eligibility": "investable | not_investable",
    "portfolio_reason_code": (
        "investable | valuation_only | business_quality | evidence_insufficient | "
        "thesis_not_activated | liquidity | balance_sheet | other"
    ),
    "reconsideration_trigger": "string | null",
    "case_horizon_months": "integer | null",
    "activation_trigger": "string | null",
    "latent_case_type": "price | operating | null",
    "activation_trigger_spec": _nullable_object_contract(
        {
            "unresolved_claim": "string",
            "observable_metric_or_event": "string",
            "threshold_or_direction": "string",
            "evidence_window": "string",
            "single_observation_sufficient": "boolean",
            "observation_requirement": "string",
        }
    ),
    "activation_trigger_evidence": [
        {
            "evidence_item": "string",
            "status": "confirms | weakens | unresolved",
            "rationale": "string",
            "source_ids": ["string"],
        }
    ],
    "reverse_dcf_expectation_assessment": (
        "plausible | demanding | unsupported | unassessable"
    ),
    "reverse_dcf_expectation_rationale": "string",
    "revenue_resilience": {
        "assessment": "resilient | mixed | variable | unassessable",
        "recurring_driver": "string",
        "variable_driver": "string",
        "cash_flow_observation": "string",
        "source_ids": ["string"],
        "recurring_source_ids": ["string"],
        "variable_source_ids": ["string"],
        "limitations": ["string"],
    },
    "current_ebit_margin": "number | null",
    "defensible_peak_ebit_margin": "number | null",
    "peak_margin_evidence": ["string"],
    "scenario_bundles": [_scenario_bundle_contract()],
    "forward_scenario_analysis": "null",
    "historical_forecast_table": "null",
    "peak_margin_bridge": "null",
    "scenario_driver_attribution": "null",
    "management_assessment": "string",
    "management_claims": [
        {
            "statement": "string",
            "evidence_kind": "fact | management_claim | analyst_inference",
            "source_ids": ["string"],
            "limitations": ["string"],
        }
    ],
    "management_credibility_ledger": [
        {
            "date": "string",
            "claim": "string",
            "expected_timing": "string | null",
            "observed_outcome": "string | null",
            "result": "kept | delayed | missed | changed | unverifiable",
            "source_ids": ["string"],
            "claim_source_ids": ["string"],
            "outcome_source_ids": ["string"],
        }
    ],
    "management_credibility_coverage": {
        "eligible_claim_count": "integer",
        "assessed_claim_count": "integer",
        "pending_claim_count": "integer",
        "omitted_claim_count": "integer",
        "omission_reasons": ["string"],
    },
    "ownership_and_flow_assessment": "string",
    "ownership_claims": [
        {
            "statement": "string",
            "evidence_kind": "fact | management_claim | analyst_inference",
            "source_ids": ["string"],
            "limitations": ["string"],
        }
    ],
    "insider_assessment": "string",
    "insider_claims": [
        {
            "statement": "string",
            "evidence_kind": "fact | management_claim | analyst_inference",
            "source_ids": ["string"],
            "limitations": ["string"],
        }
    ],
    "confirming_evidence": ["string"],
    "disconfirming_evidence": ["string"],
    "thesis_break_conditions": ["string"],
    "strongest_confirming_evidence": _nullable_object_contract(
        {
            "statement": "string",
            "why_it_matters": "string",
            "source_ids": ["string"],
        }
    ),
    "strongest_disconfirming_evidence": _nullable_object_contract(
        {
            "statement": "string",
            "why_it_matters": "string",
            "source_ids": ["string"],
        }
    ),
    "thesis_break_tests": [
        {
            "break_type": (
                "revenue_or_demand | margin_or_execution | "
                "balance_sheet_or_dilution | management_credibility | "
                "valuation_overshoot | superior_evidence_or_opportunity"
            ),
            "condition": "string",
            "observable_metric_or_event": "string",
            "threshold_or_direction": "string",
            "response": "reassess | reduce | sell",
            "source_ids": ["string"],
        }
    ],
    "missing_information": ["string"],
    "missing_information_details": [
        {
            "item": "string",
            "limitation_class": "core | supplemental",
            "impact": "string",
        }
    ],
    "citations": [
        {
            "source_id": "string",
            "claim": "string",
        }
    ],
    "structured_conclusions": "null",
}


# v3 keeps model-authored conclusions as a closed typed graph. Human-readable
# fields from the v2 contract are projections and are intentionally absent.
_TYPED_CLAIM = {
    "claim_id": "string",
    "domain": "business_model | revenue | margin | balance_sheet | management | insider | valuation | risk | timing | evidence",
    "predicate": (
        "status | observation | mechanism | threshold | baseline | outcome | "
        "assessment | source_gap | direction | event | relation"
    ),
    "value": (
        "number | boolean | null | observed | supported | unsupported | unavailable | "
        "positive | negative | mixed | confirmed | unconfirmed | unchanged | "
        "improving | deteriorating | resilient | variable | unassessable | "
        "plausible | demanding"
    ),
    "source_ids": ["string"],
    "limitation_codes": ["string"],
}
_TYPED_FACT = {
    "claim_id": "string",
    "fact_code": "string",
    "domain": "string",
    "predicate": "observation | outcome | relation | status",
    "value": (
        "number | boolean | null | observed | supported | unsupported | unavailable | "
        "positive | negative | mixed | confirmed | unconfirmed | unchanged | "
        "improving | deteriorating | resilient | variable | unassessable"
    ),
    "source_ids": ["string"],
    "limitation_codes": ["string"],
}
_CAPITAL_ALLOCATION_FACT = dict(_TYPED_FACT)
_CAPITAL_ALLOCATION_FACT["fact_code"] = (
    "cash_balance | debt_balance | working_capital | acquisition | capex | "
    "buyback | dividend | dilution | capital_allocation_policy"
)
_CAPITAL_ALLOCATION_FACT["domain"] = "balance_sheet"
_MANAGEMENT_FACT = dict(_TYPED_FACT)
_MANAGEMENT_FACT["fact_code"] = (
    "tenure | incentive_alignment | execution | governance | guidance | management_change"
)
_MANAGEMENT_FACT["domain"] = "management"
_INSIDER_CLAIM = dict(_TYPED_CLAIM)
_INSIDER_CLAIM["domain"] = "insider"
_STRUCTURED_TRIGGER = {
    "claim_id": "string",
    "trigger_type": "price | operating",
    "unresolved_claim_code": (
        "revenue_recovery | margin_recovery | cash_flow_recovery | "
        "customer_retention | balance_sheet_deleveraging | operating_execution | "
        "valuation_entry"
    ),
    "observable_metric_code": (
        "arr | mrr | revenue | sales | ebit | ebitda | gross_margin | ebit_margin | "
        "free_cash_flow | operating_cash_flow | customers | churn | retention | "
        "renewals | orders | volume | share_price | valuation | multiple | net_debt | "
        "working_capital | backlog | bookings | margin"
    ),
    "threshold_code": (
        "above_0_percent | above_5_percent | above_10_percent | above_15_percent | "
        "below_5_percent | below_10_percent | below_15_percent | reaches_entry_level | "
        "exceeds_baseline | maintains_positive | remains_positive | improves | declines"
    ),
    "evidence_window": "0_12m | 12_24m | 24_48m | uncertain",
    "single_observation_sufficient": "boolean",
    "observation_requirement": "single_observation | repeated_observations",
    "source_ids": ["string"],
    "limitation_codes": ["string"],
}
_STRUCTURED_DECISIVE_EVIDENCE = {
    "claim": _TYPED_CLAIM,
    "relevance_code": (
        "baseline_support | mechanism_support | downside_exposure | "
        "thesis_break_signal | evidence_quality"
    ),
}
_STRUCTURED_BREAK_TEST = {
    "break_type": (
        "revenue_or_demand | margin_or_execution | balance_sheet_or_dilution | "
        "management_credibility | valuation_overshoot | superior_evidence_or_opportunity"
    ),
    "condition_code": (
        "revenue_decline | demand_loss | margin_decline | execution_failure | "
        "debt_increase | dilution | management_miss | valuation_expansion | "
        "superior_evidence"
    ),
    "observable_metric_code": (
        "revenue | sales | ebit_margin | gross_margin | free_cash_flow | "
        "net_debt | share_price | valuation | multiple | customers | churn | "
        "management_guidance | new_evidence"
    ),
    "threshold_code": (
        "above_0_percent | above_5_percent | above_10_percent | above_15_percent | "
        "below_5_percent | below_10_percent | below_15_percent | reaches_entry_level | "
        "exceeds_baseline | maintains_positive | remains_positive | improves | declines"
    ),
    "response": "reassess | reduce | sell",
    "source_ids": ["string"],
    "limitation_codes": ["string"],
}
_STRUCTURED_MISSING_INFORMATION = {
    "item_code": (
        "missing_revenue_evidence | missing_cash_flow_history | "
        "missing_current_price | missing_operating_baseline | "
        "missing_management_history | missing_documentary_support | "
        "missing_ownership_data | missing_valuation_inputs"
    ),
    "limitation_class": "core | supplemental",
    "impact_code": "conclusion_limited | context_limited",
}
_STRUCTURED_RECONSIDERATION_TRIGGER = {
    "trigger_code": (
        "valuation_entry | evidence_recovery | operating_recovery | "
        "balance_sheet_recovery"
    ),
    "source_ids": ["string"],
    "limitation_codes": ["string"],
}
_STRUCTURED_TRIGGER_EVIDENCE = {
    "claim": _TYPED_CLAIM,
    "status": "confirms | weakens | unresolved",
    "rationale_code": (
        "metric_met | metric_missed | inconclusive | persistence_unresolved"
    ),
}
_STRUCTURED_CONCLUSIONS = {
    "headline_case": {
        "case_ref": " | ".join(STRUCTURED_CASE_REFS),
        "horizon_months": "integer",
        "revenue_mechanism": (
            "organic_growth | price | volume | acquisition | recurring | variable | "
            "project | transaction | unassessable"
        ),
        "profitability_state": "profitable | loss_making | recovering | unassessable",
        "expectation_refs": ["string"],
        "break_condition": _TYPED_CLAIM,
    },
    "falsifiable_case": {
        "case_ref": " | ".join(STRUCTURED_CASE_REFS),
        "horizon_months": "integer",
        "baseline_refs": ["string"],
        "falsification": _TYPED_CLAIM,
    },
    "evidence_claims": [_TYPED_CLAIM],
    "break_tests": [_TYPED_CLAIM],
    "management_claims": [_MANAGEMENT_FACT],
    "management_ledger": [_MANAGEMENT_FACT],
    "company_facts": [_CAPITAL_ALLOCATION_FACT],
    "insider_claims": [_INSIDER_CLAIM],
    "business_model_facts": [_TYPED_CLAIM],
    "margin_facts": [_TYPED_CLAIM],
    "timing_facts": [_TYPED_CLAIM],
    "strongest_confirming_evidence": _nullable_object_contract(
        _STRUCTURED_DECISIVE_EVIDENCE
    ),
    "strongest_disconfirming_evidence": _nullable_object_contract(
        _STRUCTURED_DECISIVE_EVIDENCE
    ),
    "thesis_break_tests": [_STRUCTURED_BREAK_TEST],
    "missing_information_details": [_STRUCTURED_MISSING_INFORMATION],
    "reconsideration_trigger": _nullable_object_contract(
        _STRUCTURED_RECONSIDERATION_TRIGGER
    ),
    "trigger_evidence": [_STRUCTURED_TRIGGER_EVIDENCE],
    "limitation_codes": ["string"],
    "trigger": _NullableObjectContract(_STRUCTURED_TRIGGER),
    "revenue_resilience": _TYPED_CLAIM,
    "reverse_dcf_assessment": "plausible | demanding | unsupported | unassessable",
}
V3_STOCK_ANALYSIS_OUTPUT_CONTRACT = dict(STOCK_ANALYSIS_OUTPUT_CONTRACT)
V3_STOCK_ANALYSIS_OUTPUT_CONTRACT["thesis_card_version"] = (
    "individual-thesis-card-v3-structured-conclusions"
)
for _field_name in (
    "one_sentence_thesis", "falsifiable_case", "business_model_profile",
    "margin_expansion_case", "timing_assessment", "confidence_limitations",
    "company_fact_ledger", "reconsideration_trigger", "activation_trigger",
    "latent_case_type",
    "activation_trigger_spec", "activation_trigger_evidence",
    "reverse_dcf_expectation_rationale", "revenue_resilience", "peak_margin_evidence",
    "management_assessment", "management_claims", "management_credibility_ledger",
    "management_credibility_coverage", "ownership_and_flow_assessment",
    "insider_assessment", "insider_claims", "confirming_evidence",
    "disconfirming_evidence", "thesis_break_conditions",
    "strongest_confirming_evidence", "strongest_disconfirming_evidence",
    "thesis_break_tests", "missing_information", "missing_information_details",
    "citations",
):
    V3_STOCK_ANALYSIS_OUTPUT_CONTRACT.pop(_field_name, None)
V3_STOCK_ANALYSIS_OUTPUT_CONTRACT["structured_conclusions"] = _STRUCTURED_CONCLUSIONS
V3_STOCK_ANALYSIS_OUTPUT_CONTRACT["ownership_claims"] = [
    {
        "claim_kind": " | ".join(("liquidity", "buyback", "short_interest", "listing", "long_holder_ownership")),
        "subject_role": "company | market | short_position | long_holder",
        "measure": " | ".join(OWNERSHIP_MEASURES),
        "binding": {
            "source_ids": ["string"],
            "deterministic_field": " | ".join(
                field.deterministic_field for field in OWNERSHIP_FIELD_REGISTRY.values()
            ),
            "asserted_value": "number | string | boolean | null",
            "asserted_unit": "date | days | shares | raw | identifier | status | currency | percent",
        },
        "limitation_codes": ["string"],
    }
]

QUALITATIVE_STOCK_ANALYSIS_OUTPUT_CONTRACT = {
    key: value
    for key, value in STOCK_ANALYSIS_OUTPUT_CONTRACT.items()
    if key
    not in {
        "scenario_bundles",
        "forward_scenario_analysis",
        "historical_forecast_table",
        "peak_margin_bridge",
        "scenario_driver_attribution",
    }
}
V3_QUALITATIVE_STOCK_ANALYSIS_OUTPUT_CONTRACT = {
    key: value
    for key, value in V3_STOCK_ANALYSIS_OUTPUT_CONTRACT.items()
    if key
    not in {
        "scenario_bundles",
        "forward_scenario_analysis",
        "historical_forecast_table",
        "peak_margin_bridge",
        "scenario_driver_attribution",
    }
}


THESIS_UPDATE_SECTIONS = (
    "verdict",
    "confidence",
    "thesis",
    "business_model",
    "revenue_drivers",
    "margins_and_operating_leverage",
    "balance_sheet_and_capital_allocation",
    "management_and_execution",
    "ownership_and_insiders",
    "valuation_expectations",
    "risks_and_disconfirming_evidence",
    "triggers_and_break_conditions",
    "missing_information",
)

THESIS_UPDATE_OUTPUT_CONTRACT = {
    "impact": (
        "no_material_change | thesis_strengthened | thesis_weakened | "
        "activation_trigger_reached | thesis_break_triggered | "
        "full_reassessment_required"
    ),
    "summary": "string",
    "changed_sections": [" | ".join(THESIS_UPDATE_SECTIONS)],
    "thesis": STOCK_ANALYSIS_OUTPUT_CONTRACT,
}


QUALITATIVE_THESIS_UPDATE_OUTPUT_CONTRACT = {
    key: value
    for key, value in THESIS_UPDATE_OUTPUT_CONTRACT.items()
    if key != "thesis"
}
QUALITATIVE_THESIS_UPDATE_OUTPUT_CONTRACT["thesis"] = (
    QUALITATIVE_STOCK_ANALYSIS_OUTPUT_CONTRACT
)
V3_QUALITATIVE_THESIS_UPDATE_OUTPUT_CONTRACT = {
    key: value
    for key, value in THESIS_UPDATE_OUTPUT_CONTRACT.items()
    if key != "thesis"
}
V3_QUALITATIVE_THESIS_UPDATE_OUTPUT_CONTRACT["thesis"] = (
    V3_QUALITATIVE_STOCK_ANALYSIS_OUTPUT_CONTRACT
)


SCENARIO_AUTHORING_OUTPUT_CONTRACT = {
    "case_horizon_months": "integer",
    "scenario_bundles": [_scenario_bundle_contract()],
}


def stock_analysis_json_schema() -> dict:
    return _contract_to_json_schema(STOCK_ANALYSIS_OUTPUT_CONTRACT)


def qualitative_stock_analysis_json_schema() -> dict:
    return _contract_to_json_schema(QUALITATIVE_STOCK_ANALYSIS_OUTPUT_CONTRACT)


def v3_qualitative_stock_analysis_json_schema() -> dict:
    contract = {
        key: value
        for key, value in V3_STOCK_ANALYSIS_OUTPUT_CONTRACT.items()
        if key not in {
            "scenario_bundles",
            "forward_scenario_analysis",
            "historical_forecast_table",
            "peak_margin_bridge",
            "scenario_driver_attribution",
        }
    }
    return _contract_to_json_schema(contract)


def thesis_update_json_schema() -> dict:
    return _contract_to_json_schema(THESIS_UPDATE_OUTPUT_CONTRACT)


def qualitative_thesis_update_json_schema() -> dict:
    return _contract_to_json_schema(QUALITATIVE_THESIS_UPDATE_OUTPUT_CONTRACT)


def v3_qualitative_thesis_update_json_schema() -> dict:
    return _contract_to_json_schema(V3_QUALITATIVE_THESIS_UPDATE_OUTPUT_CONTRACT)


def scenario_authoring_json_schema() -> dict:
    schema = _contract_to_json_schema(SCENARIO_AUTHORING_OUTPUT_CONTRACT)
    net_debt_change = schema["properties"]["scenario_bundles"]["items"][
        "properties"
    ]["net_debt_change"]
    net_debt_change["description"] = (
        "Projected net-debt change. If value is exactly zero, "
        "provenance_type must be not_applicable; non-zero values must be "
        "source_backed or analyst_sensitivity. Always provide a mechanism."
    )
    net_debt_change["properties"]["value"]["description"] = (
        "Use zero only with provenance_type not_applicable."
    )
    net_debt_change["properties"]["provenance_type"]["description"] = (
        "Use not_applicable for exactly zero; use source_backed or "
        "analyst_sensitivity for non-zero changes."
    )
    return schema


def _contract_to_json_schema(specification) -> dict:
    if isinstance(specification, dict):
        schema = {
            "type": "object",
            "properties": {
                key: _contract_to_json_schema(value) for key, value in specification.items()
            },
            "required": list(specification),
            "additionalProperties": False,
        }
        if isinstance(specification, _NullableObjectContract):
            return {"anyOf": [schema, {"type": "null"}]}
        return schema

    if isinstance(specification, list):
        if not specification:
            return {"type": "array", "maxItems": 0}
        return {
            "type": "array",
            "items": _contract_to_json_schema(specification[0]),
        }

    options = specification.split(" | ")
    primitive_types = {"boolean", "integer", "number", "string", "null"}
    if all(option in primitive_types for option in options):
        types = [option for option in options]
        return {"type": types[0] if len(types) == 1 else types}

    if "null" in options:
        return {
            "anyOf": [
                {"type": "string", "enum": [item for item in options if item != "null"]},
                {"type": "null"},
            ]
        }

    return {"type": "string", "enum": options}
