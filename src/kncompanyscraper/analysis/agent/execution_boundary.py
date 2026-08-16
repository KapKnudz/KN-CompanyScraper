from dataclasses import dataclass, fields, is_dataclass
from datetime import date
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
    VALIDATION_VERSION = "agent-boundary-v12"
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
        document_source_ids.update(
            candidate.research_evidence.get("prior_document_source_ids", [])
        )
        insider_source_ids.update(
            candidate.research_evidence.get("prior_insider_source_ids", [])
        )
        prior_source_ids = set(candidate.research_evidence.get("prior_source_ids", []))
        valuation_source_aliases = {
            **self._deterministic_source_aliases(candidate),
            **self._valuation_source_aliases(candidate),
            "research_evidence.insider_event_count": "research:insider_event_count",
            "research_evidence.insider_status": "research:insider_status",
        }
        for citation in result.citations:
            citation.source_id = valuation_source_aliases.get(
                citation.source_id, citation.source_id
            )
        result.risk_profile_evidence = [
            valuation_source_aliases.get(source_id, source_id)
            for source_id in result.risk_profile_evidence
        ]
        fact_source_ids = set()
        seen_facts = set()
        for heading_field in fields(result.company_fact_ledger):
            heading = heading_field.name
            for fact in getattr(result.company_fact_ledger, heading):
                fact.statement = fact.statement.strip()
                if not fact.statement:
                    raise StockAnalysisValidationError(
                        f"company fact statement cannot be empty: {heading}"
                    )
                if not fact.source_ids:
                    raise StockAnalysisValidationError(
                        f"company fact must cite evidence: {heading}"
                    )
                fact.source_ids = [
                    valuation_source_aliases.get(source_id, source_id)
                    for source_id in fact.source_ids
                ]
                if len(fact.source_ids) != len(set(fact.source_ids)):
                    raise StockAnalysisValidationError(
                        f"company fact contains duplicate source IDs: {heading}"
                    )
                if fact.source_date is not None:
                    try:
                        date.fromisoformat(fact.source_date)
                    except ValueError as exc:
                        raise StockAnalysisValidationError(
                            f"company fact source_date must be an ISO date: {heading}"
                        ) from exc
                fact_key = (heading, fact.statement.casefold())
                if fact_key in seen_facts:
                    raise StockAnalysisValidationError(
                        f"duplicate company fact: {heading}: {fact.statement}"
                    )
                seen_facts.add(fact_key)
                fact_source_ids.update(fact.source_ids)
        known_source_ids = (
            document_source_ids
            | insider_source_ids
            | prior_source_ids
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
        unknown_fact_source_ids = sorted(fact_source_ids - known_source_ids)
        if unknown_fact_source_ids:
            raise StockAnalysisValidationError(
                "company facts cite unknown evidence source(s): "
                + ", ".join(unknown_fact_source_ids)
            )

        deterministic_checks, deterministic_warnings = self._validate_model_owned_arithmetic(
            result, candidate
        )
        self._validate_scenario_characterization(result)
        self._validate_management_sources(result, document_source_ids)
        self._validate_activated_case(result, candidate)
        self._validate_portfolio_eligibility(result)
        self._validate_risk_profile(result, candidate)
        self._validate_reverse_dcf_assessment(result, candidate)
        confidence_checks = self._apply_confidence_cap(result, candidate, document_source_ids)

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
                "confidence_checks": confidence_checks,
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
    def _apply_confidence_cap(cls, result, candidate, document_source_ids):
        cap = "high"
        limitations = []
        reverse_dcf = candidate.full_results.get("reverse_dcf")

        if not document_source_ids:
            cap = "low"
            limitations.append("No textual company reports or releases were supplied.")
        else:
            if result.missing_information:
                cap = "medium"
                limitations.append("Material information remains missing.")
            if (
                cls._field(reverse_dcf, "status") != "available"
                or not (cls._field(reverse_dcf, "expectation_curve") or ())
            ):
                cap = "medium"
                limitations.append("Reverse-DCF expectations are unavailable or incomplete.")
            if result.risk_profile == "unclassified":
                cap = "medium"
                limitations.append("The business-risk profile is unclassified.")

        confidence_rank = {"low": 0, "medium": 1, "high": 2}
        proposed = result.confidence
        if confidence_rank[proposed] > confidence_rank[cap]:
            result.confidence = cap
        result.confidence_limitations = list(
            dict.fromkeys([*result.confidence_limitations, *limitations])
        )
        return [
            f"model proposed {proposed} confidence",
            f"deterministic confidence cap is {cap}",
            f"accepted confidence is {result.confidence}",
        ]

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

    @classmethod
    def _validate_reverse_dcf_assessment(cls, result, candidate):
        rationale = result.reverse_dcf_expectation_rationale.strip()
        if not rationale:
            raise StockAnalysisValidationError(
                "reverse-DCF expectation assessment requires a rationale"
            )
        if re.search(
            r"\b(?:reverse[- ]?dcf\s+)?score\b|\b\d+(?:\.\d+)?\s*/\s*100\b",
            rationale,
            re.IGNORECASE,
        ):
            raise StockAnalysisValidationError(
                "reverse-DCF expectation assessment cannot use a numerical score"
            )

        reverse_dcf = candidate.full_results.get("reverse_dcf")
        status = cls._field(reverse_dcf, "status")
        expectation_curve = cls._field(reverse_dcf, "expectation_curve") or ()
        if status != "available" or not expectation_curve:
            if result.reverse_dcf_expectation_assessment != "unassessable":
                raise StockAnalysisValidationError(
                    "unavailable reverse DCF must be assessed as unassessable"
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
                    "revenue_growth_fade_to",
                    "ebit_margin_start",
                )
            },
            "assumption_sources": cls._field(reverse_dcf, "assumption_sources") or {},
            "normalized_fcf_margin": cls._field(
                reverse_dcf, "normalized_fcf_margin"
            ),
            "normalization": cls._serialize_normalization(normalization),
            "operating_history": cls._serialize_operating_history(
                cls._field(reverse_dcf, "operating_history")
            ),
            "price_fundamental_attribution": [
                {
                    name: cls._field(period, name)
                    for name in (
                        "years",
                        "start_price_date",
                        "end_price_date",
                        "start_report_year",
                        "end_report_year",
                        "price_return",
                        "annualized_price_return",
                        "annualized_revenue_growth",
                        "annualized_ebit_growth",
                        "annualized_net_income_growth",
                        "annualized_eps_growth",
                        "ebit_margin_change",
                        "share_count_change",
                        "pe_change",
                    )
                }
                for period in cls._field(
                    reverse_dcf, "price_fundamental_attribution"
                ) or ()
            ],
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
    def _serialize_operating_history(cls, history):
        if history is None:
            return None
        return {
            "annuals": [
                {
                    name: cls._field(point, name)
                    for name in ("year", "revenue_growth", "ebit_margin")
                }
                for point in cls._field(history, "annuals") or ()
            ],
            **{
                name: cls._field(history, name)
                for name in (
                    "three_year_revenue_cagr",
                    "five_year_revenue_cagr",
                    "three_year_average_ebit_margin",
                    "five_year_average_ebit_margin",
                    "peak_ebit_margin",
                    "peak_ebit_margin_year",
                )
            },
        }

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
        consensus = candidate.full_results.get("cyclicality_consensus") or {}
        if cls._field(consensus, "status") != "complete":
            if result.risk_profile != "unclassified" or result.risk_profile_evidence:
                raise StockAnalysisValidationError(
                    "model-selected risk profiles require a completed classifier consensus"
                )
            return

        expected_profile = cls._field(consensus, "risk_profile")
        expected_confidence = (
            "high"
            if cls._field(consensus, "consensus_strength") == "unanimous"
            else "medium"
        )
        evidence = cls._field(consensus, "evidence") or ()
        expected_evidence = {
            cls._field(item, "source_id")
            for item in evidence
            if cls._field(item, "source_id")
        }
        if result.risk_profile != expected_profile:
            raise StockAnalysisValidationError(
                "risk profile must match the completed classifier consensus"
            )
        if result.risk_profile_confidence != expected_confidence:
            raise StockAnalysisValidationError(
                "risk profile confidence must match classifier consensus strength"
            )
        if set(result.risk_profile_evidence) != expected_evidence:
            raise StockAnalysisValidationError(
                "risk profile evidence must match classifier consensus evidence"
            )

        reverse_dcf = candidate.full_results.get("reverse_dcf")
        sensitivities = cls._field(reverse_dcf, "discount_rate_sensitivities") or {}
        if (
            cls._field(reverse_dcf, "status") == "available"
            and expected_profile not in sensitivities
        ):
            raise StockAnalysisValidationError(
                "classifier consensus has no matching deterministic discount-rate sensitivity"
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
        reverse_dcf = candidate.full_results.get("reverse_dcf")
        if cls._field(reverse_dcf, "normalization") is not None:
            source_id = "deterministic:reverse_dcf:normalization"
            aliases[source_id] = source_id
            aliases["full_results.reverse_dcf.normalization"] = source_id
        if cls._field(reverse_dcf, "operating_history") is not None:
            source_id = "deterministic:reverse_dcf:operating_history"
            aliases[source_id] = source_id
            aliases["full_results.reverse_dcf.operating_history"] = source_id
        if cls._field(reverse_dcf, "price_fundamental_attribution") is not None:
            source_id = "deterministic:reverse_dcf:price_fundamental_attribution"
            aliases[source_id] = source_id
            aliases[
                "full_results.reverse_dcf.price_fundamental_attribution"
            ] = source_id
        if cls._field(reverse_dcf, "missing_information") is not None:
            source_id = "deterministic:reverse_dcf:missing_information"
            aliases[source_id] = source_id
            aliases["full_results.reverse_dcf.missing_information"] = source_id
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
    def _validate_portfolio_eligibility(result):
        if result.portfolio_eligibility == "investable":
            if result.verdict != "activated_case":
                raise StockAnalysisValidationError(
                    "investable portfolio eligibility requires activated_case verdict"
                )
            if result.portfolio_reason_code != "investable":
                raise StockAnalysisValidationError(
                    "investable portfolio eligibility requires investable reason code"
                )
            if result.reconsideration_trigger is not None:
                raise StockAnalysisValidationError(
                    "investable cases cannot have a reconsideration trigger"
                )
            return

        if result.portfolio_reason_code == "investable":
            raise StockAnalysisValidationError(
                "not_investable portfolio eligibility requires an exclusion reason"
            )
        if (
            result.portfolio_reason_code in {"valuation_only", "thesis_not_activated"}
            and not (result.reconsideration_trigger or "").strip()
        ):
            raise StockAnalysisValidationError(
                "reconsiderable portfolio exclusions require a trigger"
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
