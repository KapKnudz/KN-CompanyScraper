"""Explicit, lossless model-facing packet and its canonical source catalog."""

from dataclasses import asdict, dataclass, field, is_dataclass
import json
from typing import Any, Mapping

from kncompanyscraper.analysis.agent.json_support import json_default


class SourcePathError(ValueError):
    """Raised when a deterministic full-results path is not exact and safe."""


_MISSING = object()


@dataclass(frozen=True)
class AgentCandidatePacket:
    """The deliberate subset of a candidate that is sent to an agent."""

    rank: int
    company_id: int
    ticker: str
    name: str
    ranking_model: Any
    rank_eligible: bool
    eligibility_reasons: list[str]
    total_score: float
    score_breakdown: dict
    data_quality: Any
    flags: list[str]
    candidate_reason: str | None
    positives: list[str]
    negatives: list[str]
    missing_data: list[str]
    full_results: dict
    research_evidence: dict
    evidence_catalog: dict = field(default_factory=dict)

    @classmethod
    def from_candidate(cls, candidate) -> "AgentCandidatePacket":
        return cls(
            rank=candidate.rank,
            company_id=candidate.company_id,
            ticker=candidate.ticker,
            name=candidate.name,
            ranking_model=candidate.ranking_model,
            rank_eligible=candidate.rank_eligible,
            eligibility_reasons=list(candidate.eligibility_reasons),
            total_score=candidate.total_score,
            score_breakdown=dict(candidate.score_breakdown),
            data_quality=candidate.data_quality,
            flags=list(candidate.flags),
            candidate_reason=candidate.candidate_reason,
            positives=list(candidate.positives),
            negatives=list(candidate.negatives),
            missing_data=list(candidate.missing_data),
            full_results=candidate.full_results,
            research_evidence=candidate.research_evidence,
            evidence_catalog=build_evidence_catalog(
                candidate.full_results, candidate.research_evidence
            ),
        )

    def to_dict(self) -> dict:
        return asdict(self)


# These names make the packet contract discoverable without coupling callers to
# the candidate-specific class name.
AgentEvidencePacket = AgentCandidatePacket
EvidencePacket = AgentCandidatePacket


def build_evidence_catalog(
    full_results: Mapping | None, research_evidence: Mapping | None
) -> dict:
    research_evidence = research_evidence or {}
    documentary = _ordered_ids(
        item.get("source_id")
        for item in research_evidence.get("documents", [])
        if isinstance(item, Mapping)
    )
    insider = _ordered_ids(
        item.get("source_id")
        for item in research_evidence.get("insider_transactions", [])
        if isinstance(item, Mapping)
    )
    ownership = _ordered_ids(
        research_evidence.get("ownership_liquidity", {}).get("source_ids", [])
        if isinstance(research_evidence.get("ownership_liquidity"), Mapping)
        else []
    )
    deterministic = _source_ids(full_results or {})
    financial = [
        source_id for source_id in deterministic if source_id.startswith("financial:")
    ]
    supported = [source_id for source_id in deterministic if source_id not in financial]
    aliases = build_source_aliases(full_results or {}, research_evidence)
    canonical = _ordered_ids(
        [
            *documentary,
            *insider,
            *ownership,
            *financial,
            *supported,
            *aliases.values(),
        ]
    )
    return {
        "documentary_source_ids": documentary,
        "insider_source_ids": insider,
        "ownership_flow_source_ids": ownership,
        "financial_source_ids": financial,
        "supported_deterministic_source_ids": supported,
        "canonical_source_ids": canonical,
        "aliases": aliases,
    }


