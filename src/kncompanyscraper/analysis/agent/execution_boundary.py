from dataclasses import asdict, dataclass, fields, replace
from datetime import date
from math import isfinite
import re

from kncompanyscraper.analysis.agent.result_parser import (
    StockAnalysisValidationError,
    parse_qualitative_stock_analysis_result,
    parse_stock_analysis_result,
)
from kncompanyscraper.analysis.agent.agent_packet import (
    SourcePathError,
    build_evidence_catalog,
    resolve_source_id,
)
from kncompanyscraper.analysis.agent.output_schema import (
    MissingInformationItem,
    OwnershipClaim,
    StockAnalysisResult,
)
from kncompanyscraper.analysis.agent.conclusion_contract import (
    ownership_field,
    ownership_source_ids_for_measure,
    packet_value,
    render_ownership_claims,
    NO_OWNERSHIP_LIQUIDITY_ASSESSMENT as NO_OWNERSHIP_LIQUIDITY_ASSESSMENT_TEXT,
)
from kncompanyscraper.analysis.agent.historical_forecast_table import (
    build_historical_forecast_table,
)
from kncompanyscraper.analysis.agent.peak_margin_bridge import (
    build_peak_margin_bridge,
)
from kncompanyscraper.analysis.agent.scenario_driver_attribution import (
    build_scenario_driver_attribution,
)
from kncompanyscraper.analysis.valuation.forward_scenario import (
    ForwardScenarioEngine,
    ForwardScenarioInputs,
)
from kncompanyscraper.analysis.policy_versions import (
    THESIS_CALIBRATION_POLICY_VERSION,
    VERDICT_COHERENCE_POLICY_VERSION,
)


@dataclass(frozen=True)
class PersistedStockAnalysis:
    analysis_id: int
    result: StockAnalysisResult


