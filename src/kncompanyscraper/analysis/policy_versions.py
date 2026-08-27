"""Canonical persisted-analysis policy-version composition."""

FORWARD_SCENARIO_POLICY_VERSION = "forward-scenario-v3-net-debt-bridge"
FORWARD_RANKING_POLICY_VERSION = "forward-ranking-v1"
COMPARATIVE_CONFIDENCE_POLICY_VERSION = "comparative-confidence-v1"


def compose_policy_version(*versions: str) -> str:
    return "+".join(version for version in versions if version)


def comparative_ranking_policy_version() -> str:
    return compose_policy_version(
        FORWARD_RANKING_POLICY_VERSION,
        COMPARATIVE_CONFIDENCE_POLICY_VERSION,
    )
