from dataclasses import dataclass, field
from typing import Any

@dataclass(slots=True)
class BrainReason:
    title: str
    value: str
    impact: str
    score: int

@dataclass(slots=True)
class DecisionCard:
    id: str
    priority: str
    title: str
    action: str
    expected_effect: str
    confidence: int
    reasons: list[BrainReason] = field(default_factory=list)

@dataclass(slots=True)
class TimelineEvent:
    time: str
    level: str
    title: str
    text: str

@dataclass(slots=True)
class BrainReport:
    pulse_score: int
    pulse_label: str
    pulse_trend: str
    decision: DecisionCard
    timeline: list[TimelineEvent]
    changes: list[dict[str, Any]]
