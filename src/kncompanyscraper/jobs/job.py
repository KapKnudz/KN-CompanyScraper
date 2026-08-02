from abc import ABC, abstractmethod
from kncompanyscraper.models.company import Company


class Job(ABC):
    @abstractmethod
    def run(self, company: Company) -> None:
        ...