def build_source_aliases(
    full_results: Mapping | None, research_evidence: Mapping | None
) -> dict:
    """Build only explicit compatibility aliases.

    Individual deterministic leaves are resolved from the frozen object at
    validation time; they are deliberately not enumerated here.
    """
    aliases: dict[str, str] = {}

    for path in (
        ("financial_history", "half_year_comparison"),
        ("financial_history", "scenario_history"),
        ("insider",),
        ("peer_comparison",),
        ("reverse_dcf", "required_return"),
        ("reverse_dcf", "expectation_curve"),
        ("reverse_dcf", "normalization"),
        ("reverse_dcf", "operating_history"),
        ("reverse_dcf", "price_fundamental_attribution"),
        ("reverse_dcf", "missing_information"),
    ):
        if _path_exists(full_results or {}, path):
            aliases["full_results." + ".".join(path)] = (
                "deterministic:" + ":".join(path)
            )

    reverse_dcf = _field(full_results or {}, "reverse_dcf")
    implied_expectations = _field(reverse_dcf, "implied_expectations") or {}
    if isinstance(implied_expectations, Mapping):
        for assumption, expectation in implied_expectations.items():
            path = (
                "reverse_dcf",
                "implied_expectations",
                str(assumption),
            )
            if not _path_exists(full_results or {}, path):
                continue
            aliases["full_results." + ".".join(path)] = (
                _field(expectation, "source_id")
                or f"valuation:reverse_dcf:{assumption}"
            )

    evidence = research_evidence or {}
    if "insider_event_count" in evidence:
        aliases["research:insider_event_count"] = "research:insider_event_count"
        aliases["research_evidence.insider_event_count"] = "research:insider_event_count"
    if "insider_status" in evidence:
        aliases["research:insider_status"] = "research:insider_status"
        aliases["research_evidence.insider_status"] = "research:insider_status"
        aliases["full_results.insider_status"] = "research:insider_status"
    if "missing_information" in evidence:
        aliases["research:missing_information"] = "research:missing_information"
        aliases["research_evidence.missing_information"] = "research:missing_information"

    for document in evidence.get("documents", []):
        if not isinstance(document, Mapping):
            continue
        canonical = document.get("source_id")
        if not isinstance(canonical, str) or not canonical:
            continue
        for equivalent in document.get("equivalent_source_ids", []):
            if isinstance(equivalent, str) and equivalent:
                aliases[equivalent] = canonical

    return aliases


def resolve_source_id(
    source_id: str,
    full_results: Mapping | None,
    research_evidence: Mapping | None = None,
    *,
    catalog: Mapping | None = None,
) -> str:
    """Resolve one model-supplied source ID against the supplied evidence.

    Full-results paths and deterministic IDs are accepted only after an exact
    traversal. Compatibility aliases may normalize a verified descendant to
    their declared aggregate source ID.
    """
    catalog = catalog or build_evidence_catalog(full_results, research_evidence)
    aliases = catalog.get("aliases", {})
    canonical_ids = set(catalog.get("canonical_source_ids", []))

    if source_id in canonical_ids:
        return source_id
    if source_id in aliases:
        return aliases[source_id]

    if source_id.startswith("full_results."):
        path = _parse_full_results_path(source_id)
        _walk_path(full_results or {}, path)
        canonical = "deterministic:" + ":".join(path)
        for alias, target in sorted(
            aliases.items(), key=lambda item: len(item[0]), reverse=True
        ):
            if alias.startswith("full_results.") and (
                source_id == alias or source_id.startswith(alias + ".")
            ):
                return target
        return canonical

    if source_id.startswith("deterministic:"):
        path = tuple(source_id.removeprefix("deterministic:").split(":"))
        if not path or any(not part for part in path):
            raise SourcePathError(f"invalid deterministic source ID: {source_id}")
        _walk_path(full_results or {}, path)
        return "deterministic:" + ":".join(path)

    return source_id


def _parse_full_results_path(source_id: str) -> tuple[str, ...]:
    path_text = source_id.removeprefix("full_results.")
    path = tuple(path_text.split("."))
    if not path or any(not part for part in path):
        raise SourcePathError(f"invalid full-results source path: {source_id}")
    return path


def _walk_path(value: Any, path: tuple[str, ...] | list[str]):
    current = value
    for segment in path:
        current = _walk_segment(current, segment)
        if current is _MISSING:
            raise SourcePathError(
                "nonexistent full-results source path: "
                + ".".join(path)
            )
    return current


