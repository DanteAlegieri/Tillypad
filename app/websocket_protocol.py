from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GatewayMessage(BaseModel):
    type: str
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str | None = None
    sent_at: str = Field(default_factory=utc_now_iso)
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentHelloPayload(BaseModel):
    agent_version: str
    hostname: str
    database_name: str | None = None
    capabilities: list[str] = Field(default_factory=list)


class QueryRequestPayload(BaseModel):
    query_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class QueryResultPayload(BaseModel):
    success: bool
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    error: str | None = None
    from_cache: bool = False


class HeartbeatPayload(BaseModel):
    status: Literal["online", "busy", "degraded"] = "online"
    queue_size: int = 0
    last_query_at: str | None = None
