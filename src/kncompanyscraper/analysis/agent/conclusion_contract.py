"""Closed, code-owned bindings for deterministic ownership conclusions.

The model can select a measure, but it cannot select where that measure is
rendered or broaden the source scope.  This registry is deliberately small and
is generated from the ownership/liquidity packet contract.
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class TypedClaim:
    claim_id: str
    domain: str
    predicate: str
    value: int | float | str | bool | None
    source_ids: tuple[str, ...]
    limitation_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class FalsifiableCaseComponent:
    case_ref: str
    horizon_months: int
    baseline_refs: tuple[str, ...]
    falsification: TypedClaim


@dataclass(frozen=True)
class HeadlineCase:
    case_ref: str
    horizon_months: int
    revenue_mechanism: str
    profitability_state: str
    expectation_refs: tuple[str, ...]
    break_condition: TypedClaim


@dataclass(frozen=True)
class StructuredConclusions:
    headline_case: HeadlineCase
    falsifiable_case: FalsifiableCaseComponent
    evidence_claims: tuple[TypedClaim, ...]
    break_tests: tuple[TypedClaim, ...]
    management_claims: tuple[TypedClaim, ...]
    management_ledger: tuple[TypedClaim, ...]
    company_facts: tuple[TypedClaim, ...]
    business_model_facts: tuple[TypedClaim, ...]
    margin_facts: tuple[TypedClaim, ...]
    timing_facts: tuple[TypedClaim, ...]
    limitation_codes: tuple[str, ...]
    trigger: TypedClaim | None
    revenue_resilience: TypedClaim
    reverse_dcf_assessment: str


@dataclass(frozen=True)
class OwnershipField:
    claim_kind: str
    subject_role: str
    measure: str
    deterministic_field: str
    asserted_unit: str
    renderer_key: str = "ownership_and_flow_assessment"


_FIELDS = (
    OwnershipField("listing", "company", "market_id", "research_evidence.ownership_liquidity.listing.market_id", "identifier"),
    OwnershipField("listing", "company", "venue", "research_evidence.ownership_liquidity.listing.venue", "identifier"),
    OwnershipField("listing", "company", "listing_date", "research_evidence.ownership_liquidity.listing.listing_date", "date"),
    *(OwnershipField("liquidity", "market", measure, f"research_evidence.ownership_liquidity.liquidity.{measure}", unit)
      for measure, unit in (("adtv_20", "currency"), ("adtv_60", "currency"), ("adtv_120", "currency"),
                            ("observed_days_20", "days"), ("observed_days_60", "days"),
                            ("observed_days_120", "days"), ("zero_volume_days_120", "days"))),
    *(OwnershipField("buyback", "company", measure, f"research_evidence.ownership_liquidity.flow_signals.buybacks.{measure}", unit)
      for measure, unit in (("latest_event_date", "date"), ("trailing_3_month_change_shares_raw", "shares"),
                            ("trailing_12_month_change_shares_raw", "shares"), ("latest_treasury_shares", "shares"),
                            ("latest_treasury_shares_pct_raw", "raw"))),
    *(OwnershipField("short_interest", "short_position", measure, f"research_evidence.ownership_liquidity.flow_signals.shorts.{measure}", unit)
      for measure, unit in (("observation_date", "date"), ("snapshot_age_days", "days"), ("short_pct_raw", "raw"),
                            ("reported_holder_count_raw", "raw"), ("average_short_pct_raw", "raw"),
                            ("short_value_millions_raw", "raw"))),
    *(OwnershipField("long_holder_ownership", "long_holder", measure, f"research_evidence.ownership_liquidity.ownership.{measure}", unit)
      for measure, unit in (("free_float_pct", "percent"), ("free_float_shares", "shares"),
                            ("free_float_market_cap", "currency"), ("institutional_pct", "percent"),
                            ("top_1_capital_pct", "percent"), ("top_3_capital_pct", "percent"),
                            ("top_10_capital_pct", "percent"), ("top_1_voting_pct", "percent"),
                            ("index_eligibility", "status"))),
)

OWNERSHIP_FIELD_REGISTRY = MappingProxyType({field.measure: field for field in _FIELDS})
OWNERSHIP_MEASURES = tuple(OWNERSHIP_FIELD_REGISTRY)
NO_OWNERSHIP_LIQUIDITY_ASSESSMENT = (
    "Ownership and liquidity evidence are unavailable. "
    "No inference can be made from their absence."
)

STRUCTURED_CASE_REFS = (
    "fundamental_case",
    "revenue_growth_case",
    "margin_expansion_case",
    "unassessable_case",
)


def ownership_field(measure: str) -> OwnershipField:
    try:
        return OWNERSHIP_FIELD_REGISTRY[measure]
    except KeyError as exc:
        raise ValueError(f"unknown ownership measure: {measure}") from exc


def ownership_source_ids_for_measure(packet: dict, measure: str) -> tuple[str, ...]:
    """Return the packet-generated exact source set; never infer by prefix."""
    source_map = packet.get("source_ids_by_measure") or {}
    source_ids = source_map.get(measure, ())
    return tuple(source_ids) if isinstance(source_ids, (list, tuple)) else ()


def packet_value(packet: dict, field: OwnershipField) -> Any:
    value: Any = packet
    for part in field.deterministic_field.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def render_structured_headline(conclusions: dict) -> str:
    headline = conclusions["headline_case"]
    case_label = {
        "fundamental_case": "Fundamental case",
        "revenue_growth_case": "Revenue-growth case",
        "margin_expansion_case": "Margin-expansion case",
        "unassessable_case": "Unassessable case",
    }[headline["case_ref"]]
    return (
        f"{case_label} over {headline['horizon_months']} months; "
        f"mechanism={headline['revenue_mechanism']}; "
        f"profitability={headline['profitability_state']}."
    )


def render_ownership_claims(claims: list[dict]) -> str:
    """Render only validated typed claims into the fixed ownership destination."""
    if not claims or any("measure" not in claim for claim in claims):
        return NO_OWNERSHIP_LIQUIDITY_ASSESSMENT
    rendered = []
    for claim in claims:
        field = ownership_field(claim["measure"])
        value = claim["binding"]["asserted_value"]
        rendered.append(f"{field.measure.replace('_', ' ')}: {value}")
    return "Ownership and liquidity evidence: " + "; ".join(rendered) + "."