class AgentExecutionBoundary:
    VALIDATION_VERSION = "agent-boundary-v23-ownership-source-contract"
    VERDICT_POLICY_VERSION = VERDICT_COHERENCE_POLICY_VERSION
    NO_OWNERSHIP_LIQUIDITY_ASSESSMENT = NO_OWNERSHIP_LIQUIDITY_ASSESSMENT_TEXT
    NO_INSIDER_ASSESSMENT = (
        "No insider transactions are available for the selected period. "
        "No inference can be made from their absence."
    )

    def __init__(self, analysis_repository, *, require_mandatory_scenarios=False):
        self.analysis_repository = analysis_repository
        self.require_mandatory_scenarios = require_mandatory_scenarios

    def persist_response(
        self,
        raw_response: str,
        candidate,
        created_by: str,
        metadata: dict | None = None,
    ) -> PersistedStockAnalysis:
        result = self.validate_response(raw_response, candidate)
        return self.persist_validated_result(result, candidate, created_by, metadata)

    def validate_qualitative_response(
        self, raw_response: str, candidate
    ) -> StockAnalysisResult:
        """Validate the qualitative stage without scenario calculation or persistence."""
        result = parse_qualitative_stock_analysis_result(raw_response)
        self._validate_identity(result, candidate)
        self._raise_qualitative_validation_violations(result, candidate)
        return self._persist_validated_response(
            result,
            candidate,
            created_by="",
            metadata=None,
            include_scenarios=False,
            persist=False,
        )

    def _raise_qualitative_validation_violations(self, result, candidate):
        """Report independent semantic violations in one repairable response."""
        research_evidence = candidate.research_evidence
        document_source_ids = {
            source.get("source_id")
            for source in research_evidence.get("documents", [])
        }
        document_source_ids.update(
            research_evidence.get("prior_document_source_ids", [])
        )
        insider_source_ids = {
            source.get("source_id")
            for source in research_evidence.get("insider_transactions", [])
        }
        insider_source_ids.update(
            research_evidence.get("prior_insider_source_ids", [])
        )
        ownership_liquidity = research_evidence.get("ownership_liquidity", {})
        ownership_liquidity_source_ids = set(
            ownership_liquidity.get("source_ids", [])
        )
        evidence_catalog = build_evidence_catalog(
            candidate.full_results, research_evidence
        )
        result.management_credibility_ledger = [
            claim
            for claim in result.management_credibility_ledger
            if not (
                set(claim.claim_source_ids or claim.source_ids)
                | set(claim.outcome_source_ids)
            )
            or (
                set(claim.claim_source_ids or claim.source_ids)
                | set(claim.outcome_source_ids)
            ).issubset(document_source_ids)
        ]

        checks = (
            lambda: self._validate_thesis_card(result, candidate, evidence_catalog),
            lambda: self._validate_model_owned_arithmetic(result, candidate),
            lambda: self._validate_scenario_characterization(result),
            lambda: self._validate_management_ledger(result),
            lambda: self._validate_management_sources(result, document_source_ids),
            lambda: self._validate_assessment_sections(
                result,
                document_source_ids=document_source_ids,
                insider_source_ids=insider_source_ids,
                ownership_liquidity_source_ids=ownership_liquidity_source_ids,
                ownership_liquidity=ownership_liquidity,
            ),
            lambda: self._validate_activated_case(result, candidate),
            lambda: self._validate_revenue_resilience(result),
            lambda: self._validate_reverse_dcf_assessment(result, candidate),
            lambda: self._validate_portfolio_eligibility(
                result, require_scenario=False
            ),
        )
        violations = []
        for check in checks:
            try:
                check()
            except StockAnalysisValidationError as exc:
                violations.extend(getattr(exc, "violations", (str(exc),)))
        _raise_validation_violations(violations)

    @classmethod
    def validate_response(cls, raw_response: str, candidate) -> StockAnalysisResult:
        """Parse and validate a complete result before persistence-side normalization."""
        result = parse_stock_analysis_result(raw_response)
        cls._validate_identity(result, candidate)
        return result

    @staticmethod
    def _validate_identity(result: StockAnalysisResult, candidate) -> None:
        if result.company_id != candidate.company_id:
            raise StockAnalysisValidationError(
                f"result.company_id {result.company_id} does not match candidate {candidate.company_id}"
            )
        if result.ticker.strip().upper() != candidate.ticker.strip().upper():
            raise StockAnalysisValidationError(
                f"result.ticker {result.ticker!r} does not match candidate {candidate.ticker!r}"
            )
        if result.analysis_status != "complete":
            raise StockAnalysisValidationError(
                "model-backed analysis_status must be complete; blocked packets belong "
                "to the deterministic readiness output"
            )
    def persist_validated_result(
        self,
        result: StockAnalysisResult,
        candidate,
        created_by: str,
        metadata: dict | None = None,
    ) -> PersistedStockAnalysis:
        """Validate and persist a result after all model stages have completed."""
        self._validate_identity(result, candidate)
        return self._persist_validated_response(result, candidate, created_by, metadata)

    def _persist_validated_response(
        self,
        result: StockAnalysisResult,
        candidate,
        created_by: str,
        metadata: dict | None,
        *,
        include_scenarios: bool = True,
        persist: bool = True,
    ) -> PersistedStockAnalysis:

        document_source_ids = {
            source.get("source_id")
            for source in candidate.research_evidence.get("documents", [])
        }
        insider_source_ids = {
            source.get("source_id")
            for source in candidate.research_evidence.get("insider_transactions", [])
        }
        ownership_liquidity_source_ids = set(
            candidate.research_evidence.get("ownership_liquidity", {}).get(
                "source_ids", []
            )
        )
        document_source_ids.update(
            candidate.research_evidence.get("prior_document_source_ids", [])
        )
        insider_source_ids.update(
            candidate.research_evidence.get("prior_insider_source_ids", [])
        )
        prior_source_ids = set(candidate.research_evidence.get("prior_source_ids", []))
        evidence_catalog = build_evidence_catalog(
            candidate.full_results, candidate.research_evidence
        )
        self._merge_missing_information(
            result,
            candidate.research_evidence.get("missing_information", []),
        )
        for citation in result.citations:
            citation.source_id = self._resolve_source_alias(
                citation.source_id,
                evidence_catalog,
                candidate.full_results,
                candidate.research_evidence,
            )
        self._normalize_assessment_claims(
            result.management_claims,
            evidence_catalog,
            candidate.full_results,
            candidate.research_evidence,
        )
        self._normalize_assessment_claims(
            result.insider_claims,
            evidence_catalog,
            candidate.full_results,
            candidate.research_evidence,
        )
        resilience_source_ids = [
            self._resolve_source_alias(
                source_id,
                evidence_catalog,
                candidate.full_results,
                candidate.research_evidence,
            )
            for source_id in result.revenue_resilience.source_ids
        ]
        recurring_source_ids = [
            self._resolve_source_alias(
                source_id,
                evidence_catalog,
                candidate.full_results,
                candidate.research_evidence,
            )
            for source_id in result.revenue_resilience.recurring_source_ids
        ]
        variable_source_ids = [
            self._resolve_source_alias(
                source_id,
                evidence_catalog,
                candidate.full_results,
                candidate.research_evidence,
            )
            for source_id in result.revenue_resilience.variable_source_ids
        ]
        result.revenue_resilience.recurring_source_ids = list(
            dict.fromkeys(recurring_source_ids)
        )
        result.revenue_resilience.variable_source_ids = list(
            dict.fromkeys(variable_source_ids)
        )
        result.revenue_resilience.source_ids = list(
            dict.fromkeys(
                [
                    *resilience_source_ids,
                    *result.revenue_resilience.recurring_source_ids,
                    *result.revenue_resilience.variable_source_ids,
                ]
            )
        )
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
                if len(fact.source_ids) != len(set(fact.source_ids)):
                    raise StockAnalysisValidationError(
                        f"company fact contains duplicate source IDs: {heading}"
                    )
                fact.source_ids = list(
                    dict.fromkeys(
                        self._resolve_source_alias(
                            source_id,
                            evidence_catalog,
                            candidate.full_results,
                            candidate.research_evidence,
                        )
                        for source_id in fact.source_ids
                    )
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
        thesis_card_source_ids = self._validate_thesis_card(
            result,
            candidate,
            evidence_catalog,
        )
        known_source_ids = (
            document_source_ids
            | insider_source_ids
            | ownership_liquidity_source_ids
            | prior_source_ids
            | set(evidence_catalog["canonical_source_ids"])
        )
        if include_scenarios:
            forward_source_ids = self.validate_forward_scenario_sources(
                result,
                candidate,
                source_aliases=evidence_catalog,
                known_source_ids=known_source_ids,
            )
        else:
            forward_source_ids = set()
        structured_source_ids = self._validate_structured_conclusions(result)
        # Ownership structural diagnostics must precede the generic catalog
        # check so repair feedback retains the exact offending claim.
        self._validate_assessment_sections(
            result,
            document_source_ids=document_source_ids,
            insider_source_ids=insider_source_ids,
            ownership_liquidity_source_ids=ownership_liquidity_source_ids,
            ownership_liquidity=candidate.research_evidence.get(
                "ownership_liquidity", {}
            ),
        )
        self._validate_known_sources(
            known_source_ids,
            (
                (
                    "result cites unknown evidence source(s)",
                    {citation.source_id for citation in result.citations},
                ),
                (
                    "revenue resilience cites unknown evidence source(s)",
                    set(result.revenue_resilience.source_ids),
                ),
                ("company facts cite unknown evidence source(s)", fact_source_ids),
                ("thesis card cites unknown evidence source(s)", thesis_card_source_ids),
                ("forward assumptions cite unknown evidence source(s)", forward_source_ids),
                (
                    "management claims cite unknown evidence source(s)",
                    {
                        source_id
                        for claim in result.management_claims
                        for source_id in claim.source_ids
                    },
                ),
                (
                    "ownership claims cite unknown evidence source(s)",
                    {
                        source_id
                        for claim in result.ownership_claims
                        for source_id in (
                            claim.binding.source_ids
                            if isinstance(claim, OwnershipClaim)
                            else claim.source_ids
                        )
                    },
                ),
                (
                    "insider claims cite unknown evidence source(s)",
                    {
                        source_id
                        for claim in result.insider_claims
                        for source_id in claim.source_ids
                    },
                ),
                (
                    "structured conclusions cite unknown evidence source(s)",
                    structured_source_ids,
                ),
            ),
        )

        deterministic_checks, deterministic_warnings = self._validate_model_owned_arithmetic(
            result, candidate
        )
        self._validate_scenario_characterization(result)
        result.management_credibility_ledger = [
            claim
            for claim in result.management_credibility_ledger
            if not (
                set(claim.claim_source_ids or claim.source_ids)
                | set(claim.outcome_source_ids)
            )
            or (
                set(claim.claim_source_ids or claim.source_ids)
                | set(claim.outcome_source_ids)
            ).issubset(document_source_ids)
        ]
        management_coverage = self._validate_management_ledger(result)
        if management_coverage["omitted_claim_count"]:
            self._merge_missing_information(
                result,
                [
                    "Eligible management claims were omitted from the credibility ledger"
                ],
                impacts={
                    "Eligible management claims were omitted from the credibility ledger": (
                        "supplemental",
                        "The supplied narrative history does not support a complete ledger of all eligible testable management claims.",
                    )
                },
            )
        self._validate_management_sources(result, document_source_ids)
        # Preserve the fast, legacy diagnostic for missing reverse-DCF inputs;
        # the full verdict matrix runs below after forward scenarios exist.
        self._validate_activated_case(result, candidate)
        self._validate_revenue_resilience(result)
        self._validate_reverse_dcf_assessment(result, candidate)
        if include_scenarios:
            result.forward_scenario_analysis = self.calculate_forward_scenario(
                result, candidate
            )
            result.historical_forecast_table = build_historical_forecast_table(
                candidate,
                result,
                result.forward_scenario_analysis,
            )
            result.peak_margin_bridge = build_peak_margin_bridge(candidate, result)
            result.scenario_driver_attribution = build_scenario_driver_attribution(
                candidate, result
            )
            if result.scenario_bundles:
                deterministic_limitations = [
                    *(
                        result.historical_forecast_table.get("limitations", [])
                        if result.historical_forecast_table
                        else []
                    ),
                    *(
                        result.peak_margin_bridge.get("limitations", [])
                        if result.peak_margin_bridge
                        else []
                    ),
                ]
                self._merge_missing_information(result, deterministic_limitations)
        else:
            result.forward_scenario_analysis = None
            result.historical_forecast_table = None
            result.peak_margin_bridge = None
            result.scenario_driver_attribution = None
        if include_scenarios and self.require_mandatory_scenarios:
            self._require_completed_forward_scenario(result, candidate)
        reconciliation_limitations = self._financial_reconciliation_limitations(candidate)
        result.confidence_limitations = list(
            dict.fromkeys([*result.confidence_limitations, *reconciliation_limitations])
        )
        coherence_checks = self._validate_verdict_coherence(
            result,
            candidate,
            require_forward_scenario=include_scenarios,
        )
        self._validate_portfolio_eligibility(result, require_scenario=include_scenarios)
        confidence_checks = self._apply_confidence_cap(
            result, candidate, document_source_ids
        )

        warnings = list(deterministic_warnings)
        ownership_checks = []
        if ownership_liquidity_source_ids:
            ownership_checks.append(
                "ownership/liquidity assessment uses supplied deterministic evidence "
                f"({len(ownership_liquidity_source_ids)} source IDs available)"
            )
            if result.ownership_claims and all(
                isinstance(claim, OwnershipClaim) for claim in result.ownership_claims
            ):
                result.ownership_and_flow_assessment = render_ownership_claims(
                    [
                        {
                            "measure": claim.measure,
                            "binding": {
                                "asserted_value": claim.binding.asserted_value
                            },
                        }
                        for claim in result.ownership_claims
                    ]
                )
        else:
            if (
                result.ownership_and_flow_assessment
                != self.NO_OWNERSHIP_LIQUIDITY_ASSESSMENT
            ):
                warnings.append(
                    "model ownership/liquidity assessment replaced because no evidence was supplied"
                )
            result.ownership_and_flow_assessment = (
                self.NO_OWNERSHIP_LIQUIDITY_ASSESSMENT
            )
            result.ownership_claims = []
            ownership_checks.append("no-data ownership/liquidity assessment normalized")

        insider_checks = []
        if insider_source_ids:
            cited_source_ids = {
                citation.source_id for citation in result.citations
            } | fact_source_ids | {
                source_id
                for claim in result.insider_claims
                for source_id in claim.source_ids
            }
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
            result.insider_claims = []
            insider_checks.append("no-data insider assessment normalized")

        validation_metadata = dict(metadata or {})
        valuation_provenance = self._valuation_provenance(candidate)
        if valuation_provenance is not None:
            validation_metadata["valuation_provenance"] = valuation_provenance
        required_return = self._selected_required_return(result, candidate)
        validation_metadata["forward_scenario"] = None
        if result.forward_scenario_analysis is not None:
            validation_metadata["forward_scenario"] = {
                "policy_version": result.forward_scenario_analysis.policy_version,
                "status": result.forward_scenario_analysis.status,
                "required_return": required_return,
                "methodology_flags": list(
                    result.forward_scenario_analysis.methodology_flags
                ),
                "warnings": list(result.forward_scenario_analysis.warnings),
                "net_debt_bridges": self._net_debt_bridges(result, candidate),
                "capital_allocation_limitations": [
                    warning
                    for warning in result.forward_scenario_analysis.warnings
                    if any(
                        term in warning.lower()
                        for term in ("net_debt", "share_count", "distribution")
                    )
                ],
            }
        validation_metadata["financial_reconciliation_limitations"] = (
            reconciliation_limitations
        )
        validation_metadata["management_credibility"] = management_coverage
        validation_metadata.update(
            {
                "artifact_type": "validated_analysis",
                "validation_version": self.VALIDATION_VERSION,
                "validation_status": "accepted",
                "analysis_status": result.analysis_status,
                "deterministic_value_checks": [
                    *deterministic_checks,
                    *(["forward scenario output recalculated from sourced bundles"]
                      if include_scenarios else []),
                ],
                "insider_checks": insider_checks,
                "ownership_liquidity_checks": ownership_checks,
                "confidence_checks": confidence_checks,
                "confidence_cap": self._confidence_cap_details(
                    result, candidate, document_source_ids
                ),
                "verdict_coherence": coherence_checks,
                "verdict_policy_version": self.VERDICT_POLICY_VERSION,
                "thesis_calibration_policy_version": THESIS_CALIBRATION_POLICY_VERSION,
                "warnings": warnings,
            }
        )

        if not persist:
            return result

        analysis_id = self.analysis_repository.save_stock_analysis(
            result,
            created_by=created_by,
            metadata=validation_metadata,
        )
        return PersistedStockAnalysis(analysis_id=analysis_id, result=result)

    @classmethod
    def calculate_forward_scenario(cls, result, candidate):
        return ForwardScenarioEngine().analyze(
            cls._forward_scenario_inputs(result, candidate)
        )

    @classmethod
    def validate_forward_scenario_sources(
        cls,
        result,
        candidate,
        *,
        source_aliases=None,
        known_source_ids=None,
        source_whitelist=None,
    ):
        strict_whitelist = source_whitelist is not None
        if strict_whitelist:
            source_aliases = {}
            known_source_ids = set(source_whitelist)
        elif source_aliases is None:
            source_aliases = build_evidence_catalog(
                candidate.full_results, candidate.research_evidence
            )
        if known_source_ids is None:
            known_source_ids = {
                source.get("source_id")
                for key in ("documents", "insider_transactions")
                for source in candidate.research_evidence.get(key, [])
            }
            known_source_ids.update(
                candidate.research_evidence.get("ownership_liquidity", {}).get(
                    "source_ids", []
                )
            )
            known_source_ids.update(
                candidate.research_evidence.get("prior_source_ids", [])
            )
            known_source_ids.update(
                candidate.research_evidence.get("prior_document_source_ids", [])
            )
            known_source_ids.update(
                candidate.research_evidence.get("prior_insider_source_ids", [])
            )
            known_source_ids.update(source_aliases["canonical_source_ids"])

        forward_source_ids = set()
        normalized_bundles = []
        for bundle in result.scenario_bundles:
            replacements = {}
            for name in (
                "revenue_cagr",
                "ebit_margin",
                "terminal_ev_ebit_low",
                "terminal_ev_ebit_high",
                "net_debt_change",
                "share_count_growth",
                "distributions_per_share",
            ):
                assumption = getattr(bundle, name)
                source_ids = tuple(
                    source_id
                    if strict_whitelist
                    else cls._resolve_source_alias(
                        source_id,
                        source_aliases,
                        candidate.full_results,
                        candidate.research_evidence,
                    )
                    for source_id in assumption.source_ids
                )
                forward_source_ids.update(source_ids)
                replacements[name] = replace(assumption, source_ids=source_ids)
            normalized_bundles.append(replace(bundle, **replacements))
        result.scenario_bundles = normalized_bundles
        cls._validate_known_sources(
            known_source_ids,
            (("forward assumptions cite unknown evidence source(s)", forward_source_ids),),
            strict=strict_whitelist,
        )
        return forward_source_ids

    @classmethod
    def _require_completed_forward_scenario(cls, result, candidate):
        if candidate.ranking_model != "general":
            return
        readiness = cls._forward_scenario_inputs(result, candidate)
        if ForwardScenarioEngine.assess_readiness(readiness).status != "required":
            return
        analysis = result.forward_scenario_analysis
        if (
            analysis is None
            or analysis.status != "available"
            or len(result.scenario_bundles) != 3
            or len(analysis.bands) != 3
        ):
            raise StockAnalysisValidationError(
                "completed general-company analyses require exactly three "
                "scenario bundles and three calculated bands"
            )

    @staticmethod
    def _validate_known_sources(known_source_ids, source_groups, *, strict=False) -> None:
        for label, source_ids in source_groups:
            # Generated deterministic IDs have already passed exact traversal
            # in _resolve_source_alias; they are intentionally not enumerated
            # in the compact catalog.
            unknown = sorted(set(source_ids) - known_source_ids)
            if not strict:
                unknown = [
                    source_id
                    for source_id in unknown
                    if not source_id.startswith("deterministic:")
                ]
            if unknown:
                raise StockAnalysisValidationError(
                    f"{label}: " + ", ".join(unknown)
                )

    @staticmethod
    def _merge_missing_information(result, items, *, impacts=None):
        """Keep packet and deterministic limitations visible in the card."""
        impacts = impacts or {}
        normalized_items = []
        seen_items = set()
        for item in items or ():
            if not isinstance(item, str):
                continue
            item = item.strip()
            if not item or item.casefold() in seen_items:
                continue
            normalized_items.append(item)
            seen_items.add(item.casefold())

        result.missing_information = list(result.missing_information or [])
        existing_keys = {
            item.casefold()
            for item in result.missing_information
            if isinstance(item, str)
        }
        for item in normalized_items:
            if item.casefold() not in existing_keys:
                result.missing_information.append(item)
                existing_keys.add(item.casefold())

        # Align legacy/detail casing and fill any detail omitted by an older
        # model response. New entries therefore cannot lose their impact class.
        detail_by_key = {}
        for detail in result.missing_information_details or []:
            key = detail.item.strip().casefold()
            matching_item = next(
                (
                    item
                    for item in result.missing_information
                    if isinstance(item, str) and item.casefold() == key
                ),
                detail.item.strip(),
            )
            detail.item = matching_item
            detail_by_key[key] = detail

        details = []
        for item in result.missing_information:
            if not isinstance(item, str) or not item.strip():
                continue
            item = item.strip()
            key = item.casefold()
            detail = detail_by_key.get(key)
            if detail is None:
                limitation_class, impact = impacts.get(
                    item,
                    AgentExecutionBoundary._default_missing_information_impact(item),
                )
                detail = MissingInformationItem(
                    item=item,
                    limitation_class=limitation_class,
                    impact=impact,
                )
            details.append(detail)
        result.missing_information = list(
            dict.fromkeys(
                item.strip()
                for item in result.missing_information
                if isinstance(item, str) and item.strip()
            )
        )
        result.missing_information_details = details

    @staticmethod
    def _default_missing_information_impact(item):
        lowered = item.casefold()
        core_markers = (
            "no textual company reports",
            "no dated annual report",
            "broken fiscal year",
            "comparable prior-year interim",
            "historical table rows unavailable",
            "cash-flow normalization",
            "current r12",
        )
        if any(marker in lowered for marker in core_markers):
            return (
                "core",
                "This missing input can affect the fundamental company conclusion.",
            )
        return (
            "supplemental",
            "This missing input limits context but does not by itself establish a broken fundamental case.",
        )

    @classmethod
    def _apply_confidence_cap(cls, result, candidate, document_source_ids):
        details = cls._confidence_cap_details(result, candidate, document_source_ids)
        cap = details["cap"]
        limitations = details["reasons"]

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
    def _confidence_cap_details(cls, result, candidate, document_source_ids):
        cap = "high"
        reasons = []
        reverse_dcf = candidate.full_results.get("reverse_dcf")

        if not document_source_ids:
            cap = "low"
            reasons.append("No textual company reports or releases were supplied.")
        else:
            core_limitations = [
                item.item
                for item in result.missing_information_details
                if item.limitation_class == "core"
            ]
            legacy_missing_information = bool(
                result.missing_information and not result.missing_information_details
            )
            if core_limitations or legacy_missing_information:
                cap = "medium"
                reasons.append(
                    "Unresolved core information remains missing."
                    if core_limitations
                    else "Legacy missing-information entries have no materiality class."
                )
            if (
                cls._field(reverse_dcf, "status") != "available"
                or not (cls._field(reverse_dcf, "expectation_curve") or ())
            ):
                cap = "medium"
                reasons.append("Reverse-DCF expectations are unavailable or incomplete.")
            normalization = cls._field(reverse_dcf, "normalization")
            if cls._field(normalization, "confidence") == "low":
                cap = "medium"
                reasons.append("Cash-flow normalization confidence is low.")
            if (
                result.forward_scenario_analysis is not None
                and result.forward_scenario_analysis.status != "available"
            ):
                cap = "medium"
                reasons.append(
                    "Forward scenario evidence is insufficient or the method is unsupported."
                )
        return {
            "cap": cap,
            "reasons": list(dict.fromkeys(reasons)),
            "core_limitation_items": [
                item.item
                for item in result.missing_information_details
                if item.limitation_class == "core"
            ],
            "supplemental_limitation_items": [
                item.item
                for item in result.missing_information_details
                if item.limitation_class == "supplemental"
            ],
            "accepted_confidence": result.confidence,
        }

    @classmethod
    def _validate_thesis_card(cls, result, candidate, source_aliases):
        evidence_as_of = candidate.research_evidence.get("as_of")
        if result.evidence_as_of is not None:
            try:
                date.fromisoformat(result.evidence_as_of)
            except ValueError as exc:
                raise StockAnalysisValidationError(
                    "evidence_as_of must be an ISO date"
                ) from exc
        if evidence_as_of and result.evidence_as_of != evidence_as_of:
            raise StockAnalysisValidationError(
                "evidence_as_of must match the supplied research evidence cutoff"
            )

        timing_horizon = result.timing_assessment.horizon_months
        if (
            timing_horizon is not None
            and result.case_horizon_months is not None
            and timing_horizon != result.case_horizon_months
        ):
            raise StockAnalysisValidationError(
                "timing horizon must match case_horizon_months"
            )

        def normalize(source_ids):
            normalized = [
                cls._resolve_source_alias(
                    source_id,
                    source_aliases,
                    candidate.full_results,
                    candidate.research_evidence,
                )
                for source_id in source_ids
            ]
            if len(normalized) != len(set(normalized)):
                raise StockAnalysisValidationError(
                    "thesis card contains duplicate source IDs"
                )
            return normalized

        falsifiable = result.falsifiable_case
        falsifiable.statement = falsifiable.statement.strip()
        falsifiable.falsification_test = falsifiable.falsification_test.strip()
        falsifiable.source_ids = normalize(falsifiable.source_ids)
        if (
            falsifiable.statement
            and falsifiable.statement != result.one_sentence_thesis.strip()
        ):
            raise StockAnalysisValidationError(
                "falsifiable_case.statement must match one_sentence_thesis"
            )
        if (
            falsifiable.horizon_months is not None
            and result.case_horizon_months is not None
            and falsifiable.horizon_months != result.case_horizon_months
        ):
            raise StockAnalysisValidationError(
                "falsifiable-case horizon must match case_horizon_months"
            )
        if falsifiable.falsification_test and not falsifiable.source_ids:
            raise StockAnalysisValidationError(
                "falsifiable case must cite evidence"
            )

        decisive_source_ids = set()
        for label, evidence in (
            ("strongest confirming evidence", result.strongest_confirming_evidence),
            ("strongest disconfirming evidence", result.strongest_disconfirming_evidence),
        ):
            if evidence is None:
                continue
            evidence.statement = evidence.statement.strip()
            evidence.why_it_matters = evidence.why_it_matters.strip()
            evidence.source_ids = normalize(evidence.source_ids)
            if not evidence.statement or not evidence.why_it_matters:
                raise StockAnalysisValidationError(
                    f"{label} requires a statement and why_it_matters"
                )
            if not evidence.source_ids:
                raise StockAnalysisValidationError(f"{label} must cite evidence")
            decisive_source_ids.update(evidence.source_ids)

        break_types = set()
        break_source_ids = set()
        allowed_break_types = {
            "revenue_or_demand",
            "margin_or_execution",
            "balance_sheet_or_dilution",
            "management_credibility",
            "valuation_overshoot",
            "superior_evidence_or_opportunity",
        }
        for test in result.thesis_break_tests:
            fields_to_strip = (
                "condition",
                "observable_metric_or_event",
                "threshold_or_direction",
            )
            for field_name in fields_to_strip:
                setattr(test, field_name, getattr(test, field_name).strip())
            test.source_ids = normalize(test.source_ids)
            if test.break_type not in allowed_break_types:
                raise StockAnalysisValidationError(
                    f"unsupported thesis break type: {test.break_type}"
                )
            if test.break_type in break_types:
                raise StockAnalysisValidationError(
                    f"duplicate thesis break type: {test.break_type}"
                )
            if any(not getattr(test, field_name) for field_name in fields_to_strip):
                raise StockAnalysisValidationError(
                    "thesis break tests require a condition, observable, and threshold"
                )
            if not test.source_ids:
                raise StockAnalysisValidationError(
                    "thesis break tests must cite the evidence establishing the baseline"
                )
            break_types.add(test.break_type)
            break_source_ids.update(test.source_ids)

        profile = result.business_model_profile
        profile_fields = (
            "summary",
            "customer_and_need",
            "offering",
            "revenue_mechanics",
            "sales_and_distribution",
            "cost_structure",
            "reinvestment_requirements",
            "competitive_position",
            "key_dependencies",
        )
        for field_name in profile_fields:
            setattr(profile, field_name, getattr(profile, field_name).strip())
        profile.source_ids = normalize(profile.source_ids)
        if any(getattr(profile, field_name) for field_name in profile_fields) and not (
            profile.source_ids
        ):
            raise StockAnalysisValidationError(
                "business model profile must cite evidence"
            )

        margin = result.margin_expansion_case
        margin.mechanism = margin.mechanism.strip()
        margin.source_ids = normalize(margin.source_ids)
        margin.contrary_source_ids = normalize(margin.contrary_source_ids)
        if margin.status not in {"not_applicable", "unassessable"}:
            if not margin.mechanism or not margin.source_ids:
                raise StockAnalysisValidationError(
                    "an assessable margin-expansion case requires a mechanism and evidence"
                )

        timing = result.timing_assessment
        timing.why_now = timing.why_now.strip()
        timing.source_ids = normalize(timing.source_ids)
        if timing.why_now and not timing.source_ids:
            raise StockAnalysisValidationError(
                "timing assessment must cite evidence"
            )
        catalyst_source_ids = set()
        for catalyst in timing.catalysts:
            catalyst.description = catalyst.description.strip()
            catalyst.observable_confirmation = catalyst.observable_confirmation.strip()
            catalyst.source_ids = normalize(catalyst.source_ids)
            if not catalyst.description or not catalyst.observable_confirmation:
                raise StockAnalysisValidationError(
                    "each catalyst requires a description and observable confirmation"
                )
            if not catalyst.source_ids:
                raise StockAnalysisValidationError(
                    "each catalyst must cite evidence"
                )
            catalyst_source_ids.update(catalyst.source_ids)

        if result.verdict == "latent_case":
            if result.latent_case_type not in {"price", "operating"}:
                raise StockAnalysisValidationError(
                    "latent_case requires latent_case_type price or operating"
                )
            if not (result.activation_trigger or "").strip():
                raise StockAnalysisValidationError(
                    "latent_case requires one primary activation_trigger"
                )
            if result.activation_trigger_spec is None:
                raise StockAnalysisValidationError(
                    "latent_case requires activation_trigger_spec"
                )
            cls._validate_activation_trigger(result)
        elif result.latent_case_type is not None:
            raise StockAnalysisValidationError(
                "non-latent verdicts must have latent_case_type null"
            )
        elif result.activation_trigger_spec is not None:
            raise StockAnalysisValidationError(
                "non-latent verdicts cannot have activation_trigger_spec"
            )

        trigger_evidence_source_ids = set()
        for evidence in result.activation_trigger_evidence:
            evidence.evidence_item = evidence.evidence_item.strip()
            evidence.rationale = evidence.rationale.strip()
            evidence.source_ids = normalize(evidence.source_ids)
            if not evidence.evidence_item or not evidence.rationale:
                raise StockAnalysisValidationError(
                    "activation trigger evidence requires an item and rationale"
                )
            if not evidence.source_ids:
                raise StockAnalysisValidationError(
                    "activation trigger evidence requires source_ids"
                )
            trigger_evidence_source_ids.update(evidence.source_ids)

        if result.verdict == "activated_case" and result.activation_trigger:
            raise StockAnalysisValidationError(
                "activated_case cannot retain an unresolved activation_trigger"
            )

        missing_items = [item.strip() for item in result.missing_information]
        result.missing_information = list(dict.fromkeys(missing_items))
        detail_items = []
        for detail in result.missing_information_details:
            detail.item = detail.item.strip()
            detail.impact = detail.impact.strip()
            if not detail.item or not detail.impact:
                raise StockAnalysisValidationError(
                    "missing-information details require item and impact"
                )
            if detail.limitation_class not in {"core", "supplemental"}:
                raise StockAnalysisValidationError(
                    "missing-information details require core or supplemental class"
                )
            if detail.item in detail_items:
                raise StockAnalysisValidationError(
                    "missing-information details contain duplicate items"
                )
            detail_items.append(detail.item)
        if result.missing_information_details and set(detail_items) != set(
            result.missing_information
        ):
            raise StockAnalysisValidationError(
                "missing-information details must cover exactly missing_information"
            )

        return {
            *falsifiable.source_ids,
            *decisive_source_ids,
            *break_source_ids,
            *profile.source_ids,
            *margin.source_ids,
            *margin.contrary_source_ids,
            *timing.source_ids,
            *catalyst_source_ids,
            *trigger_evidence_source_ids,
        }

    @staticmethod
    def _validate_activation_trigger(result):
        spec = result.activation_trigger_spec
        fields = (
            spec.unresolved_claim,
            spec.observable_metric_or_event,
            spec.threshold_or_direction,
            spec.evidence_window,
            spec.observation_requirement,
        )
        if any(not isinstance(value, str) or not value.strip() for value in fields):
            raise StockAnalysisValidationError(
                "activation_trigger_spec requires all trigger definition fields"
            )
        vague = re.compile(
            r"\b(?:better results|more evidence|two strong reports|"
            r"wait for two reports|"
            r"generic evidence|more data)\b",
            re.IGNORECASE,
        )
        if vague.search(" ".join(fields)):
            raise StockAnalysisValidationError(
                "activation triggers must name a company-specific metric or event"
            )
        observable_text = spec.observable_metric_or_event
        if not re.search(
            r"\b(?:arr|mrr|revenue|sales|ebit|ebitda|gross margin|ebit margin|"
            r"free cash flow|operating cash flow|customer(?:s)?|churn|retention|"
            r"renewal|renewals|orders?|volume|share price|valuation|multiple|"
            r"net debt|working capital|backlog|bookings|margin)\b"
            r"|\bq[1-4]\b|\bfy\s*20\d{2}\b|%|[<>]=?",
            observable_text,
            re.IGNORECASE,
        ):
            raise StockAnalysisValidationError(
                "activation triggers must name a company-specific metric or event"
            )
        if result.latent_case_type == "operating" and re.search(
            r"\b(?:share price|valuation|multiple)\b",
            observable_text,
            re.IGNORECASE,
        ):
            raise StockAnalysisValidationError(
                "operating latent triggers must name an operating metric or event"
            )
        if not re.search(
            r"\b(?:above|below|at least|at most|no more than|maintain|maintains?|"
            r"remain|reaches?|exceeds?|replace|replaces?|renew|renews?|increase|"
            r"decrease|positive|negative|within|by|from|to)\b|[<>]=?|\d",
            spec.threshold_or_direction,
            re.IGNORECASE,
        ):
            raise StockAnalysisValidationError(
                "activation triggers must state a threshold or directional result"
            )
        if re.search(
            r"\b(?:indefinitely|forever|until further notice|future reports?|"
            r"ongoing reports?|another report(?:ing period)?|next reporting period|"
            r"future evidence)\b",
            spec.evidence_window,
            re.IGNORECASE,
        ):
            raise StockAnalysisValidationError(
                "activation trigger evidence_window must be bounded and non-rolling"
            )
        multi_observation = bool(
            re.search(
                r"\b(?:two|2|multiple|several|consecutive)\b|"
                r"\breports?\b.*\b(?:reports?|quarters?)\b|"
                r"\bq[1-4]\b.*\bq[1-4]\b",
                spec.evidence_window,
                re.IGNORECASE,
            )
        )
        if multi_observation and spec.single_observation_sufficient:
            raise StockAnalysisValidationError(
                "a multi-report activation trigger cannot claim one observation is sufficient"
            )
        if multi_observation and len(spec.observation_requirement.strip()) < 20:
            raise StockAnalysisValidationError(
                "multi-report activation triggers must explain the persistence risk tested"
            )
        if multi_observation and not re.search(
            r"\b(?:persist|durab|temporary|integration|replacement|replace|"
            r"margin|working[- ]capital|normalization|retention|churn|acquisition|"
            r"customer|baseline|recheck|one observation|single observation|quarter)\w*\b",
            spec.observation_requirement,
            re.IGNORECASE,
        ):
            raise StockAnalysisValidationError(
                "multi-report activation triggers must name the persistence risk tested"
            )

    @classmethod
    def _validate_model_owned_arithmetic(cls, result, candidate):
        cls._validate_prose_upside(result)
        return ["forward scenario values are calculated at the execution boundary"], []

    @classmethod
    def _forward_scenario_inputs(cls, result, candidate):
        reverse_dcf = candidate.full_results.get("reverse_dcf")
        valuation = candidate.full_results.get("valuation")
        operating_history = cls._field(reverse_dcf, "operating_history")
        assumptions = cls._field(reverse_dcf, "assumptions")
        current_multiple = cls._field(valuation, "raw_ev_ebit") or cls._field(
            valuation, "ev_ebit"
        )
        base_ceiling = cls._field(valuation, "ev_ebit_base_ceiling")
        bull_ceiling = cls._field(valuation, "ev_ebit_bull_ceiling")
        historical_high = cls._field(valuation, "ev_ebit_guardrail_high")
        if base_ceiling is None:
            base_ceiling = historical_high
        if bull_ceiling is None:
            bull_ceiling = historical_high
        if current_multiple is not None:
            base_ceiling = max(current_multiple, base_ceiling or current_multiple)
            bull_ceiling = max(current_multiple, bull_ceiling or current_multiple)

        annual_growth = [
            cls._field(point, "revenue_growth")
            for point in (cls._field(operating_history, "annuals") or ())
        ]
        demonstrated_growth = cls._max_number(
            *annual_growth,
            cls._field(operating_history, "three_year_revenue_cagr"),
            cls._field(operating_history, "five_year_revenue_cagr"),
        )
        demonstrated_margin = cls._max_number(
            cls._field(operating_history, "peak_ebit_margin"),
            cls._field(assumptions, "ebit_margin_start"),
        )
        return ForwardScenarioInputs(
            current_price=cls._field(reverse_dcf, "current_price"),
            current_revenue=cls._field(reverse_dcf, "current_revenue"),
            current_shares=cls._field(reverse_dcf, "current_shares"),
            current_net_debt=cls._field(reverse_dcf, "current_net_debt"),
            historical_terminal_multiple_range=(
                cls._field(valuation, "ev_ebit_guardrail_low"),
                historical_high,
            ),
            bundles=tuple(result.scenario_bundles),
            ranking_model=candidate.ranking_model,
            price_currency=cls._field(reverse_dcf, "price_currency"),
            financial_currency=cls._field(reverse_dcf, "financial_currency"),
            current_terminal_multiple=current_multiple,
            base_terminal_multiple_ceiling=base_ceiling,
            bull_terminal_multiple_ceiling=bull_ceiling,
            demonstrated_revenue_cagr=demonstrated_growth,
            demonstrated_ebit_margin=demonstrated_margin,
            case_horizon_months=result.case_horizon_months,
        )

    @staticmethod
    def _max_number(*values):
        numbers = [
            value
            for value in values
            if isinstance(value, (int, float)) and isfinite(value)
        ]
        return max(numbers) if numbers else None

    @classmethod
    def _selected_required_return(cls, result, candidate):
        reverse_dcf = candidate.full_results.get("reverse_dcf")
        required_return = cls._field(reverse_dcf, "required_return")
        return cls._field(required_return, "required_return")

    @staticmethod
    def _validate_scenario_characterization(result):
        texts = [
            result.one_sentence_thesis,
            result.activation_trigger or "",
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
    def _net_debt_bridges(cls, result, candidate):
        reverse_dcf = candidate.full_results.get("reverse_dcf")
        current_net_debt = cls._field(reverse_dcf, "current_net_debt")
        current_shares = cls._field(reverse_dcf, "current_shares")
        current_sources = cls._field(reverse_dcf, "assumption_sources") or {}
        current_net_debt_source = current_sources.get("current_net_debt") or current_sources.get(
            "net_debt"
        )
        if current_net_debt_source is None:
            latest_r12 = cls._field(
                candidate.full_results.get("financial_history"), "latest_r12"
            )
            current_net_debt_source = cls._field(latest_r12, "source_id")
        if current_net_debt_source is None:
            current_net_debt_source_ids = []
        elif isinstance(current_net_debt_source, (list, tuple)):
            current_net_debt_source_ids = list(current_net_debt_source)
        else:
            current_net_debt_source_ids = [current_net_debt_source]
        current_shares_source_ids = [
            "deterministic:reverse_dcf:current_shares"
        ] if current_shares is not None else []
        return [
            {
                "case": bundle.case,
                "current_net_debt": current_net_debt,
                "net_debt_change": bundle.net_debt_change.value,
                "projected_net_debt": current_net_debt + bundle.net_debt_change.value
                if current_net_debt is not None
                else None,
                "current_net_debt_source_ids": current_net_debt_source_ids,
                "current_shares_source_ids": current_shares_source_ids,
                "change_source_ids": list(bundle.net_debt_change.source_ids),
                "provenance_type": bundle.net_debt_change.provenance_type,
                "mechanism": bundle.net_debt_change.mechanism,
                "reconciles": current_net_debt is not None,
                "current_shares": current_shares,
                "share_count_growth": bundle.share_count_growth.value,
                "projected_shares": current_shares * (1 + bundle.share_count_growth.value)
                if current_shares is not None
                else None,
                "distributions_per_share": bundle.distributions_per_share.value,
                "share_count_assumption_status": cls._zero_assumption_status(
                    bundle.share_count_growth.value,
                    bundle.share_count_growth.rationale,
                ),
                "distribution_assumption_status": cls._zero_assumption_status(
                    bundle.distributions_per_share.value,
                    bundle.distributions_per_share.rationale,
                ),
            }
            for bundle in result.scenario_bundles
        ]

    @staticmethod
    def _zero_assumption_status(value, rationale):
        if value == 0 and any(
            phrase in rationale.lower()
            for phrase in ("missing", "unavailable", "not provided", "unknown")
        ):
            return "analyst_sensitivity_missing_data"
        return "explicit_or_source_backed"

    @classmethod
    def _valuation_provenance(cls, candidate):
        reverse_dcf = candidate.full_results.get("reverse_dcf")
        if reverse_dcf is None:
            return None
        assumptions = cls._field(reverse_dcf, "assumptions")
        implied_expectations = cls._field(reverse_dcf, "implied_expectations") or {}
        required_return = cls._field(reverse_dcf, "required_return")
        normalization = cls._field(reverse_dcf, "normalization")
        expectation_curve = cls._field(reverse_dcf, "expectation_curve") or ()
        return {
            "status": cls._field(reverse_dcf, "status"),
            "reverse_dcf_policy_version": cls._field(reverse_dcf, "policy_version"),
            "price_date": cls._field(reverse_dcf, "price_date"),
            "current_price": cls._field(reverse_dcf, "current_price"),
            "current_revenue": cls._field(reverse_dcf, "current_revenue"),
            "current_shares": cls._field(reverse_dcf, "current_shares"),
            "current_net_debt": cls._field(reverse_dcf, "current_net_debt"),
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
                    "market_cap",
                    "size_bucket",
                    "required_return",
                    "source_date",
                )
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
        expectation_curve = cls._field(reverse_dcf, "expectation_curve") or ()
        for point in expectation_curve:
            expectation = cls._field(point, "ebit_margin_expectation")
            source_id = cls._field(expectation, "source_id")
            if source_id:
                aliases[source_id] = source_id
        return aliases

    @staticmethod
    def _validate_revenue_resilience(result):
        resilience = result.revenue_resilience
        if resilience.assessment == "unassessable":
            if not resilience.limitations:
                raise StockAnalysisValidationError(
                    "unassessable revenue resilience requires a limitation"
                )
            return
        if not resilience.source_ids:
            raise StockAnalysisValidationError(
                "revenue resilience assessments require documentary evidence"
            )
        for name in ("recurring_driver", "variable_driver", "cash_flow_observation"):
            if not getattr(resilience, name).strip():
                raise StockAnalysisValidationError(
                    f"revenue resilience requires {name.replace('_', ' ')}"
                )
        persistence_terms = re.compile(
            r"\b(contract(?:ual)?|renew(?:al|s)?|retention|churn|persist(?:ence|ent)?|"
            r"customer lifetime|net revenue retention)\b",
            re.IGNORECASE,
        )
        variable_terms = re.compile(
            r"\b(transaction\w*|usage\w*|project\w*|order\w*|volume\w*|"
            r"product\w*|sales|one[- ]off|message\w*)\b",
            re.IGNORECASE,
        )
        recurring_terms = re.compile(
            r"\b(contract\w*|subscription\w*|renew\w*|retention|churn|recurring\w*)\b",
            re.IGNORECASE,
        )
        if resilience.assessment == "resilient" and not persistence_terms.search(
            resilience.recurring_driver
        ):
            raise StockAnalysisValidationError(
                "resilient revenue resilience requires evidence of persistence"
            )
        if resilience.assessment == "mixed":
            if not recurring_terms.search(resilience.recurring_driver):
                raise StockAnalysisValidationError(
                    "mixed revenue resilience requires a supported recurring driver"
                )
            if not variable_terms.search(resilience.variable_driver):
                raise StockAnalysisValidationError(
                    "mixed revenue resilience requires a supported variable driver"
                )

        profile = result.business_model_profile
        recurring_models = {
            "subscription",
            "interest_spread",
            "rental",
        }
        variable_models = {"transaction", "usage", "product_sales", "project"}
        models = set(profile.revenue_model_types)
        if models:
            has_recurring_model = bool(models & recurring_models)
            has_variable_model = bool(models & variable_models)
            if resilience.assessment == "resilient" and not has_recurring_model:
                raise StockAnalysisValidationError(
                    "resilient revenue resilience conflicts with revenue model types"
                )
            if resilience.assessment == "mixed" and not (
                has_recurring_model and has_variable_model
            ):
                raise StockAnalysisValidationError(
                    "mixed revenue resilience requires recurring and variable revenue model types"
                )
            if resilience.assessment == "variable" and has_recurring_model:
                raise StockAnalysisValidationError(
                    "variable revenue resilience conflicts with recurring revenue model types"
                )
        if resilience.assessment in {"resilient", "mixed"} and not resilience.recurring_source_ids:
            raise StockAnalysisValidationError(
                f"{resilience.assessment} revenue resilience requires sourced recurring evidence"
            )
        if resilience.assessment == "mixed" and not resilience.variable_source_ids:
            raise StockAnalysisValidationError(
                "mixed revenue resilience requires sourced variable evidence"
            )
        if resilience.assessment in {"resilient", "mixed"} and (
            profile.recurring_revenue_profile == "none"
        ):
            raise StockAnalysisValidationError(
                "revenue resilience conflicts with recurring_revenue_profile=none"
            )
        if resilience.assessment == "variable" and profile.recurring_revenue_profile == "majority":
            raise StockAnalysisValidationError(
                "variable revenue resilience conflicts with recurring_revenue_profile=majority"
            )

    @classmethod
    def _financial_reconciliation_limitations(cls, candidate):
        history = candidate.full_results.get("financial_history")
        framing = cls._field(history, "half_year_comparison")
        limitations = cls._field(framing, "limitations") or []
        return [
            limitation
            for limitation in limitations
            if isinstance(limitation, str) and limitation.startswith("Report ")
        ]

    @classmethod
    def _deterministic_source_aliases(cls, candidate):
        return build_evidence_catalog(
            candidate.full_results, candidate.research_evidence
        )["aliases"]

    @staticmethod
    def _validate_management_sources(result, document_source_ids):
        for claim in result.management_credibility_ledger:
            if not claim.claim_source_ids:
                raise StockAnalysisValidationError(
                    "management credibility claims require claim_source_ids"
                )
            unknown_source_ids = sorted(
                (set(claim.claim_source_ids) | set(claim.outcome_source_ids))
                - document_source_ids
            )
            if unknown_source_ids:
                raise StockAnalysisValidationError(
                    "management credibility claim cites unknown document source(s): "
                    + ", ".join(unknown_source_ids)
                )

    @staticmethod
    def _validate_management_ledger(result):
        assessed_results = {"kept", "delayed", "missed", "changed"}
        ledger = result.management_credibility_ledger
        for index, claim in enumerate(ledger):
            claim.claim = claim.claim.strip()
            if not claim.claim:
                raise StockAnalysisValidationError(
                    f"management credibility claim cannot be empty: {index}"
                )

            legacy_source_ids = set(claim.source_ids)
            if not claim.claim_source_ids and claim.source_ids:
                claim.claim_source_ids = list(claim.source_ids)
            claim.claim_source_ids = list(dict.fromkeys(claim.claim_source_ids))
            claim.outcome_source_ids = list(dict.fromkeys(claim.outcome_source_ids))
            normalized_source_ids = list(
                dict.fromkeys([*claim.claim_source_ids, *claim.outcome_source_ids])
            )
            if legacy_source_ids - set(normalized_source_ids):
                raise StockAnalysisValidationError(
                    "management credibility source_ids must match claim and outcome source IDs"
                )
            claim.source_ids = normalized_source_ids

            observed_outcome = (
                claim.observed_outcome.strip()
                if claim.observed_outcome is not None
                else None
            )
            claim.observed_outcome = observed_outcome or None
            if claim.result in assessed_results:
                if not claim.observed_outcome:
                    raise StockAnalysisValidationError(
                        "assessed management credibility claims require observed_outcome"
                    )
                if not claim.outcome_source_ids:
                    raise StockAnalysisValidationError(
                        "assessed management credibility claims require outcome_source_ids"
                    )
            elif claim.result == "unverifiable":
                claim.observed_outcome = None
                claim.outcome_source_ids = []
                claim.source_ids = list(claim.claim_source_ids)

        coverage = result.management_credibility_coverage
        if (
            not isinstance(coverage.omitted_claim_count, int)
            or isinstance(coverage.omitted_claim_count, bool)
            or coverage.omitted_claim_count < 0
        ):
            raise StockAnalysisValidationError(
                "management credibility omitted_claim_count must be a non-negative integer"
            )

        assessed_count = sum(claim.result in assessed_results for claim in ledger)
        pending_count = sum(claim.result == "unverifiable" for claim in ledger)
        coverage.assessed_claim_count = assessed_count
        coverage.pending_claim_count = pending_count
        coverage.eligible_claim_count = (
            assessed_count + pending_count + coverage.omitted_claim_count
        )
        if coverage.omitted_claim_count and not coverage.omission_reasons:
            raise StockAnalysisValidationError(
                "omitted management credibility claims require omission_reasons"
            )
        if not coverage.omitted_claim_count and coverage.omission_reasons:
            raise StockAnalysisValidationError(
                "omission_reasons require omitted management credibility claims"
            )
        coverage.omission_reasons = [
            reason.strip() for reason in coverage.omission_reasons
        ]
        if any(not reason for reason in coverage.omission_reasons):
            raise StockAnalysisValidationError(
                "management credibility omission reasons cannot be empty"
            )
        return {
            "eligible_claim_count": coverage.eligible_claim_count,
            "assessed_claim_count": coverage.assessed_claim_count,
            "pending_claim_count": coverage.pending_claim_count,
            "omitted_claim_count": coverage.omitted_claim_count,
            "omission_reasons": list(coverage.omission_reasons),
        }

    @staticmethod
    def _validate_structured_conclusions(result):
        structured = result.structured_conclusions
        if structured is None:
            return set()
        payload = asdict(structured)
        source_ids = set()
        claim_ids = set()

        def visit(value):
            if isinstance(value, dict):
                if "claim_id" in value:
                    claim_id = value["claim_id"]
                    if claim_id in claim_ids:
                        raise StockAnalysisValidationError(
                            f"duplicate structured claim ID: {claim_id}"
                        )
                    claim_ids.add(claim_id)
                ids = value.get("source_ids")
                if isinstance(ids, (list, tuple)):
                    if len(ids) != len(set(ids)):
                        raise StockAnalysisValidationError(
                            "structured claim contains duplicate source IDs"
                        )
                    source_ids.update(ids)
                for child in value.values():
                    visit(child)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    visit(child)

        visit(payload)
        return source_ids

    @staticmethod
    def _normalize_assessment_claims(
        claims, source_aliases, full_results=None, research_evidence=None
    ):
        for claim in claims:
            claim.statement = claim.statement.strip()
            if not claim.statement:
                raise StockAnalysisValidationError(
                    "assessment claim statement cannot be empty"
                )
            if not claim.source_ids:
                raise StockAnalysisValidationError(
                    "assessment claims require source_ids"
                )
            claim.source_ids = [
                AgentExecutionBoundary._resolve_source_alias(
                    source_id,
                    source_aliases,
                    full_results,
                    research_evidence,
                )
                for source_id in claim.source_ids
            ]
            if len(claim.source_ids) != len(set(claim.source_ids)):
                raise StockAnalysisValidationError(
                    "assessment claim contains duplicate source IDs"
                )

    @staticmethod
    def _resolve_source_alias(
        source_id,
        source_aliases,
        full_results=None,
        research_evidence=None,
    ):
        if "canonical_source_ids" in source_aliases:
            try:
                return resolve_source_id(
                    source_id,
                    full_results,
                    research_evidence,
                    catalog=source_aliases,
                )
            except SourcePathError as exc:
                raise StockAnalysisValidationError(
                    f"unknown evidence source: {source_id}"
                ) from exc
        return source_aliases.get(source_id, source_id)

    @staticmethod
    def _validate_assessment_sections(
        result,
        *,
        document_source_ids,
        insider_source_ids,
        ownership_liquidity_source_ids,
        ownership_liquidity,
    ):
        violations = []
        if result.management_assessment.strip() and not result.management_claims:
            violations.append(
                "management assessment requires structured management claims"
            )
        management_sources = {
            source_id
            for claim in result.management_claims
            for source_id in claim.source_ids
        }
        unknown_management_sources = sorted(
            management_sources - document_source_ids
        )
        if unknown_management_sources:
            violations.append(
                "management claims must cite supplied documents: "
                + ", ".join(unknown_management_sources)
            )

        if (
            ownership_liquidity_source_ids
            and result.ownership_and_flow_assessment.strip()
            and not result.ownership_claims
        ):
            violations.append(
                "ownership and flow assessment requires structured ownership claims"
            )
        ownership_sources = set()
        for index, claim in enumerate(result.ownership_claims):
            if isinstance(claim, OwnershipClaim):
                ownership_sources.update(claim.binding.source_ids)
                try:
                    AgentExecutionBoundary._validate_typed_ownership_claim(
                        claim, {"research_evidence": {"ownership_liquidity": ownership_liquidity}}
                    )
                except StockAnalysisValidationError as exc:
                    violations.append(
                        f'ownership_claims[{index}] offending claim '
                        f'"{claim.measure}={claim.binding.asserted_value!r}" requires repair; '
                        f'{exc}; documentary citations cannot be relabeled as ownership evidence; '
                        "changing a documentary citation into an ownership citation is not permitted; "
                        "omit the claim."
                    )
            else:
                ownership_sources.update(claim.source_ids)
                if not claim.source_ids or set(claim.source_ids) - ownership_liquidity_source_ids:
                    violations.append(
                        f'ownership_claims[{index}] offending statement '
                        f'{claim.statement!r} requires an approved ownership/liquidity source; '
                        "documentary citations cannot be relabeled as ownership evidence; "
                        "changing a documentary citation into an ownership citation is not permitted; "
                        "omit the claim."
                    )
        unknown_ownership_sources = sorted(
            ownership_sources - ownership_liquidity_source_ids
        )
        if unknown_ownership_sources:
            violations.append(
                "ownership claims must cite supplied ownership/liquidity evidence: "
                + ", ".join(unknown_ownership_sources)
            )
        try:
            AgentExecutionBoundary._validate_supported_ownership_claims(
                [claim for claim in result.ownership_claims if not isinstance(claim, OwnershipClaim)],
                ownership_liquidity,
            )
        except StockAnalysisValidationError as exc:
            violations.extend(getattr(exc, "violations", (str(exc),)))

        if insider_source_ids and result.insider_assessment.strip() and not result.insider_claims:
            violations.append(
                "insider assessment requires structured insider claims"
            )
        insider_sources = {
            source_id
            for claim in result.insider_claims
            for source_id in claim.source_ids
        }
        if insider_sources and not insider_sources.intersection(insider_source_ids):
            violations.append(
                "insider claims must cite at least one supplied insider transaction"
            )
        _raise_validation_violations(violations)

    @classmethod
    def _validate_typed_ownership_claim(cls, claim, evidence):
        if not claim.binding.source_ids:
            raise StockAnalysisValidationError(
                "binding requires the exact generated ownership source set"
            )
        if len(claim.binding.source_ids) != len(set(claim.binding.source_ids)):
            raise StockAnalysisValidationError("binding contains duplicate source IDs")
        try:
            field = ownership_field(claim.measure)
        except ValueError as exc:
            raise StockAnalysisValidationError(str(exc)) from exc
        if claim.subject_role != field.subject_role or claim.claim_kind != field.claim_kind:
            raise StockAnalysisValidationError(
                f"claim kind/subject role does not match measure {claim.measure}"
            )
        if claim.binding.deterministic_field != field.deterministic_field:
            raise StockAnalysisValidationError(
                f"deterministic field must be {field.deterministic_field}"
            )
        if claim.binding.asserted_unit != field.asserted_unit:
            raise StockAnalysisValidationError(
                f"asserted unit must be {field.asserted_unit}"
            )
        expected = packet_value(evidence, field)
        if expected is None:
            raise StockAnalysisValidationError(
                f"measure {claim.measure} has no supplied deterministic field"
            )
        if claim.binding.asserted_value != expected:
            raise StockAnalysisValidationError(
                f"asserted value for {claim.measure} must equal the supplied packet value"
            )
        ownership_evidence = evidence["research_evidence"]["ownership_liquidity"]
        supplied = ownership_source_ids_for_measure(ownership_evidence, claim.measure)
        if not supplied or tuple(claim.binding.source_ids) != supplied:
            raise StockAnalysisValidationError(
                f"source IDs {list(claim.binding.source_ids)!r} must equal the exact "
                f"generated source set {list(supplied)!r} for measure {claim.measure}"
            )

    @staticmethod
    def _validate_supported_ownership_claims(claims, evidence):
        ownership = evidence.get("ownership") or {}
        changes = evidence.get("changes") or {}
        field_groups = (
            (("free float", "free-float"), ownership, (
                "free_float_pct", "free_float_shares", "free_float_market_cap"
            )),
            (("institutional ownership",), ownership, ("institutional_pct",)),
            (("holder concentration", "capital concentration"), ownership, (
                "top_1_capital_pct", "top_3_capital_pct", "top_10_capital_pct"
            )),
            (("voting control", "voting ownership"), ownership, ("top_1_voting_pct",)),
            (("ownership change", "ownership broadening", "ownership concentration"), changes, (
                "quarter", "year"
            )),
        )
        for claim in claims:
            statement = claim.statement.casefold()
            if not re.search(r"(?<!\w)[+-]?\d+(?:[.,]\d+)?\s*%?", statement):
                continue
            for phrases, values, fields_to_check in field_groups:
                if any(phrase in statement for phrase in phrases) and not any(
                    values.get(field) is not None for field in fields_to_check
                ):
                    raise StockAnalysisValidationError(
                        "precise ownership claim requires a supplied deterministic field"
                    )

    @staticmethod
    def _validate_portfolio_eligibility(result, *, require_scenario=True):
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
            if require_scenario and (
                result.forward_scenario_analysis is None
                or result.forward_scenario_analysis.status != "available"
            ):
                raise StockAnalysisValidationError(
                    "investable cases require an available forward scenario"
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

    @classmethod
    def _validate_verdict_coherence(
        cls, result, candidate, *, require_forward_scenario=True
    ):
        """Validate the model verdict against deterministic valuation outputs.

        This method only rejects a contradictory model verdict. It never changes
        the verdict or promotes a case.
        """
        reverse_dcf = candidate.full_results.get("reverse_dcf")
        reverse_status = cls._field(reverse_dcf, "status")
        normalization = cls._field(reverse_dcf, "normalization")
        reverse_assessment = result.reverse_dcf_expectation_assessment
        forward = result.forward_scenario_analysis
        base = forward.band("base") if forward is not None else None
        required_return = cls._selected_required_return(result, candidate)
        checks = {
            "reverse_dcf_available": reverse_status == "available",
            "reverse_dcf_assessment": reverse_assessment,
            "forward_scenario_available": bool(
                forward is not None and forward.status == "available"
            ),
            "base_annualized_return_range": (
                [base.low_annualized_return, base.high_annualized_return]
                if base is not None
                else None
            ),
            "required_return": required_return,
            "normalization_confidence": cls._field(normalization, "confidence"),
            "latent_case_type": result.latent_case_type,
            "activation_trigger_present": bool(
                (result.activation_trigger or "").strip()
            ),
        }

        def reject(message):
            error = StockAnalysisValidationError(
                "verdict coherence conflict: " + message
            )
            error.deterministic_output_diagnostic = {
                "type": "verdict_coherence",
                "verdict": result.verdict,
                "latent_case_type": result.latent_case_type,
                "base_annualized_return_range": checks[
                    "base_annualized_return_range"
                ],
                "required_return": required_return,
                "conflict": message,
            }
            raise error

        if result.verdict == "activated_case":
            if reverse_status != "available":
                reject("activated_case requires reverse_dcf.status=available")
            if reverse_assessment == "unsupported":
                reject("activated_case cannot use unsupported reverse DCF")
            if require_forward_scenario:
                if forward is None or forward.status != "available":
                    reject("activated_case requires an available forward scenario")
                if base is None or required_return is None:
                    reject(
                        "activated_case requires a base annualized-return range and required_return"
                    )
                if base.low_annualized_return < required_return:
                    reject(
                        "activated_case base lower-bound return is below required_return"
                    )
            if any(
                evidence.status == "unresolved"
                for evidence in result.activation_trigger_evidence
            ):
                reject("activated_case cannot retain unresolved activation trigger evidence")
        elif result.verdict == "operating-latent":
            # Kept as an internal spelling guard in case a caller bypasses the
            # contract type; public cards use latent_case_type=operating.
            reject("operating-latent is not a public verdict")
        elif result.verdict == "latent_case" and result.latent_case_type == "operating":
            if reverse_status != "available":
                reject("operating latent requires reverse_dcf.status=available")
            if reverse_assessment == "unsupported":
                reject("operating latent cannot use unsupported reverse DCF")
            if require_forward_scenario:
                if forward is None or forward.status != "available":
                    reject("operating latent requires an available forward scenario")
                if base is None or required_return is None:
                    reject(
                        "operating latent requires a base annualized-return range and required_return"
                    )
                if base.high_annualized_return < required_return:
                    reject(
                        "operating latent base upper-bound return is below required_return"
                    )
        elif result.verdict == "latent_case" and result.latent_case_type == "price":
            trigger_text = " ".join(
                (
                    result.activation_trigger or "",
                    result.activation_trigger_spec.observable_metric_or_event,
                    result.activation_trigger_spec.threshold_or_direction,
                )
            ).lower()
            if not re.search(r"\b(price|valuation|multiple|return|hurdle)\b", trigger_text):
                reject("price latent requires a concrete price or valuation condition")
            if (
                base is not None
                and required_return is not None
                and base.low_annualized_return >= required_return
            ):
                reject(
                    "price latent cannot claim economically sufficient current-price returns"
                )

        if result.verdict in {"activated_case"} or (
            result.verdict == "latent_case" and result.latent_case_type == "operating"
        ):
            if base is not None and required_return is not None:
                if base.high_annualized_return < required_return:
                    reject(
                        "base upper-bound return is below required_return for the selected verdict"
                    )
        return checks

    @classmethod
    def validate_verdict_coherence(
        cls, result, candidate, *, require_forward_scenario=True
    ):
        """Validate a completed scenario against its qualitative verdict."""
        return cls._validate_verdict_coherence(
            result,
            candidate,
            require_forward_scenario=require_forward_scenario,
        )


def _raise_validation_violations(violations):
    unique = list(dict.fromkeys(violations))
    if not unique:
        return
    if len(unique) == 1:
        raise StockAnalysisValidationError(unique[0])
    details = "\n".join(f"- {message}" for message in unique)
    error = StockAnalysisValidationError(
        f"qualitative validation failed with {len(unique)} violations:\n{details}"
    )
    error.violations = tuple(unique)
    raise error
