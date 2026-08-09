from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ResearchDocument:
    id: int | None
    company_id: int
    document_type: str
    title: str
    url: str
    published_at: datetime | None
    text: str
    source_release_url: str | None = None
    metadata: dict = field(default_factory=dict)
