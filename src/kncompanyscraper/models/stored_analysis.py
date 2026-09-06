from __future__ import annotations

from kncompanyscraper.analysis.policy_versions import FORWARD_SCENARIO_POLICY_VERSION
from kncompanyscraper.analysis.agent.conclusion_contract import (
    project_structured_conclusions,
    render_ownership_claims,
)


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
    @property
    def is_legacy_v2(self) -> bool:
        return self.thesis_card_version == "individual-thesis-card-v2"

    @property
    def is_current_forward_scenario(self) -> bool:
        return (
            self.thesis_card_version
            in {"individual-thesis-card-v3-structured-conclusions"}
            and self.forward_scenario_policy_version == FORWARD_SCENARIO_POLICY_VERSION
        )

    @property
    def is_enriched_forward_scenario(self) -> bool:
        forward = self.forward_scenario
        return (
            self.is_current_forward_scenario
            and isinstance(forward, dict)
            and forward.get("status") == "available"
            and isinstance(self.content.get("scenario_bundles"), list)
            and len(self.content["scenario_bundles"]) == 3
            and isinstance(forward.get("bands"), list)
            and len(forward["bands"]) == 3
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
        return self._projected_content().get("revenue_resilience") or {}

    def _projected_content(self) -> dict:
        structured = self.content.get("structured_conclusions")
        if not isinstance(structured, dict):
            return self.content
        return {
            **self.content,
            **project_structured_conclusions(
                structured, self.content.get("ownership_claims") or []
            ),
        }

    @property
    def one_sentence_thesis(self) -> str:
        return self._projected_content()["one_sentence_thesis"]

    @property
    def reverse_dcf_expectation_assessment(self):
        return self._projected_content().get(
            "reverse_dcf_expectation_assessment", "unassessable"
        )

    @property
    def thesis_break_conditions(self) -> tuple:
        return tuple(self._projected_content().get("thesis_break_conditions", []))

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
    def latent_case_type(self) -> str | None:
        """Return the explicit subtype, or null for legacy v2 cards."""
        return self.content.get("latent_case_type")

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
        content = self._projected_content()
        provenance = self.metadata.get("valuation_provenance") or {}
        forward = self.forward_scenario or {}
        bundles = {
            item.get("case"): item
            for item in content.get("scenario_bundles", [])
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
                        "horizon_months", content.get("case_horizon_months")
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
            "verdict_label": (
                f"{self.latent_case_type}-latent"
                if self.verdict == "latent_case" and self.latent_case_type
                else self.verdict
            ),
            "latent_case_type": self.latent_case_type,
            "activation_trigger": content.get("activation_trigger"),
            "activation_trigger_spec": content.get("activation_trigger_spec"),
            "activation_trigger_evidence": list(
                content.get("activation_trigger_evidence", [])
            ),
            "confidence": self.confidence,
            "current_price": provenance.get("current_price"),
            "horizon_months": content.get("case_horizon_months"),
            "one_sentence_thesis": self.one_sentence_thesis,
            "company_fact_ledger": content.get("company_fact_ledger", {}),
            "management_claims": content.get("management_claims", []),
            "management_credibility_ledger": content.get(
                "management_credibility_ledger", []
            ),
            "ownership_and_flow_assessment": render_ownership_claims(
                content.get("ownership_claims") or []
            ),
            "falsifiable_case": content.get("falsifiable_case"),
            "revenue_resilience": self.revenue_resilience,
            "reverse_dcf": {
                "assessment": self.reverse_dcf_expectation_assessment,
                "rationale": content.get(
                    "reverse_dcf_expectation_rationale", ""
                ),
                "selected_curve_points": curve,
            },
            "scenarios": scenarios,
            "scenario_driver_attribution": content.get(
                "scenario_driver_attribution"
            ),
            "why_now": timing.get("why_now", ""),
            "strongest_confirming_evidence": content.get(
                "strongest_confirming_evidence"
            ),
            "strongest_disconfirming_evidence": content.get(
                "strongest_disconfirming_evidence"
            ),
            "thesis_break_conditions": list(self.thesis_break_conditions),
            "thesis_break_tests": list(
                content.get("thesis_break_tests", [])
            ),
            "material_missing_information": list(
                content.get("missing_information", [])
            ),
            "missing_information_details": list(
                content.get("missing_information_details", [])
            ),
            "confidence_cap": (self.metadata.get("confidence_cap") or {}).get("cap"),
            "capital_allocation_limitations": list(
                self.forward_scenario_metadata.get(
                    "capital_allocation_limitations", []
                )
            ),
        }


def as_stored_analysis(value: dict) -> StoredAnalysisDocument:
    return value if isinstance(value, StoredAnalysisDocument) else StoredAnalysisDocument(value)
