from __future__ import annotations

from kncompanyscraper.analysis.policy_versions import FORWARD_SCENARIO_POLICY_VERSION


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
    def thesis_card_version(self) -> str | None:
        return self.content.get("thesis_card_version")

    @property
    def forward_scenario_policy_version(self) -> str | None:
        return (self.forward_scenario or {}).get("policy_version")

    @property
    def is_current_forward_scenario(self) -> bool:
        return (
            self.thesis_card_version == "individual-thesis-card-v2"
            and self.forward_scenario_policy_version == FORWARD_SCENARIO_POLICY_VERSION
        )

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
    def revenue_resilience(self) -> dict:
        return self.content.get("revenue_resilience") or {}

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

    @property
    def thesis_summary(self) -> dict:
        """Return the deterministic, consumer-facing thesis projection.

        This only selects and organizes persisted fields. It deliberately does
        not recreate valuation arithmetic or translate historical v1 fields.
        """
        provenance = self.metadata.get("valuation_provenance") or {}
        forward = self.forward_scenario or {}
        bundles = {
            item.get("case"): item
            for item in self.content.get("scenario_bundles", [])
            if isinstance(item, dict) and item.get("case")
        }
        scenarios = {}
        if forward.get("status") == "available":
            bands = {
                band.get("case"): band
                for band in forward.get("bands", [])
                if isinstance(band, dict)
            }
            for case in ("bear", "base", "bull"):
                band = bands.get(case)
                if band is None:
                    continue
                bundle = bundles.get(case, {})
                scenarios[case] = {
                    "price_range": [band["low_price"], band["high_price"]],
                    "holding_value_range": [
                        band.get("low_holding_value"),
                        band.get("high_holding_value"),
                    ],
                    "annualized_return_range": [
                        band["low_annualized_return"],
                        band["high_annualized_return"],
                    ],
                    "horizon_months": band.get(
                        "horizon_months", self.content.get("case_horizon_months")
                    ),
                    "assumptions": bundle,
                    "explanation": bundle.get("mechanism", ""),
                    "capital_allocation": next(
                        (
                            bridge
                            for bridge in self.forward_scenario_metadata.get(
                                "net_debt_bridges", []
                            )
                            if bridge.get("case") == case
                        ),
                        None,
                    ),
                }
        timing = self.content.get("timing_assessment") or {}
        curve = provenance.get("expectation_curve") or []
        return {
            "verdict": self.verdict,
            "confidence": self.confidence,
            "current_price": provenance.get("current_price"),
            "horizon_months": self.content.get("case_horizon_months"),
            "one_sentence_thesis": self.one_sentence_thesis,
            "revenue_resilience": self.revenue_resilience,
            "reverse_dcf": {
                "assessment": self.reverse_dcf_expectation_assessment,
                "rationale": self.content.get(
                    "reverse_dcf_expectation_rationale", ""
                ),
                "selected_curve_points": curve,
            },
            "scenarios": scenarios,
            "why_now": timing.get("why_now", ""),
            "thesis_break_conditions": list(self.thesis_break_conditions),
            "material_missing_information": list(
                self.content.get("missing_information", [])
            ),
            "capital_allocation_limitations": list(
                self.forward_scenario_metadata.get(
                    "capital_allocation_limitations", []
                )
            ),
        }


def as_stored_analysis(value: dict) -> StoredAnalysisDocument:
    return value if isinstance(value, StoredAnalysisDocument) else StoredAnalysisDocument(value)
