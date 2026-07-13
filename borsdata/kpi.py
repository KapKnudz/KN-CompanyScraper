from dataclasses import dataclass


@dataclass
class Kpi:

    id: int
    name: str
    value: float