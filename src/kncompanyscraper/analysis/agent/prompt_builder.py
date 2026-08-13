from dataclasses import asdict, dataclass
from hashlib import sha256
from importlib import resources
import json

from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.output_schema import STOCK_ANALYSIS_OUTPUT_CONTRACT


@dataclass(frozen=True)
class AgentPrompt:
    system: str
    user: str
    policy_name: str = ""
    policy_version: str = ""
    policy_sha256: str = ""


class AgentPromptBuilder:
    POLICY_NAME = "nordic-case-investing-policy"
    POLICY_VERSION = "1.17.0"

    def build(self, candidate: AgentCandidate) -> AgentPrompt:
        policy = self._read_resource("resources/analyst_policy.md")
        workflow = self._read_resource("resources/analysis_workflow.md")
        template = self._read_resource("prompts/stock_analysis_prompt.md")
        policy_sha256 = sha256(f"{policy}\n\n{workflow}".encode("utf-8")).hexdigest()

        candidate_json = json.dumps(
            asdict(candidate),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        output_contract = json.dumps(
            STOCK_ANALYSIS_OUTPUT_CONTRACT,
            ensure_ascii=False,
            indent=2,
        )

        return AgentPrompt(
            system=(
                "# Policy provenance\n\n"
                f"- Name: `{self.POLICY_NAME}`\n"
                f"- Version: `{self.POLICY_VERSION}`\n"
                f"- SHA-256: `{policy_sha256}`\n\n"
                f"{policy}\n\n{workflow}"
            ),
            user=template.format(
                candidate_json=candidate_json,
                output_contract=output_contract,
            ),
            policy_name=self.POLICY_NAME,
            policy_version=self.POLICY_VERSION,
            policy_sha256=policy_sha256,
        )

    @staticmethod
    def _read_resource(relative_path: str) -> str:
        root = resources.files("kncompanyscraper.analysis.agent")
        return root.joinpath(*relative_path.split("/")).read_text(encoding="utf-8").strip()
