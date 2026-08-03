from dataclasses import dataclass
from datetime import datetime


@dataclass
class CompanyProfile:
    company_id: int
    description: str | None
    business_model: str | None
    competitive_advantages: str | None
    management: dict | None
    updated_at: datetime | None
    website: str | None
    founded_year: int | None
    employees: int | None
    headquarters: str | None
    ceo: str | None
    board_members: list[str] | None