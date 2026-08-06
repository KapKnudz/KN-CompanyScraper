import json
from dataclasses import asdict, dataclass
from importlib import resources

from kncompanyscraper.analysis.agent.agent_candidate import AgentCandidate
from kncompanyscraper.analysis.agent.output_schema import STOCK_ANALYSIS_OUTPUT_CONTRACT


@dataclass(frozen=True)
class AgentPrompt:
    system: str
    user: str


class AgentPromptBuilder:
    def build(self, candidate: AgentCandidate) -> AgentPrompt:
        policy = self._read_resource("resources/analyst_policy.md")
        workflow = self._read_resource("resources/analysis_workflow.md")
        template = self._read_resource("prompts/stock_analysis_prompt.md")

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
            system=f"{policy}\n\n{workflow}",
            user=template.format(
                candidate_json=candidate_json,
                output_contract=output_contract,
            ),
        )

    @staticmethod
    def _read_resource(relative_path: str) -> str:
        root = resources.files("kncompanyscraper.analysis.agent")
        return root.joinpath(*relative_path.split("/")).read_text(encoding="utf-8").strip()
