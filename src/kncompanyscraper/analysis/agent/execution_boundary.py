from dataclasses import dataclass, fields, is_dataclass
import re

from kncompanyscraper.analysis.agent.result_parser import (
    StockAnalysisValidationError,
    parse_stock_analysis_result,
)
from kncompanyscraper.analysis.agent.output_schema import StockAnalysisResult


@dataclass(frozen=True)
class PersistedStockAnalysis:
    analysis_id: int
    result: StockAnalysisResult


class AgentExecutionBoundary:
    VALIDATION_VERSION = "agent-boundary-v8"
    NO_INSIDER_ASSESSMENT = (
        "No insider transactions are available for the selected period. "
        "No inference can be made from their absence."
    )

    def __init__(self, analysis_repository):
        self.analysis_repository = analysis_repository

    def persist_response(
        self,
        raw_response: str,
        candidate,
        created_by: str,
        metadata: dict | None = None,
    ) -> PersistedStockAnalysis:
        result = parse_stock_analysis_result(raw_response)
        if result.company_id != candidate.company_id:
            raise StockAnalysisValidationError(
                f"result.company_id {result.company_id} does not match candidate {candidate.company_id}"
            )
        if result.ticker.strip().upper() != candidate.ticker.strip().upper():
            raise StockAnalysisValidationError(
                f"result.ticker {result.ticker!r} does not match candidate {candidate.ticker!r}"
            )

        document_source_ids = {
            source.get("source_id")
            for source in candidate.research_evidence.get("documents", [])
        }
        insider_source_ids = {
            source.get("source_id")
            for source in candidate.research_evidence.get("insider_transactions", [])
        }
        valuation_source_aliases = {
            **self._deterministic_source_aliases(candidate),
            **self._valuation_source_aliases(candidate),
        }
        for citation in result.citations:
            citation.source_id = valuation_source_aliases.get(
                citation.source_id, citation.source_id
            )
        result.risk_profile_evidence = [
            valuation_source_aliases.get(source_id, source_id)
            for source_id in result.risk_profile_evidence
        ]
        known_source_ids = (
            document_source_ids
            | insider_source_ids
            | set(valuation_source_aliases.values())
        )
        unknown_source_ids = sorted(
            {citation.source_id for citation in result.citations} - known_source_ids
        )
        if unknown_source_ids:
            raise StockAnalysisValidationError(
                "result cites unknown evidence source(s): " + ", ".join(unknown_source_ids)
            )
        unknown_risk_source_ids = sorted(
            set(result.risk_profile_evidence) - known_source_ids
        )
        if unknown_risk_source_ids:
            raise StockAnalysisValidationError(
                "risk profile cites unknown evidence source(s): "
                + ", ".join(unknown_risk_source_ids)
            )

        deterministic_checks, deterministic_warnings = self._validate_model_owned_arithmetic(
            result, candidate
        )
        self._validate_scenario_characterization(result)
        self._validate_management_sources(result, document_source_ids)
        self._validate_activated_case(result, candidate)
        self._validate_risk_profile(result, candidate)

        insider_checks = []
        warnings = list(deterministic_warnings)
        if insider_source_ids:
            cited_source_ids = {citation.source_id for citation in result.citations}
            if not cited_source_ids.intersection(insider_source_ids):
                raise StockAnalysisValidationError(
                    "insider assessment must cite at least one supplied insider transaction"
                )
            insider_checks.append(
                f"insider assessment references supplied events ({len(insider_source_ids)} available)"
            )
        else:
            if result.insider_assessment != self.NO_INSIDER_ASSESSMENT:
                warnings.append("model insider assessment replaced because no events were supplied")
            result.insider_assessment = self.NO_INSIDER_ASSESSMENT
            insider_checks.append("no-data insider assessment normalized")

        validation_metadata = dict(metadata or {})
        valuation_provenance = self._valuation_provenance(candidate)
        if valuation_provenance is not None:
            validation_metadata["valuation_provenance"] = valuation_provenance
        validation_metadata.update(
            {
                "validation_version": self.VALIDATION_VERSION,
                "validation_status": "accepted",
                "deterministic_value_checks": [
                    *deterministic_checks,
                    "model-owned expected return components are null",
                ],
                "insider_checks": insider_checks,
                "warnings": warnings,
            }
        )

        analysis_id = self.analysis_repository.save_stock_analysis(
            result,
            created_by=created_by,
            metadata=validation_metadata,
        )
        return PersistedStockAnalysis(analysis_id=analysis_id, result=result)

    @classmethod
    def _validate_model_owned_arithmetic(cls, result, candidate):
        if result.valuation_scenarios:
            raise StockAnalysisValidationError(
                "forward valuation scenarios are not allowed by the reverse-only policy"
            )

        if any(value is not None for value in result.expected_return_components.values()):
            raise StockAnalysisValidationError(
                "model-generated expected return components are not allowed"
            )
        cls._validate_prose_upside(result)
        return ["forward valuation scenarios are disabled"], []

    @staticmethod
    def _validate_scenario_characterization(result):
        texts = [
            result.one_sentence_thesis,
            result.activation_trigger or "",
            result.business_model_assessment,
            result.revenue_growth_case,
            *result.confirming_evidence,
            *result.disconfirming_evidence,
        ]
        joined = "\n".join(texts)
        if re.search(
            r"\b(conservative|realistic|likely|probable)\s+base[- ]case\b",
            joined,
            re.IGNORECASE,
        ):
            raise StockAnalysisValidationError(
                "scenario labels cannot be characterized as probabilities"
            )
        if re.search(
            r"\b(requires? no|no)\s+(?:net\s+)?reinvestment(?:\s+is\s+required)?\b",
            joined,
            re.IGNORECASE,
        ):
            raise StockAnalysisValidationError(
                "normalized reinvestment cannot be described as no reinvestment required"
            )

    @classmethod
    def _validate_prose_upside(cls, result):
        texts = [
            result.one_sentence_thesis,
            result.activation_trigger or "",
        ]
        for text in texts:
            for match in re.finditer(r"(\d+(?:\.\d+)?)%\+?\s+upside", text, re.IGNORECASE):
                raise StockAnalysisValidationError(
                    "prose upside claims are not allowed by the reverse-only policy"
                )

    @staticmethod
    def _field(value, name):
        if isinstance(value, dict):
            return value.get(name)
        return getattr(value, name, None)

    @classmethod
    def _valuation_provenance(cls, candidate):
        reverse_dcf = candidate.full_results.get("reverse_dcf")
        if reverse_dcf is None:
            return None
        assumptions = cls._field(reverse_dcf, "assumptions")
        implied_expectations = cls._field(reverse_dcf, "implied_expectations") or {}
        required_return = cls._field(reverse_dcf, "required_return")
        normalization = cls._field(reverse_dcf, "normalization")
        rate_profiles = cls._field(required_return, "profiles") or {}
        sensitivities = cls._field(reverse_dcf, "discount_rate_sensitivities") or {}
        expectation_curve = cls._field(reverse_dcf, "expectation_curve") or ()
        return {
            "status": cls._field(reverse_dcf, "status"),
            "reverse_dcf_policy_version": cls._field(reverse_dcf, "policy_version"),
            "price_date": cls._field(reverse_dcf, "price_date"),
            "current_price": cls._field(reverse_dcf, "current_price"),
            "assumptions": {
                name: cls._field(assumptions, name)
                for name in (
                    "projection_years",
                    "revenue_growth",
                    "ebit_margin",
                    "tax_rate",
                    "discount_rate",
                    "terminal_growth",
                    "net_reinvestment_rate",
                    "reinvestment_return",
                )
            },
            "assumption_sources": cls._field(reverse_dcf, "assumption_sources") or {},
            "normalized_fcf_margin": cls._field(
                reverse_dcf, "normalized_fcf_margin"
            ),
            "normalization": cls._serialize_normalization(normalization),
            "reinvestment_roic": cls._field(reverse_dcf, "reinvestment_roic"),
            "required_return": {
                name: cls._field(required_return, name)
                for name in (
                    "policy_version",
                    "risk_free_rate",
                    "risk_free_rate_date",
                    "risk_free_rate_source",
                    "equity_risk_premium",
                    "market_cap",
                    "size_bucket",
                    "size_adjustment",
                    "baseline_profile",
                )
            },
            "discount_rate_profiles": {
                name: {
                    key: cls._field(profile, key)
                    for key in (
                        "label",
                        "business_risk_adjustment",
                        "discount_rate",
                    )
                }
                for name, profile in rate_profiles.items()
            },
            "implied_expectations": {
                name: {
                    key: cls._field(expectation, key)
                    for key in (
                        "status",
                        "source_id",
                        "lower_bound",
                        "upper_bound",
                        "implied_value",
                        "modeled_price",
                        "modeled_price_range",
                        "outside_direction",
                        "required_value_hint",
                        "reason",
                    )
                }
                for name, expectation in implied_expectations.items()
            },
            "expectation_curve": [
                {
                    "revenue_growth": cls._field(point, "revenue_growth"),
                    "ebit_margin_expectation": cls._serialize_expectation(
                        cls._field(point, "ebit_margin_expectation")
                    ),
                }
                for point in expectation_curve
            ],
            "discount_rate_sensitivities": {
                profile_name: {
                    "label": cls._field(sensitivity, "label"),
                    "discount_rate": cls._field(sensitivity, "discount_rate"),
                    "business_risk_adjustment": cls._field(
                        sensitivity, "business_risk_adjustment"
                    ),
                    "implied_expectations": cls._serialize_expectations(
                        cls._field(sensitivity, "implied_expectations") or {}
                    ),
                    "expectation_curve": cls._serialize_expectation_curve(
                        cls._field(sensitivity, "expectation_curve") or ()
                    ),
                }
                for profile_name, sensitivity in sensitivities.items()
            },
            "warnings": list(cls._field(reverse_dcf, "warnings") or []),
        }

    @classmethod
    def _serialize_normalization(cls, normalization):
        if normalization is None:
            return None

        def window(value):
            if value is None:
                return None
            return {
                name: cls._field(value, name)
                for name in (
                    "years",
                    "start_year",
                    "end_year",
                    "ebit_margin",
                    "reported_fcf_margin",
                    "operating_cash_flow_margin",
                )
            }

        serialized = {
            name: cls._field(normalization, name)
            for name in (
                "confidence",
                "selected_window_years",
                "annual_fcf_margin_stddev",
                "annual_fcf_margin_range",
                "negative_fcf_years",
                "fcf_sign_changes",
                "highly_volatile_fcf",
                "material_window_disagreement",
                "material_aggregate_investing",
                "reasons",
            )
        } | {
            "three_year": window(cls._field(normalization, "three_year")),
            "five_year": window(cls._field(normalization, "five_year")),
        }
        serialized["reasons"] = list(serialized["reasons"] or [])
        return serialized

    @classmethod
    def _serialize_expectations(cls, expectations):
        return {
            name: cls._serialize_expectation(expectation)
            for name, expectation in expectations.items()
        }

    @classmethod
    def _serialize_expectation_curve(cls, expectation_curve):
        return [
            {
                "revenue_growth": cls._field(point, "revenue_growth"),
                "ebit_margin_expectation": cls._serialize_expectation(
                    cls._field(point, "ebit_margin_expectation")
                ),
            }
            for point in expectation_curve
        ]

    @classmethod
    def _serialize_expectation(cls, expectation):
        return {
            key: cls._field(expectation, key)
            for key in (
                "status",
                "source_id",
                "lower_bound",
                "upper_bound",
                "implied_value",
                "modeled_price",
                "modeled_price_range",
                "outside_direction",
                "required_value_hint",
                "reason",
            )
        }

    @classmethod
    def _valuation_source_aliases(cls, candidate):
        reverse_dcf = candidate.full_results.get("reverse_dcf")
        if reverse_dcf is None:
            return {}
        aliases = {}
        implied_expectations = cls._field(reverse_dcf, "implied_expectations") or {}
        for assumption, expectation in implied_expectations.items():
            source_id = (
                cls._field(expectation, "source_id")
                or f"valuation:reverse_dcf:{assumption}"
            )
            aliases[source_id] = source_id
            aliases[
                f"full_results.reverse_dcf.implied_expectations.{assumption}"
            ] = source_id
        sensitivities = cls._field(reverse_dcf, "discount_rate_sensitivities") or {}
        for profile, sensitivity in sensitivities.items():
            expectations = cls._field(sensitivity, "implied_expectations") or {}
            for assumption, expectation in expectations.items():
                source_id = (
                    cls._field(expectation, "source_id")
                    or f"valuation:reverse_dcf:{profile}:{assumption}"
                )
                aliases[source_id] = source_id
                aliases[
                    "full_results.reverse_dcf.discount_rate_sensitivities."
                    f"{profile}.implied_expectations.{assumption}"
                ] = source_id
            expectation_curve = cls._field(sensitivity, "expectation_curve") or ()
            for point in expectation_curve:
                expectation = cls._field(point, "ebit_margin_expectation")
                source_id = cls._field(expectation, "source_id")
                if source_id:
                    aliases[source_id] = source_id
        expectation_curve = cls._field(reverse_dcf, "expectation_curve") or ()
        for point in expectation_curve:
            expectation = cls._field(point, "ebit_margin_expectation")
            source_id = cls._field(expectation, "source_id")
            if source_id:
                aliases[source_id] = source_id
        return aliases

    @classmethod
    def _validate_risk_profile(cls, result, candidate):
        if result.risk_profile == "unclassified":
            if result.risk_profile_evidence:
                raise StockAnalysisValidationError(
                    "unclassified risk profile cannot carry classification evidence"
                )
            return
        if not result.risk_profile_evidence:
            raise StockAnalysisValidationError(
                "classified risk profile requires cited evidence"
            )
        reverse_dcf = candidate.full_results.get("reverse_dcf")
        sensitivities = cls._field(reverse_dcf, "discount_rate_sensitivities") or {}
        if result.risk_profile not in sensitivities:
            raise StockAnalysisValidationError(
                "risk profile does not match a deterministic discount-rate sensitivity"
            )

    @classmethod
    def _deterministic_source_aliases(cls, candidate):
        aliases = {}

        def visit(value, path):
            if is_dataclass(value):
                for field in fields(value):
                    visit(getattr(value, field.name), [*path, field.name])
                return
            if isinstance(value, dict):
                for key, nested in value.items():
                    visit(nested, [*path, str(key)])
                return
            if isinstance(value, (list, tuple)):
                for index, nested in enumerate(value):
                    visit(nested, [*path, str(index)])
                return
            if not path:
                return
            source_id = "deterministic:" + ":".join(path)
            aliases[source_id] = source_id
            aliases["full_results." + ".".join(path)] = source_id

        visit(candidate.full_results, [])
        return aliases

    @staticmethod
    def _validate_management_sources(result, document_source_ids):
        for claim in result.management_credibility_ledger:
            if not claim.source_ids:
                raise StockAnalysisValidationError(
                    "management credibility claims require document source_ids"
                )
            unknown_source_ids = sorted(set(claim.source_ids) - document_source_ids)
            if unknown_source_ids:
                raise StockAnalysisValidationError(
                    "management credibility claim cites unknown document source(s): "
                    + ", ".join(unknown_source_ids)
                )

    @staticmethod
    def _validate_activated_case(result, candidate):
        if result.verdict != "activated_case":
            return
        reverse_dcf = candidate.full_results.get("reverse_dcf")
        status = AgentExecutionBoundary._field(reverse_dcf, "status")
        implied_expectations = AgentExecutionBoundary._field(
            reverse_dcf, "implied_expectations"
        )
        if status != "available" or not implied_expectations:
            raise StockAnalysisValidationError(
                "activated_case requires deterministic reverse-DCF expectations"
            )
