"""Read-only size measurements for model input packets."""

from dataclasses import asdict, dataclass, field, is_dataclass
from hashlib import sha256
import json
from math import ceil
from typing import Mapping

from kncompanyscraper.analysis.agent.agent_packet import AgentCandidatePacket, serialize_packet
from kncompanyscraper.analysis.agent.json_support import json_default


@dataclass(frozen=True)
class PacketMeasurement:
    byte_count: int
    character_count: int
    document_count: int
    token_estimate: int
    section_sizes: dict[str, int] = field(default_factory=dict)


def measure_packet(
    packet: Mapping | object | str, *, pretty: bool = True
) -> PacketMeasurement:
    """Measure a packet without modifying it.

    The token value is deliberately a labelled estimate based on four
    characters per token. Exact provider usage belongs to the model adapter.
    """
    if isinstance(packet, str):
        serialized = packet
        payload = json.loads(packet)
    else:
        payload = packet.to_dict() if hasattr(packet, "to_dict") else (
            asdict(packet) if is_dataclass(packet) else packet
        )
        if isinstance(packet, AgentCandidatePacket):
            serialized = serialize_packet(packet, pretty=pretty)
        else:
            serialized = json.dumps(
                payload,
                ensure_ascii=False,
                indent=2 if pretty else None,
                separators=None if pretty else (",", ":"),
                sort_keys=True,
                default=json_default,
            )

    if not isinstance(payload, Mapping):
        raise TypeError("packet must serialize to a JSON object")

    evidence = payload.get("research_evidence") or payload
    documents = evidence.get("documents", []) if isinstance(evidence, Mapping) else []
    section_sizes = {
        key: len(
            json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
                default=json_default,
            )
        )
        for key, value in payload.items()
    }
    return measure_text(
        serialized,
        document_count=len(documents),
        section_sizes=section_sizes,
    )


def measure_text(
    serialized: str,
    *,
    document_count: int = 0,
    section_sizes: dict[str, int] | None = None,
) -> PacketMeasurement:
    """Measure already serialized model input text."""
    character_count = len(serialized)
    return PacketMeasurement(
        byte_count=len(serialized.encode("utf-8")),
        character_count=character_count,
        document_count=document_count,
        token_estimate=ceil(character_count / 4),
        section_sizes=section_sizes or {},
    )


def measure_adapter_input(
    serialized: str,
    *,
    document_count: int = 0,
    section_sizes: dict[str, int] | None = None,
    provider_character_limit: int | None = None,
    warning_threshold_characters: int | None = None,
) -> dict:
    """Measure the complete text handed to a model adapter.

    Unlike ``measure_packet``, this boundary is called after the adapter has
    added its wrapper and policy text.  The returned dictionary is suitable
    for persistence alongside an individual model attempt.
    """
    measurement = asdict(
        measure_text(
            serialized,
            document_count=document_count,
            section_sizes=section_sizes,
        )
    )
    measurement["provider_character_limit"] = provider_character_limit
    measurement["remaining_character_headroom"] = (
        provider_character_limit - measurement["character_count"]
        if provider_character_limit is not None
        else None
    )
    measurement["warning_threshold_characters"] = warning_threshold_characters
    measurement["input_sha256"] = sha256(serialized.encode("utf-8")).hexdigest()
    return measurement
