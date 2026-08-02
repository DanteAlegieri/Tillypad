from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from .protocol import GatewayMessage
from .payload_codec import decode_payload


@dataclass
class AgentConnection:
    agent_id: str
    websocket: WebSocket
    pending: dict[str, asyncio.Future] = field(default_factory=dict)


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[str, AgentConnection] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self,
        agent_id: str,
        websocket: WebSocket,
    ) -> AgentConnection:
        await websocket.accept()
        connection = AgentConnection(agent_id, websocket)
        async with self._lock:
            old = self.connections.get(agent_id)
            self.connections[agent_id] = connection
        if old is not None:
            try:
                await old.websocket.close(code=4001)
            except Exception:
                pass
        return connection

    async def disconnect(self, agent_id: str) -> None:
        async with self._lock:
            connection = self.connections.pop(agent_id, None)
        if connection:
            for future in connection.pending.values():
                if not future.done():
                    future.cancel()

    def is_online(self, agent_id: str) -> bool:
        return agent_id in self.connections

    async def request(
        self,
        agent_id: str,
        query_name: str,
        parameters: dict[str, Any],
        timeout: float,
        *,
        bypass_cache: bool = False,
        cache_ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        connection = self.connections.get(agent_id)
        if connection is None:
            raise RuntimeError("Агент не подключён")

        message = GatewayMessage(
            type="query_request",
            agent_id=agent_id,
            payload={
                "query_name": query_name,
                "parameters": parameters,
                "bypass_cache": bypass_cache,
                "cache_ttl_seconds": cache_ttl_seconds,
            },
        )
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        connection.pending[message.request_id] = future
        try:
            await connection.websocket.send_text(
                message.model_dump_json()
            )
            return await asyncio.wait_for(future, timeout)
        finally:
            connection.pending.pop(message.request_id, None)

    async def control(
        self,
        agent_id: str,
        message_type: str,
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        connection = self.connections.get(agent_id)
        if connection is None:
            raise RuntimeError("Агент не подключён")

        message = GatewayMessage(
            type=message_type,
            agent_id=agent_id,
            payload=payload,
        )
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        connection.pending[message.request_id] = future
        try:
            await connection.websocket.send_text(
                message.model_dump_json()
            )
            return await asyncio.wait_for(future, timeout)
        finally:
            connection.pending.pop(message.request_id, None)

    def resolve(
        self,
        agent_id: str,
        message: GatewayMessage,
    ) -> bool:
        connection = self.connections.get(agent_id)
        if connection is None:
            return False
        future = connection.pending.get(message.request_id)
        if future is None or future.done():
            return False
        future.set_result(decode_payload(message.payload))
        return True
