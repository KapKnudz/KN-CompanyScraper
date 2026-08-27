from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ArticleAttachment:
    title: str
    url: str


@dataclass
class ScrapedArticle:
    company: str
    slug: str
    url: str
    title: str
    body: str
    published_at: datetime | None = None
    attachments: list[ArticleAttachment] = field(default_factory=list)
