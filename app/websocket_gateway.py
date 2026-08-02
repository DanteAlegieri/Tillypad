from __future__ import annotations

import asyncio
import contextlib
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.websocket_protocol import GatewayMessage


app = FastAPI(
    title="Gastrodom WebSocket Gateway",
    version="15.2.0",
)


@dataclass
class AgentConnection:
    agent_id: str
    websocket: WebSocket
    connected_at: str
    last_seen_at: str
    metadata: dict[str, Any] = field(default_factory=dict)


class QueryRequest(BaseModel):
    query_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = 30


class GatewayState:
    def __init__(self) -> None:
        self.agents: dict[str, AgentConnection] = {}
        self.pending: dict[str, asyncio.Future] = {}
        self.lock = asyncio.Lock()

    async def register(
        self,
        agent_id: str,
        websocket: WebSocket,
    ) -> AgentConnection:
        now = datetime.now(timezone.utc).isoformat()
        connection = AgentConnection(
            agent_id=agent_id,
            websocket=websocket,
            connected_at=now,
            last_seen_at=now,
        )
        async with self.lock:
            old = self.agents.get(agent_id)
            self.agents[agent_id] = connection

        if old is not None:
            with contextlib.suppress(Exception):
                await old.websocket.close(
                    code=4001,
                    reason="Новое соединение агента",
                )
        return connection

    async def unregister(
        self,
        agent_id: str,
        websocket: WebSocket,
    ) -> None:
        async with self.lock:
            current = self.agents.get(agent_id)
            if current and current.websocket is websocket:
                self.agents.pop(agent_id, None)

    async def resolve(self, message: GatewayMessage) -> None:
        future = self.pending.pop(message.request_id, None)
        if future is not None and not future.done():
            future.set_result(message.payload)


state = GatewayState()


def verify_api_key(value: str | None) -> None:
    expected = os.environ.get("TILLYPAD_WS_API_KEY", "")
    if not expected or value != expected:
        raise HTTPException(status_code=401, detail="Неверный API-ключ")


@app.websocket("/ws/agent")
async def agent_socket(
    websocket: WebSocket,
) -> None:
    api_key = websocket.headers.get("x-relay-key")
    agent_id = websocket.headers.get("x-agent-id")

    expected = os.environ.get("TILLYPAD_WS_API_KEY", "")
    if not expected or api_key != expected or not agent_id:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    connection = await state.register(agent_id, websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            message = GatewayMessage.model_validate_json(raw)
            connection.last_seen_at = datetime.now(
                timezone.utc
            ).isoformat()

            if message.type == "agent_hello":
                connection.metadata = message.payload
            elif message.type == "heartbeat":
                connection.metadata["heartbeat"] = message.payload
            elif message.type == "query_result":
                await state.resolve(message)
    except WebSocketDisconnect:
        pass
    finally:
        await state.unregister(agent_id, websocket)


@app.get("/v1/agents")
async def list_agents(
    x_relay_key: str | None = Header(default=None),
) -> dict[str, Any]:
    verify_api_key(x_relay_key)
    return {
        "agents": [
            {
                "agent_id": connection.agent_id,
                "connected_at": connection.connected_at,
                "last_seen_at": connection.last_seen_at,
                "metadata": connection.metadata,
            }
            for connection in state.agents.values()
        ]
    }


@app.get("/v1/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "gateway_version": "15.2.0",
        "online_agents": len(state.agents),
    }


@app.post("/v1/agents/{agent_id}/query")
async def run_query(
    agent_id: str,
    request: QueryRequest,
    x_relay_key: str | None = Header(default=None),
) -> dict[str, Any]:
    verify_api_key(x_relay_key)

    connection = state.agents.get(agent_id)
    if connection is None:
        raise HTTPException(
            status_code=503,
            detail="Агент не подключён",
        )

    request_id = str(uuid4())
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    state.pending[request_id] = future

    message = GatewayMessage(
        type="query_request",
        request_id=request_id,
        agent_id=agent_id,
        payload={
            "query_name": request.query_name,
            "parameters": request.parameters,
        },
    )

    try:
        await connection.websocket.send_text(
            message.model_dump_json()
        )
        result = await asyncio.wait_for(
            future,
            timeout=max(1, min(request.timeout_seconds, 120)),
        )
        return result
    except asyncio.TimeoutError as exc:
        state.pending.pop(request_id, None)
        raise HTTPException(
            status_code=504,
            detail="Агент не ответил вовремя",
        ) from exc
