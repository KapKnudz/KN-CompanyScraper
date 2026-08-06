from kncompanyscraper.analysis.agent.prompt_builder import AgentPromptBuilder


class AgentAnalysisService:
    def __init__(self, model_adapter, execution_boundary, prompt_builder=None):
        self.model_adapter = model_adapter
        self.execution_boundary = execution_boundary
        self.prompt_builder = prompt_builder or AgentPromptBuilder()

    def analyze(self, candidates: list) -> list:
        persisted = []
        for candidate in candidates:
            prompt = self.prompt_builder.build(candidate)
            response = self.model_adapter.generate(prompt)
            persisted.append(
                self.execution_boundary.persist_response(
                    response.output_text,
                    candidate,
                    created_by=response.model,
                    metadata={
                        "openai_response_id": response.response_id,
                        "usage": response.usage,
                    },
                )
            )
        return persisted
