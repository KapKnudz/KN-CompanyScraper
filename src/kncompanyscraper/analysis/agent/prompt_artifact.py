"""Serialization and integrity helpers for resumable model-stage prompts."""

from __future__ import annotations

import json
from hashlib import sha256

from kncompanyscraper.analysis.agent.json_support import json_default
from kncompanyscraper.analysis.agent.prompt_builder import AgentPrompt


PROMPT_ARTIFACT_VERSION = "agent-stage-prompt-v1"


def serialize_prompt(prompt: AgentPrompt) -> str:
    """Return the immutable JSON representation stored in a job checkpoint."""
    payload = {
        "artifact_version": PROMPT_ARTIFACT_VERSION,
        "prompt": {
            "system": prompt.system,
            "user": prompt.user,
            "policy_name": prompt.policy_name,
            "policy_version": prompt.policy_version,
            "policy_sha256": prompt.policy_sha256,
            "output_schema": prompt.output_schema,
            "schema_name": prompt.schema_name,
            "packet_measurement": prompt.packet_measurement,
            "contract_version": getattr(prompt, "contract_version", ""),
        },
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=json_default,
    )


def prompt_sha256(artifact: str) -> str:
    return sha256(artifact.encode("utf-8")).hexdigest()


def deserialize_prompt(artifact: str) -> AgentPrompt:
    try:
        payload = json.loads(artifact)
        if payload.get("artifact_version") != PROMPT_ARTIFACT_VERSION:
            raise ValueError("unsupported prompt artifact version")
        prompt = payload["prompt"]
        return AgentPrompt(
            system=prompt["system"],
            user=prompt["user"],
            policy_name=prompt.get("policy_name", ""),
            policy_version=prompt.get("policy_version", ""),
            policy_sha256=prompt.get("policy_sha256", ""),
            output_schema=prompt.get("output_schema"),
            schema_name=prompt.get("schema_name", "stock_analysis"),
            packet_measurement=prompt.get("packet_measurement"),
            contract_version=prompt.get("contract_version", ""),
        )
    except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("malformed prompt artifact") from exc
