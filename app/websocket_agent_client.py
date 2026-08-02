from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import platform
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import websockets

from app.db.sql_server import SqlServer
from app.query_registry import QueryRegistry, QueryRegistryError
from app.websocket_protocol import GatewayMessage


LOGGER = logging.getLogger("gastrodom.websocket_agent")


class WebSocketAgentClient:
    def __init__(self) -> None:
        self.gateway_url = os.environ.get(
            "TILLYPAD_WS_GATEWAY_URL",
            "ws://127.0.0.1:8020/ws/agent",
        )
        self.api_key = os.environ.get(
            "TILLYPAD_WS_API_KEY",
            "",
        )
        self.agent_id = os.environ.get(
            "TILLYPAD_AGENT_ID",
            socket.gethostname(),
        )
        self.heartbeat_seconds = int(
            os.environ.get("TILLYPAD_WS_HEARTBEAT", "20")
        )
        self.reconnect_max_seconds = int(
            os.environ.get("TILLYPAD_WS_RECONNECT_MAX", "60")
        )

        self.database = SqlServer()
        self.registry = QueryRegistry()
        self.last_query_at: str | None = None

    async def run_forever(self) -> None:
        delay = 2

        while True:
            try:
                await self._run_session()
                delay = 2
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.exception(
                    "WebSocket-сессия завершилась с ошибкой: %s",
                    exc,
                )

            await asyncio.sleep(delay)
            delay = min(delay * 2, self.reconnect_max_seconds)

    async def _run_session(self) -> None:
        headers = {
            "X-Relay-Key": self.api_key,
            "X-Agent-ID": self.agent_id,
        }

        async with websockets.connect(
            self.gateway_url,
            additional_headers=headers,
            ping_interval=None,
            close_timeout=10,
            max_size=16 * 1024 * 1024,
        ) as websocket:
            await self._send_hello(websocket)

            heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(websocket)
            )
            try:
                async for raw_message in websocket:
                    await self._handle_message(websocket, raw_message)
            finally:
                heartbeat_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat_task

    async def _send_hello(self, websocket: Any) -> None:
        message = GatewayMessage(
            type="agent_hello",
            agent_id=self.agent_id,
            payload={
                "agent_version": "15.2.0",
                "hostname": platform.node(),
                "database_name": os.environ.get(
                    "TILLYPAD_SQL_DATABASE",
                    "",
                ),
                "capabilities": [
                    "named_queries",
                    "heartbeat",
                    "automatic_reconnect",
                ],
            },
        )
        await websocket.send(message.model_dump_json())

    async def _heartbeat_loop(self, websocket: Any) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_seconds)
            message = GatewayMessage(
                type="heartbeat",
                agent_id=self.agent_id,
                payload={
                    "status": "online",
                    "queue_size": 0,
                    "last_query_at": self.last_query_at,
                },
            )
            await websocket.send(message.model_dump_json())

    async def _handle_message(
        self,
        websocket: Any,
        raw_message: str,
    ) -> None:
        message = GatewayMessage.model_validate_json(raw_message)

        if message.type != "query_request":
            return

        query_name = str(message.payload.get("query_name") or "")
        parameters = dict(message.payload.get("parameters") or {})

        try:
            sql, args = self.registry.build(query_name, parameters)
            result = await asyncio.to_thread(
                self._execute_query,
                sql,
                args,
            )
            payload = {
                "success": True,
                **result,
                "error": None,
                "from_cache": False,
            }
        except QueryRegistryError as exc:
            payload = {
                "success": False,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "error": str(exc),
                "from_cache": False,
            }
        except Exception as exc:
            LOGGER.exception("Ошибка выполнения запроса %s", query_name)
            payload = {
                "success": False,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "error": str(exc),
                "from_cache": False,
            }

        self.last_query_at = datetime.now(timezone.utc).isoformat()

        response = GatewayMessage(
            type="query_result",
            request_id=message.request_id,
            agent_id=self.agent_id,
            payload=payload,
        )
        await websocket.send(response.model_dump_json())

    def _execute_query(
        self,
        sql: str,
        args: list[Any],
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, *args)
            columns = [column[0] for column in cursor.description]
            rows = [
                [
                    self._json_safe(value)
                    for value in row
                ]
                for row in cursor.fetchall()
            ]

        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
        }

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        if isinstance(value, bytes):
            return value.hex()
        try:
            json.dumps(value)
            return value
        except TypeError:
            return str(value)


async def main() -> None:
    client = WebSocketAgentClient()
    await client.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
