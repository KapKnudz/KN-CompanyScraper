@dataclass
class SkillResult:
    score: int
    confidence: int
    summary: str
    evidence: dict