def _path_exists(value: Any, path: tuple[str, ...] | list[str]) -> bool:
    try:
        _walk_path(value, path)
    except SourcePathError:
        return False
    return True


def _walk_segment(value: Any, segment: str):
    if isinstance(value, Mapping):
        has_string_key = segment in value
        numeric_key = _canonical_integer(segment)
        has_integer_key = numeric_key is not None and numeric_key in value
        if has_string_key and has_integer_key:
            raise SourcePathError(f"ambiguous numeric mapping key: {segment}")
        if has_string_key:
            return value[segment]
        if has_integer_key:
            return value[numeric_key]
        return _MISSING
    if isinstance(value, (list, tuple)):
        index = _canonical_integer(segment)
        if index is None or index < 0 or index >= len(value):
            return _MISSING
        return value[index]
    if is_dataclass(value) and not isinstance(value, type):
        if segment in value.__dataclass_fields__:
            return getattr(value, segment)
    return _MISSING


def _canonical_integer(value: str) -> int | None:
    if value == "0":
        return 0
    if value.startswith("-"):
        digits = value[1:]
        if digits and digits.isdigit() and digits != "0":
            return int(value)
        return None
    if value.isdigit() and not value.startswith("0"):
        return int(value)
    return None


def _field(value, name):
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def citation_instructions(catalog: Mapping) -> str:
    """Render citation rules from the same catalog used by validation."""
    aliases = catalog.get("aliases", {})
    return json.dumps(
        {
            "canonical_source_ids": list(catalog.get("canonical_source_ids", [])),
            "permitted_aliases": dict(aliases),
            "deterministic_path_rule": (
                "Use an exact full_results path; it is verified by traversal and "
                "normalized to deterministic:<path>. Invented fields, indices, "
                "and prefix lookalikes are invalid."
            ),
            "rule": "Use a canonical source ID or a permitted compatibility alias; invented IDs are invalid.",
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def serialize_packet(packet: AgentCandidatePacket | Mapping, *, pretty: bool = False) -> str:
    payload = packet.to_dict() if isinstance(packet, AgentCandidatePacket) else packet
    options = {
        "ensure_ascii": False,
        "sort_keys": True,
        "default": json_default,
    }
    if pretty:
        return json.dumps(payload, indent=2, **options)
    return json.dumps(payload, separators=(",", ":"), **options)


def deserialize_packet(serialized: str) -> dict:
    payload = json.loads(serialized)
    if not isinstance(payload, dict):
        raise TypeError("agent packet must deserialize to a JSON object")
    return payload


def _source_ids(value, key: str | None = None) -> list[str]:
    if isinstance(value, Mapping):
        result = []
        for raw_child_key, child_value in value.items():
            child_key = str(raw_child_key)
            if child_key == "source_id":
                result.extend(_ordered_ids([child_value]))
            elif child_key.endswith("source_ids") or child_key == "source_ids":
                result.extend(_source_ids(child_value, "source_ids"))
            else:
                result.extend(
                    _source_ids(
                        child_value,
                        key if key and key.endswith("source_ids") else child_key,
                    )
                )
        return _ordered_ids(result)
    if isinstance(value, (list, tuple)):
        result = []
        for item in value:
            if isinstance(item, str) and key and key.endswith("source_ids"):
                result.append(item)
            elif isinstance(item, (Mapping, list, tuple)):
                result.extend(_source_ids(item, key))
        return _ordered_ids(result)
    if is_dataclass(value) and not isinstance(value, type):
        result = []
        for field_name in value.__dataclass_fields__:
            result.extend(
                _source_ids(
                    getattr(value, field_name),
                    field_name,
                )
            )
        return _ordered_ids(result)
    if isinstance(value, str) and key and key.endswith("source_ids"):
        return [value]
    return []


def _ordered_ids(values) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if not isinstance(value, str) or not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
