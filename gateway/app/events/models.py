from __future__ import annotations
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from .types import EventType, EventSeverity, EventSource, EventStatus

def utc_now()->str:
    return datetime.now(timezone.utc).isoformat()

@dataclass(slots=True)
class Snapshot:
    id:str
    agent_id:str
    business_date:str
    created_at:str
    revenue:float
    orders:int
    average_check:float
    raw_payload:dict[str,Any]=field(default_factory=dict)

    @classmethod
    def from_payload(cls, agent_id:str, payload:dict[str,Any])->"Snapshot":
        return cls(
            id=str(payload.get("snapshot_id") or uuid4()),
            agent_id=agent_id,
            business_date=str(payload.get("business_date") or ""),
            created_at=str(payload.get("captured_at") or utc_now()),
            revenue=float(payload.get("revenue") or 0),
            orders=int(payload.get("checks_count") or 0),
            average_check=float(payload.get("average_check") or 0),
            raw_payload=payload,
        )

@dataclass(slots=True)
class Event:
    id:str
    snapshot_id:str
    agent_id:str
    event_type:EventType
    severity:EventSeverity
    source:EventSource
    title:str
    description:str
    payload:dict[str,Any]
    score:int
    status:EventStatus
    created_at:str
    acknowledged_at:str|None=None
    resolved_at:str|None=None

    @classmethod
    def create(cls, **kwargs)->"Event":
        return cls(
            id=str(uuid4()),
            status=EventStatus.NEW,
            created_at=utc_now(),
            payload=kwargs.pop("payload",{}),
            score=max(0,min(100,int(kwargs.pop("score",50)))),
            **kwargs,
        )

    def to_dict(self)->dict[str,Any]:
        d=asdict(self)
        for key in ("event_type","severity","source","status"):
            d[key]=getattr(self,key).value
        return d
