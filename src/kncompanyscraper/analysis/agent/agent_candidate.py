from dataclasses import dataclass, field


@dataclass
class AgentCandidate:
    rank: int
    company_id: int
    ticker: str
    name: str

    total_score: float = 0.0
    score_breakdown: dict = field(default_factory=dict)
    data_quality: str = "medium"
    flags: list[str] = field(default_factory=list)
    candidate_reason: str | None = None
    positives: list[str] = field(default_factory=list)
    negatives: list[str] = field(default_factory=list)
    missing_data: list[str] = field(default_factory=list)

    # Raw skill results — available to the LLM for deeper reasoning
    full_results: dict = field(default_factory=dict)
