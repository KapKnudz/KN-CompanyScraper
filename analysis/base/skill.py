from abc import ABC, abstractmethod

class Skill(ABC):

    @property
    @abstractmethod
    def name(self):
        ...

    @abstractmethod
    def run(self, company):
        """
        Returns SkillResult
        """