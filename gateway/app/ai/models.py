from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class ScoreFactor:
    key: str
    title: str
    weight: int
    score: float
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Recommendation:
    id: str
    agent: str
    priority: str
    title: str
    reason: str
    action: str
    expected_effect: str
    confidence: int
    evidence: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Event:
    level: str
    title: str
    text: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
