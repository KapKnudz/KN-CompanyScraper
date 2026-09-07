"""Deterministic, shadow-only evaluation of the four explicit specialist conflicts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Literal

from kncompanyscraper.analysis.agent.output_schema import (
    SpecialistAgentName,
    SpecialistClaimDirection,
    SpecialistOutput,
)


ConflictRuleId = Literal[
    "margin_vs_sell_condition",
    "insider_vs_credibility_record",
    "circle_of_competence_vs_valuation",
    "multiple_expansion_vs_activation",
]
ConflictSeverity = Literal["medium", "high"]
ConflictAction = Literal["annotate", "block_activation"]
FinalDirection = Literal["reject", "watch", "latent_case", "activated_case"]


@dataclass(frozen=True)
class SpecialistConflict:
    rule_id: ConflictRuleId
    severity: ConflictSeverity
    trigger_fields: tuple[str, ...]
    trigger_claim_ids: tuple[str, ...]
    explanation: str
    source_ids: tuple[str, ...]
    action: ConflictAction

    def to_dict(self) -> dict:
        data = asdict(self)
        data["trigger_fields"] = list(self.trigger_fields)
        data["trigger_claim_ids"] = list(self.trigger_claim_ids)
        data["source_ids"] = list(self.source_ids)
        return data


def evaluate_specialist_conflicts(
    outputs: Iterable[SpecialistOutput],
    *,
    final_direction: FinalDirection | None = None,
) -> tuple[SpecialistConflict, ...]:
    """Evaluate only the named conflicts over typed specialist outputs.

    The function intentionally has no prose comparison, scoring, or generic
    disagreement behavior. Sell-condition and final-direction inputs are
    optional because those stages are not part of the first-wave shadow run.
    """
    by_agent = {output.agent_name: output for output in outputs}
    conflicts: list[SpecialistConflict] = []

    margin = by_agent.get(SpecialistAgentName.MARGIN)
    sell = by_agent.get(SpecialistAgentName.SELL_CONDITIONS)
    if margin is not None and _margin_conflict(margin, sell):
        margin_claims = _envelope_claims(margin)
        sell_test = _margin_sell_test(sell)
        blockers = _margin_blockers(sell, margin_claims)
        conflicts.append(
            SpecialistConflict(
                rule_id="margin_vs_sell_condition",
                severity="high",
                trigger_fields=(
                    "margin.margin_state",
                    "margin.margin_dependency",
                    "sell_conditions.margin_or_execution",
                ),
                trigger_claim_ids=_ordered_ids(
                    [
                        *[claim.claim_id for claim in margin_claims],
                        *(_test_claim_ids(sell_test) if sell_test else ()),
                        *(_blocker_claim_ids(blockers)),
                    ]
                ),
                explanation=(
                    "stalled_or_invalidated_material_margin_mechanism_has_a_triggered_break"
                ),
                source_ids=_ordered_ids(
                    [
                        *[source_id for claim in margin_claims for source_id in claim.source_ids],
                        *(_test_source_ids(sell_test) if sell_test else ()),
                        *(_blocker_source_ids(blockers)),
                        *margin.margin.supporting_source_ids,
                        *margin.margin.contrary_source_ids,
                    ]
                ),
                action="block_activation",
            )
        )

    management = by_agent.get(SpecialistAgentName.MANAGEMENT_CREDIBILITY)
    insider = by_agent.get(SpecialistAgentName.INSIDER_OWNERSHIP)
    if management is not None and insider is not None and _insider_conflict(
        management, insider
    ):
        missed_rows = [
            row
            for row in management.management_credibility.ledger
            if _enum_value(row.result) == "missed"
        ]
        insider_claims = insider.insider_ownership.event_claims
        conflicts.append(
            SpecialistConflict(
                rule_id="insider_vs_credibility_record",
                severity="medium",
                trigger_fields=(
                    "insider_ownership.insider_signal",
                    "insider_ownership.signal_strength",
                    "management_credibility.pattern_state",
                    "management_credibility.ledger.result=missed",
                ),
                trigger_claim_ids=_ordered_ids(
                    [
                        *[claim.claim_id for claim in insider_claims],
                        *[row.claim_id for row in missed_rows],
                    ]
                ),
                explanation="strong_positive_insider_signal_conflicts_with_genuine_missed_promises",
                source_ids=_ordered_ids(
                    [
                        *[source_id for claim in insider_claims for source_id in claim.source_ids],
                        *[
                            source_id
                            for row in missed_rows
                            for source_id in row.source_ids
                        ],
                    ]
                ),
                action="annotate",
            )
        )

    business = by_agent.get(SpecialistAgentName.BUSINESS_MODEL)
    growth = by_agent.get(SpecialistAgentName.GROWTH_VALUATION)
    if business is not None and growth is not None and _circle_conflict(
        business, growth
    ):
        business_claims = business.business_model.claims
        growth_claims = growth.growth_valuation.claims
        conflicts.append(
            SpecialistConflict(
                rule_id="circle_of_competence_vs_valuation",
                severity="high",
                trigger_fields=(
                    "business_model.circle_of_competence",
                    "growth_valuation.reverse_dcf_assessment",
                ),
                trigger_claim_ids=_ordered_ids(
                    [
                        *[claim.claim_id for claim in business_claims],
                        *[claim.claim_id for claim in growth_claims],
                    ]
                ),
                explanation="valuation_claim_relies_on_assumptions_outside_or_unassessable_within_circle",
                source_ids=_ordered_ids(
                    [
                        *[source_id for claim in business_claims for source_id in claim.source_ids],
                        *[source_id for claim in growth_claims for source_id in claim.source_ids],
                    ]
                ),
                action="block_activation",
            )
        )

    margin_output = by_agent.get(SpecialistAgentName.MARGIN)
    if growth is not None and _multiple_conflict(
        growth, margin_output, final_direction
    ):
        growth_claims = growth.growth_valuation.claims
        margin_claims = margin_output.claims if margin_output is not None else []
        conflicts.append(
            SpecialistConflict(
                rule_id="multiple_expansion_vs_activation",
                severity="high",
                trigger_fields=(
                    "growth_valuation.engine_dependency",
                    "final_direction",
                    "fundamental_revenue_or_margin_engine_claim",
                ),
                trigger_claim_ids=_ordered_ids(
                    [
                        *[claim.claim_id for claim in growth_claims],
                        *[claim.claim_id for claim in margin_claims],
                    ]
                ),
                explanation="multiple_expansion_is_primary_without_a_supported_fundamental_engine",
                source_ids=_ordered_ids(
                    [
                        *[source_id for claim in growth_claims for source_id in claim.source_ids],
                        *[source_id for claim in margin_claims for source_id in claim.source_ids],
                    ]
                ),
                action="block_activation",
            )
        )

    return tuple(conflicts)


def _margin_conflict(margin: SpecialistOutput, sell: SpecialistOutput | None) -> bool:
    margin_payload = margin.margin
    if margin_payload is None or margin_payload.margin_state not in {
        "stalled",
        "invalidated",
    } or margin_payload.margin_dependency not in {"material", "primary"}:
        return False
    return _margin_sell_test(sell) is not None or bool(
        _margin_blockers(sell, _envelope_claims(margin))
    )


def _margin_sell_test(output: SpecialistOutput | None) -> dict | None:
    if output is None or output.sell_conditions is None:
        return None
    for test in output.sell_conditions.tests:
        if (
            test.get("break_type") == "margin_or_execution"
            and test.get("current_break_status") == "triggered"
        ):
            return test
    return None


def _margin_blockers(
    output: SpecialistOutput | None, margin_claims
) -> list[dict]:
    if output is None or output.sell_conditions is None:
        return []
    margin_claim_ids = {claim.claim_id for claim in margin_claims}
    return [
        blocker
        for blocker in output.sell_conditions.activation_blockers
        if blocker.get("blocker_code") == "margin_or_execution"
        or margin_claim_ids.intersection(blocker.get("claim_ids", []))
    ]


def _insider_conflict(management: SpecialistOutput, insider: SpecialistOutput) -> bool:
    management_payload = management.management_credibility
    insider_payload = insider.insider_ownership
    if management_payload is None or insider_payload is None:
        return False
    return (
        insider_payload.insider_signal == "positive"
        and insider_payload.signal_strength == "strong"
        and _enum_value(management_payload.pattern_state) == "weak"
        and any(
            _enum_value(row.result) == "missed"
            for row in management_payload.ledger
        )
    )


def _circle_conflict(business: SpecialistOutput, growth: SpecialistOutput) -> bool:
    business_payload = business.business_model
    growth_payload = growth.growth_valuation
    if business_payload is None or growth_payload is None:
        return False
    outside_circle = business_payload.circle_of_competence in {"outside", "unassessable"}
    valuation_claim = growth_payload.reverse_dcf_assessment in {
        "plausible",
        "demanding",
        "unsupported",
    }
    return outside_circle and valuation_claim


def _multiple_conflict(
    growth: SpecialistOutput,
    margin: SpecialistOutput | None,
    final_direction: FinalDirection | None,
) -> bool:
    growth_payload = growth.growth_valuation
    if growth_payload is None or final_direction not in {"latent_case", "activated_case"}:
        return False
    if growth_payload.engine_dependency not in {"multiple_primary", "multiple_only"}:
        return False
    return not _has_supported_fundamental_engine(growth, margin)


def _has_supported_fundamental_engine(
    growth: SpecialistOutput, margin: SpecialistOutput | None
) -> bool:
    claims = list(growth.claims)
    if growth.growth_valuation is not None:
        claims.extend(growth.growth_valuation.claims)
    if margin is not None:
        claims.extend(margin.claims)
    return any(
        claim.domain in {"revenue", "margin"}
        and claim.source_ids
        and (
            claim.direction is SpecialistClaimDirection.POSITIVE
            or claim.value in {"supported", "positive", "confirmed", "improving", "resilient"}
        )
        for claim in claims
    )


def _enum_value(value):
    return getattr(value, "value", value)


def _envelope_claims(output: SpecialistOutput) -> list:
    return list(output.claims)


def _test_claim_ids(test: dict | None) -> tuple[str, ...]:
    return tuple(test.get("claim_ids", [])) if test else ()


def _test_source_ids(test: dict | None) -> tuple[str, ...]:
    return tuple(test.get("source_ids", [])) if test else ()


def _blocker_claim_ids(blockers: list[dict]) -> tuple[str, ...]:
    return tuple(
        claim_id
        for blocker in blockers
        for claim_id in blocker.get("claim_ids", [])
    )


def _blocker_source_ids(blockers: list[dict]) -> tuple[str, ...]:
    return tuple(
        source_id
        for blocker in blockers
        for source_id in blocker.get("source_ids", [])
    )


def _ordered_ids(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))
