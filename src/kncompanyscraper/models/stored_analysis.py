from __future__ import annotations


class StoredAnalysisDocument(dict):
    """Mapping-compatible typed accessors for a persisted stock analysis."""

    @property
    def analysis_id(self) -> int:
        return self["analysis_id"]

    @property
    def company_id(self) -> int:
        return self["company_id"]

    @property
    def content(self) -> dict:
        return self["content"]

    @property
    def metadata(self) -> dict:
        return self["metadata"]

    @property
    def forward_scenario(self) -> dict | None:
        return self.content.get("forward_scenario_analysis")

    @property
    def forward_scenario_metadata(self) -> dict:
        return self.metadata.get("forward_scenario") or {}

    @property
    def policy_version(self) -> str | None:
        return self.metadata.get("policy_version")

    @property
    def ticker(self) -> str:
        return self.content["ticker"]

    @property
    def confidence(self) -> str:
        return self.content["confidence"]

    @property
    def risk_profile(self) -> str:
        return self.content["risk_profile"]

    @property
    def one_sentence_thesis(self) -> str:
        return self.content["one_sentence_thesis"]

    @property
    def reverse_dcf_expectation_assessment(self):
        return self.content["reverse_dcf_expectation_assessment"]

    @property
    def thesis_break_conditions(self) -> tuple:
        return tuple(self.content["thesis_break_conditions"])

    @property
    def analysis_status(self) -> str | None:
        return self.content.get("analysis_status")

    @property
    def portfolio_eligibility(self) -> str | None:
        return self.content.get("portfolio_eligibility")

    @property
    def portfolio_reason_code(self) -> str:
        return self.content["portfolio_reason_code"]

    @property
    def reconsideration_trigger(self):
        return self.content.get("reconsideration_trigger")

    @property
    def verdict(self) -> str:
        return self.content["verdict"]

    @property
    def required_return(self) -> float | None:
        return self.forward_scenario_metadata.get("required_return")

    @property
    def evidence_as_of(self) -> str | None:
        return self.metadata.get("evidence_as_of")


def as_stored_analysis(value: dict) -> StoredAnalysisDocument:
    return value if isinstance(value, StoredAnalysisDocument) else StoredAnalysisDocument(value)
