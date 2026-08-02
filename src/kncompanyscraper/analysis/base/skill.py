from abc import ABC, abstractmethod

class Skill(ABC):

    @property
    @abstractmethod
    def name(self):
        ...

    @abstractmethod
    def run(self, company):
        """
        Returns this skill's computed result (e.g. FinancialResult, ValuationResult) —
        no score or summary. Interpretation happens later, once all skills' evidence
        is combined.
        """