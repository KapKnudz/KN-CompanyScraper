from dataclasses import dataclass, fields, is_dataclass
from math import isclose
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
    VALIDATION_VERSION = "agent-boundary-v6"
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

        deterministic_checks, deterministic_warnings = self._validate_model_owned_arithmetic(
            result, candidate
        )
        self._validate_scenario_characterization(result)
        self._validate_management_sources(result, document_source_ids)
        self._validate_activated_case(result, candidate)

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
        reverse_dcf = candidate.full_results.get("reverse_dcf")
        forward_scenarios = cls._field(reverse_dcf, "forward_scenarios") or {}
        if forward_scenarios:
            expected_labels = set(forward_scenarios)
            actual_labels = {scenario.label for scenario in result.valuation_scenarios}
            if actual_labels != expected_labels or len(result.valuation_scenarios) != len(
                expected_labels
            ):
                raise StockAnalysisValidationError(
                    "valuation scenarios must match supplied deterministic scenario labels"
                )
            scenario_descriptions_replaced = False
            for scenario in result.valuation_scenarios:
                supplied = forward_scenarios[scenario.label]
                supplied_value = cls._field(supplied, "value_per_share")
                supplied_return = cls._field(supplied, "expected_return")
                if not cls._same_number(scenario.implied_value_per_share, supplied_value):
                    raise StockAnalysisValidationError(
                        f"{scenario.label} implied value does not match deterministic output"
                    )
                if not cls._same_number(scenario.expected_return, supplied_return):
                    raise StockAnalysisValidationError(
                        f"{scenario.label} expected return does not match deterministic output"
                    )
                deterministic_assumptions = cls._deterministic_assumption_descriptions(supplied)
                scenario_descriptions_replaced = (
                    scenario_descriptions_replaced
                    or scenario.assumptions != deterministic_assumptions
                )
                scenario.assumptions = deterministic_assumptions
            deterministic_checks = [
                "scenario values and expected returns match deterministic forward DCF",
                "scenario descriptions normalized from deterministic assumptions",
            ]
            deterministic_warnings = (
                ["model scenario descriptions replaced with deterministic descriptions"]
                if scenario_descriptions_replaced
                else []
            )
        else:
            for scenario in result.valuation_scenarios:
                if (
                    scenario.implied_value_per_share is not None
                    or scenario.expected_return is not None
                ):
                    raise StockAnalysisValidationError(
                        "model-generated valuation scenario values are not allowed"
                    )
            deterministic_checks = [
                "scenario values are null because deterministic forward DCF is unavailable"
            ]
            deterministic_warnings = []

        for scenario in result.valuation_scenarios:
            for assumption in scenario.assumptions:
                normalized = assumption.casefold()
                if "buyback" in normalized and any(
                    term in normalized for term in ("share count", "per-share", "eps")
                ):
                    raise StockAnalysisValidationError(
                        "buyback assumptions cannot create an unsupported per-share effect"
                    )

        if any(value is not None for value in result.expected_return_components.values()):
            raise StockAnalysisValidationError(
                "model-generated expected return components are not allowed"
            )
        cls._validate_prose_upside(result, forward_scenarios)
        return deterministic_checks, deterministic_warnings

    @classmethod
    def _deterministic_assumption_descriptions(cls, scenario):
        assumptions = cls._field(scenario, "assumptions")
        sources = cls._field(scenario, "assumption_sources") or {}
        return [
            (
                f"Projection horizon: {cls._field(assumptions, 'projection_years')} years "
                f"(source: {sources.get('projection_years', 'unspecified')})."
            ),
            (
                f"Revenue growth: {cls._field(assumptions, 'revenue_growth'):.4%} "
                f"(source: {sources.get('revenue_growth', 'unspecified')})."
            ),
            (
                f"EBIT margin: {cls._field(assumptions, 'ebit_margin'):.4%} "
                f"(source: {sources.get('ebit_margin', 'unspecified')})."
            ),
            (
                "Net reinvestment rate: "
                f"{cls._field(assumptions, 'net_reinvestment_rate'):.4%}; "
                "this is a normalized modeling input, not a claim that the business "
                "requires no reinvestment "
                f"(source: {sources.get('net_reinvestment_rate', 'unspecified')})."
            ),
            (
                f"Tax rate: {cls._field(assumptions, 'tax_rate'):.4%} "
                f"(source: {sources.get('tax_rate', 'unspecified')})."
            ),
            (
                f"Discount rate: {cls._field(assumptions, 'discount_rate'):.4%} "
                f"(source: {sources.get('discount_rate', 'unspecified')})."
            ),
            (
                f"Terminal growth: {cls._field(assumptions, 'terminal_growth'):.4%} "
                f"(source: {sources.get('terminal_growth', 'unspecified')})."
            ),
        ]

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
    def _validate_prose_upside(cls, result, forward_scenarios):
        allowed_returns = [
            cls._field(scenario, "expected_return")
            for scenario in forward_scenarios.values()
        ]
        texts = [
            result.one_sentence_thesis,
            result.activation_trigger or "",
            *[assumption for scenario in result.valuation_scenarios for assumption in scenario.assumptions],
        ]
        for text in texts:
            for match in re.finditer(r"(\d+(?:\.\d+)?)%\+?\s+upside", text, re.IGNORECASE):
                claimed_return = float(match.group(1)) / 100.0
                if not any(
                    value is not None
                    and isclose(claimed_return, value, rel_tol=0.05, abs_tol=0.05)
                    for value in allowed_returns
                ):
                    raise StockAnalysisValidationError(
                        "prose upside claim "
                        f"{claimed_return:.4f} does not match deterministic forward DCF "
                        f"returns {allowed_returns} within rounding tolerance"
                    )

    @staticmethod
    def _same_number(actual, expected):
        return (
            actual is not None
            and expected is not None
            and isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-6)
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
        forward_scenarios = cls._field(reverse_dcf, "forward_scenarios") or {}
        scenarios = {}
        for label, scenario in forward_scenarios.items():
            assumptions = cls._field(scenario, "assumptions")
            scenarios[label] = {
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
                    )
                },
                "source_id": (
                    cls._field(scenario, "source_id")
                    or f"valuation:forward_dcf:{label}"
                ),
                "assumption_sources": cls._field(scenario, "assumption_sources") or {},
                "value_per_share": cls._field(scenario, "value_per_share"),
                "expected_return": cls._field(scenario, "expected_return"),
                "terminal_value_share": cls._field(scenario, "terminal_value_share"),
            }
        return {
            "status": cls._field(reverse_dcf, "status"),
            "reverse_dcf_policy_version": cls._field(reverse_dcf, "policy_version"),
            "forward_dcf_policy_version": cls._field(
                reverse_dcf, "forward_policy_version"
            ),
            "price_date": cls._field(reverse_dcf, "price_date"),
            "current_price": cls._field(reverse_dcf, "current_price"),
            "scenarios": scenarios,
            "warnings": list(cls._field(reverse_dcf, "warnings") or []),
        }

    @classmethod
    def _valuation_source_aliases(cls, candidate):
        reverse_dcf = candidate.full_results.get("reverse_dcf")
        if reverse_dcf is None:
            return {}
        aliases = {}
        forward_scenarios = cls._field(reverse_dcf, "forward_scenarios") or {}
        for label, scenario in forward_scenarios.items():
            source_id = cls._field(scenario, "source_id") or f"valuation:forward_dcf:{label}"
            aliases[source_id] = source_id
            aliases[f"full_results.reverse_dcf.forward_scenarios.{label}"] = source_id
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
        return aliases

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
        forward_scenarios = AgentExecutionBoundary._field(
            reverse_dcf, "forward_scenarios"
        )
        if status != "available" or not forward_scenarios:
            raise StockAnalysisValidationError(
                "activated_case requires deterministic forward valuation scenarios"
            )
