from dataclasses import asdict, dataclass, field
from typing import Literal


AnalysisVerdict = Literal["reject", "watch", "latent_case", "activated_case"]
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
ScenarioLabel = Literal["bear", "base", "bull"]
ClaimResult = Literal["kept", "delayed", "missed", "changed", "unverifiable"]
BusinessRiskProfile = Literal[
    "noncyclical_recurring",
    "slightly_cyclical",
    "cyclical_or_other_risk",
    "unclassified",
]
ReverseDcfExpectationAssessment = Literal[
    "plausible",
    "demanding",
    "unsupported",
    "unassessable",
]
ThesisUpdateImpact = Literal[
    "no_material_change",
    "thesis_strengthened",
    "thesis_weakened",
    "activation_trigger_reached",
    "thesis_break_triggered",
    "full_reassessment_required",
]


@dataclass
class ValuationScenario:
    label: ScenarioLabel
    implied_value_per_share: float | None
    expected_return: float | None
    assumptions: list[str] = field(default_factory=list)


@dataclass
class ManagementClaimAssessment:
    date: str
    claim: str
    expected_timing: str | None
    observed_outcome: str | None
    result: ClaimResult
    source_ids: list[str] = field(default_factory=list)


@dataclass
class EvidenceCitation:
    source_id: str
    claim: str


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
class StockAnalysisResult:
    company_id: int
    ticker: str
    company_name: str
    verdict: AnalysisVerdict
    confidence: Confidence
    one_sentence_thesis: str
    confidence_limitations: list[str] = field(default_factory=list)
    company_fact_ledger: CompanyFactLedger = field(default_factory=CompanyFactLedger)
    portfolio_eligibility: PortfolioEligibility = "not_investable"
    portfolio_reason_code: PortfolioReasonCode = "evidence_insufficient"
    reconsideration_trigger: str | None = None

    case_horizon_months: int | None = None
    activation_trigger: str | None = None
    business_model_assessment: str = ""
    revenue_growth_case: str = ""
    reverse_dcf_expectation_assessment: ReverseDcfExpectationAssessment = "unassessable"
    reverse_dcf_expectation_rationale: str = ""
    risk_profile: BusinessRiskProfile = "unclassified"
    risk_profile_confidence: Confidence = "low"
    risk_profile_evidence: list[str] = field(default_factory=list)
    current_ebit_margin: float | None = None
    defensible_peak_ebit_margin: float | None = None
    peak_margin_evidence: list[str] = field(default_factory=list)
    valuation_scenarios: list[ValuationScenario] = field(default_factory=list)
    expected_return_components: dict[str, float | None] = field(default_factory=dict)
    management_assessment: str = ""
    management_credibility_ledger: list[ManagementClaimAssessment] = field(default_factory=list)
    ownership_and_flow_assessment: str = ""
    insider_assessment: str = ""
    confirming_evidence: list[str] = field(default_factory=list)
    disconfirming_evidence: list[str] = field(default_factory=list)
    thesis_break_conditions: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    citations: list[EvidenceCitation] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ThesisUpdateResult:
    impact: ThesisUpdateImpact
    summary: str
    changed_sections: list[str]
    thesis: StockAnalysisResult

    def to_dict(self) -> dict:
        return asdict(self)


STOCK_ANALYSIS_OUTPUT_CONTRACT = {
    "company_id": "integer",
    "ticker": "string",
    "company_name": "string",
    "verdict": "reject | watch | latent_case | activated_case",
    "confidence": "low | medium | high",
    "one_sentence_thesis": "string",
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
    "business_model_assessment": "string",
    "revenue_growth_case": "string",
    "reverse_dcf_expectation_assessment": (
        "plausible | demanding | unsupported | unassessable"
    ),
    "reverse_dcf_expectation_rationale": "string",
    "risk_profile": (
        "noncyclical_recurring | slightly_cyclical | "
        "cyclical_or_other_risk | unclassified"
    ),
    "risk_profile_confidence": "low | medium | high",
    "risk_profile_evidence": ["string"],
    "current_ebit_margin": "number | null",
    "defensible_peak_ebit_margin": "number | null",
    "peak_margin_evidence": ["string"],
    "valuation_scenarios": [],
    "expected_return_components": {
        "revenue_growth": "number | null",
        "margin_change": "number | null",
        "multiple_change": "number | null",
        "balance_sheet_change": "number | null",
        "dilution": "number | null",
    },
    "management_assessment": "string",
    "management_credibility_ledger": [
        {
            "date": "string",
            "claim": "string",
            "expected_timing": "string | null",
            "observed_outcome": "string | null",
            "result": "kept | delayed | missed | changed | unverifiable",
            "source_ids": ["string"],
        }
    ],
    "ownership_and_flow_assessment": "string",
    "insider_assessment": "string",
    "confirming_evidence": ["string"],
    "disconfirming_evidence": ["string"],
    "thesis_break_conditions": ["string"],
    "missing_information": ["string"],
    "citations": [
        {
            "source_id": "string",
            "claim": "string",
        }
    ],
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


def stock_analysis_json_schema() -> dict:
    return _contract_to_json_schema(STOCK_ANALYSIS_OUTPUT_CONTRACT)


def thesis_update_json_schema() -> dict:
    return _contract_to_json_schema(THESIS_UPDATE_OUTPUT_CONTRACT)


def _contract_to_json_schema(specification) -> dict:
    if isinstance(specification, dict):
        return {
            "type": "object",
            "properties": {
                key: _contract_to_json_schema(value) for key, value in specification.items()
            },
            "required": list(specification),
            "additionalProperties": False,
        }

    if isinstance(specification, list):
        if not specification:
            return {"type": "array", "maxItems": 0}
        return {
            "type": "array",
            "items": _contract_to_json_schema(specification[0]),
        }

    options = specification.split(" | ")
    primitive_types = {"integer", "number", "string", "null"}
    if all(option in primitive_types for option in options):
        types = [option for option in options]
        return {"type": types[0] if len(types) == 1 else types}

    return {"type": "string", "enum": options}
