from dataclasses import asdict, dataclass
from hashlib import sha256
from importlib import resources
import json

from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.agent_packet import (
    AgentCandidatePacket,
    serialize_packet,
)
from kncompanyscraper.analysis.agent.packet_measurement import measure_packet
from kncompanyscraper.analysis.agent.output_schema import (
    QUALITATIVE_STOCK_ANALYSIS_OUTPUT_CONTRACT,
    qualitative_stock_analysis_json_schema,
)
from kncompanyscraper.analysis.policy_versions import THESIS_CALIBRATION_POLICY_VERSION


@dataclass(frozen=True)
class AgentPrompt:
    system: str
    user: str
    policy_name: str = ""
    policy_version: str = ""
    policy_sha256: str = ""
    output_schema: dict | None = None
    schema_name: str = "stock_analysis"
    packet_measurement: dict | None = None
    contract_version: str = ""


class AgentPromptBuilder:
    POLICY_NAME = "nordic-case-investing-policy"
    POLICY_VERSION = "1.28.0"
    CONTRACT_VERSION = "qualitative-stage-prompt-v3"

    def build(self, candidate: AgentCandidate) -> AgentPrompt:
        policy = self._read_resource("resources/analyst_policy.md")
        workflow = self._read_resource("resources/analysis_workflow.md")
        template = self._read_resource("prompts/stock_analysis_prompt.md")
        policy_sha256 = sha256(f"{policy}\n\n{workflow}".encode("utf-8")).hexdigest()

        packet = AgentCandidatePacket.from_candidate(candidate)
        candidate_json = serialize_packet(packet)
        output_contract = json.dumps(
            QUALITATIVE_STOCK_ANALYSIS_OUTPUT_CONTRACT,
            ensure_ascii=False,
            indent=2,
        )
        return AgentPrompt(
            system=(
                "# Policy provenance\n\n"
                f"- Name: `{self.POLICY_NAME}`\n"
                f"- Version: `{self.POLICY_VERSION}`\n"
                f"- Thesis calibration: `{THESIS_CALIBRATION_POLICY_VERSION}`\n"
                f"- SHA-256: `{policy_sha256}`\n\n"
                f"{policy}\n\n{workflow}"
                "\n\n# Evidence catalog\n\n"
                "Use the single `evidence_catalog` in the candidate packet for every "
                "citation and structured source ID. For deterministic values, cite "
                "the exact supplied path beginning with `full_results.`; the execution "
                "boundary verifies it by safe traversal and normalizes it to a "
                "canonical `deterministic:<path>` ID. Never invent, abbreviate, or "
                "extend a path with a nonexistent field or index."
            ),
            user=template.format(
                candidate_json=candidate_json,
                output_contract=output_contract,
            ),
            policy_name=self.POLICY_NAME,
            policy_version=self.POLICY_VERSION,
            policy_sha256=policy_sha256,
            output_schema=qualitative_stock_analysis_json_schema(),
            packet_measurement=asdict(measure_packet(packet, pretty=False)),
            contract_version=self.CONTRACT_VERSION,
        )

    @staticmethod
    def _read_resource(relative_path: str) -> str:
        root = resources.files("kncompanyscraper.analysis.agent")
        return root.joinpath(*relative_path.split("/")).read_text(encoding="utf-8").strip()
