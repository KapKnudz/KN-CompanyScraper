import json
import re
from pathlib import Path

from kncompanyscraper.analysis.agent.prompt_builder import AgentPromptBuilder


class AgentPromptExporter:
    def __init__(self, prompt_builder=None):
        self.prompt_builder = prompt_builder or AgentPromptBuilder()

    def export(self, candidates: list, output_dir: Path) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []

        for candidate in candidates:
            prompt = self.prompt_builder.build(candidate)
            ticker = re.sub(r"[^A-Za-z0-9_-]+", "-", candidate.ticker).strip("-") or "company"
            path = output_dir / f"{candidate.rank:03d}-{candidate.company_id}-{ticker}.json"
            export_prompt(
                prompt,
                path,
                company_id=candidate.company_id,
                ticker=candidate.ticker,
            )
            paths.append(path)

        return paths


def export_prompt(prompt, path: Path, **metadata) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **metadata,
        "policy_name": prompt.policy_name,
        "policy_version": prompt.policy_version,
        "policy_sha256": prompt.policy_sha256,
        "system": prompt.system,
        "user": prompt.user,
        "schema_name": prompt.schema_name,
        "output_schema": prompt.output_schema,
    }
    if prompt.packet_measurement is not None:
        payload["packet_measurement"] = prompt.packet_measurement
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return path
