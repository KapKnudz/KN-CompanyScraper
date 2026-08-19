from enum import Enum


class DataQuality(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RankingModel(str, Enum):
    GENERAL = "general"
    BANK = "bank"
    PROPERTY = "property"
