from dataclasses import asdict, dataclass, field
from typing import Literal


AnalysisVerdict = Literal["reject", "watch", "latent_case", "activated_case"]
Confidence = Literal["low", "medium", "high"]
ScenarioLabel = Literal["bear", "base", "bull"]
ClaimResult = Literal["kept", "delayed", "missed", "changed", "unverifiable"]


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
class StockAnalysisResult:
    company_id: int
    ticker: str
    company_name: str
    verdict: AnalysisVerdict
    confidence: Confidence
    one_sentence_thesis: str

    case_horizon_months: int | None = None
    activation_trigger: str | None = None
    business_model_assessment: str = ""
    revenue_growth_case: str = ""
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


STOCK_ANALYSIS_OUTPUT_CONTRACT = {
    "company_id": "integer",
    "ticker": "string",
    "company_name": "string",
    "verdict": "reject | watch | latent_case | activated_case",
    "confidence": "low | medium | high",
    "one_sentence_thesis": "string",
    "case_horizon_months": "integer | null",
    "activation_trigger": "string | null",
    "business_model_assessment": "string",
    "revenue_growth_case": "string",
    "current_ebit_margin": "number | null",
    "defensible_peak_ebit_margin": "number | null",
    "peak_margin_evidence": ["string"],
    "valuation_scenarios": [
        {
            "label": "bear | base | bull",
            "implied_value_per_share": "number | null",
            "expected_return": "number | null",
            "assumptions": ["string"],
        }
    ],
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


def stock_analysis_json_schema() -> dict:
    return _contract_to_json_schema(STOCK_ANALYSIS_OUTPUT_CONTRACT)


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
