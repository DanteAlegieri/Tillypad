from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Recommendation:
    code: str
    source: str
    title: str
    action: str
    reason: str
    priority: str = "medium"
    confidence: float = 0.5
    expected_effect: str = ""
    route: str = ""
    entity_name: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "source": self.source,
            "title": self.title,
            "action": self.action,
            "reason": self.reason,
            "priority": self.priority,
            "confidence": round(self.confidence * 100),
            "expected_effect": self.expected_effect,
            "route": self.route,
            "entity_name": self.entity_name,
            "metrics": self.metrics,
        }
