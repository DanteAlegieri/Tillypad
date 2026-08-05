from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import platform
import socket
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
from typing import Any

import websockets

from app.db.sql_server import SqlServer
from app.query_registry import QueryRegistry, QueryRegistryError
from app.query_cache import QueryCache
from app.payload_codec import encode_payload
from app.websocket_protocol import GatewayMessage
from app.agent_state import get_runtime_state, utc_now
from app.agent_config import reload_config


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
        self.cloud_sync_seconds = int(
            os.environ.get(
                "TILLYPAD_CLOUD_SYNC_SECONDS",
                "300",
            )
        )

        self.database = SqlServer()
        self.registry = QueryRegistry()
        self.cache = QueryCache(
            default_ttl_seconds=int(
                os.environ.get("TILLYPAD_QUERY_CACHE_TTL", "45")
            ),
            max_entries=int(
                os.environ.get("TILLYPAD_QUERY_CACHE_MAX", "256")
            ),
        )
        self.compress_threshold_bytes = int(
            os.environ.get(
                "TILLYPAD_WS_COMPRESS_THRESHOLD",
                str(64 * 1024),
            )
        )
        self.last_query_at: str | None = None
        self.state = get_runtime_state()
        self.state.update(
            version="17.0.0",
            agent_id=self.agent_id,
            gateway_url=self.gateway_url,
            service_status="running",
            gateway_status="disconnected",
            sql_status="configured",
        )

    def _reload_config_if_needed(self) -> None:
        data_dir = Path(
            os.environ.get(
                "RESTAURANTOS_DATA_DIR",
                os.getcwd(),
            )
        )
        marker = data_dir / "reload_config.request"

        config = reload_config()
        changed = (
            config.agent_id != self.agent_id
            or config.gateway_url != self.gateway_url
            or config.api_key != self.api_key
        )

        if marker.exists():
            changed = True
            try:
                marker.unlink()
            except OSError:
                pass

        if changed:
            old_agent_id = self.agent_id
            old_gateway = self.gateway_url

            self.agent_id = config.agent_id
            self.gateway_url = config.gateway_url
            self.api_key = config.api_key

            self.state.update(
                agent_id=self.agent_id,
                gateway_url=self.gateway_url,
                gateway_status="disconnected",
                last_error=None,
            )
            LOGGER.info(
                "Конфигурация перечитана: agent_id %s -> %s, "
                "gateway %s -> %s",
                old_agent_id,
                self.agent_id,
                old_gateway,
                self.gateway_url,
            )

    async def run_forever(self) -> None:
        delay = 2
        attempt = 0

        while True:
            self._reload_config_if_needed()
            attempt += 1
            self.state.update(
                gateway_status="connecting",
                reconnect_attempt=attempt,
            )
            try:
                await self._run_session()
                delay = 2
                attempt = 0
            except asyncio.CancelledError:
                self.state.update(
                    service_status="stopping",
                    gateway_status="disconnected",
                )
                raise
            except Exception as exc:
                error_text = f"{type(exc).__name__}: {exc}"
                self.state.update(
                    gateway_status="disconnected",
                    last_disconnected_at=utc_now(),
                    last_error=error_text,
                    reconnect_attempt=attempt,
                )
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
            ping_interval=15,
            ping_timeout=45,
            close_timeout=10,
            open_timeout=15,
            max_size=16 * 1024 * 1024,
        ) as websocket:
            self.state.update(
                gateway_status="connected",
                last_connected_at=utc_now(),
                last_error=None,
                reconnect_attempt=0,
            )
            LOGGER.info(
                "WebSocket подключён: %s, agent_id=%s",
                self.gateway_url,
                self.agent_id,
            )
            await self._send_hello(websocket)

            heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(websocket)
            )
            cloud_sync_task = asyncio.create_task(
                self._cloud_sync_loop(websocket)
            )
            try:
                async for raw_message in websocket:
                    await self._handle_message(websocket, raw_message)
            finally:
                self.state.update(
                    gateway_status="disconnected",
                    last_disconnected_at=utc_now(),
                )
                heartbeat_task.cancel()
                cloud_sync_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat_task
                with contextlib.suppress(asyncio.CancelledError):
                    await cloud_sync_task

    async def _send_hello(self, websocket: Any) -> None:
        message = GatewayMessage(
            type="agent_hello",
            agent_id=self.agent_id,
            payload={
                "agent_version": "31.1.0",
                "hostname": platform.node(),
                "database_name": os.environ.get(
                    "TILLYPAD_SQL_DATABASE",
                    "",
                ),
                "capabilities": [
                    "named_queries",
                    "query_cache",
                    "gzip_results",
                    "cache_control",
                    "heartbeat",
                    "automatic_reconnect",
                    "cloud_snapshots",
                    "application_heartbeat_ack",
                    "snapshot_ack",
                ],
                "allowed_queries": self.registry.names(),
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
                    "cache_entries": self.cache.size(),
                    "last_query_at": self.last_query_at,
                },
            )
            await websocket.send(message.model_dump_json())
            self.state.update(
                last_heartbeat_at=utc_now(),
                gateway_status="connected",
                cache_entries=self.cache.size(),
            )
            self._consume_local_commands()

    async def _cloud_sync_loop(self, websocket: Any) -> None:
        # Первая отправка почти сразу после подключения.
        await asyncio.sleep(3)

        try:
            await self._send_history_backfill(websocket, days=70)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOGGER.exception(
                "Не удалось выполнить загрузку истории: %s",
                exc,
            )

        while True:
            try:
                payload = await asyncio.to_thread(
                    self._build_cloud_snapshot,
                )
                message = GatewayMessage(
                    type="cloud_snapshot",
                    agent_id=self.agent_id,
                    payload=encode_payload(
                        payload,
                        threshold_bytes=self.compress_threshold_bytes,
                    ),
                )
                await websocket.send(message.model_dump_json())
                self.state.update(
                    last_cloud_sync_at=utc_now(),
                    sql_status="ok",
                    last_error=None,
                )
                LOGGER.info(
                    "Облачный снимок отправлен: дата=%s, выручка=%s, чеков=%s",
                    payload.get("business_date"),
                    payload.get("revenue"),
                    payload.get("checks_count"),
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.exception(
                    "Не удалось сформировать облачный снимок: %s",
                    exc,
                )
                self.state.update(
                    sql_status="error",
                    last_error=f"Cloud sync: {exc}",
                )

            await asyncio.sleep(max(30, self.cloud_sync_seconds))

    async def _send_history_backfill(
        self,
        websocket: Any,
        days: int = 70,
    ) -> None:
        today = date.today()
        LOGGER.info(
            "Начинаю загрузку истории за %s дней",
            days,
        )

        for offset in range(days - 1, 0, -1):
            business_day = today - timedelta(days=offset)
            payload = await asyncio.to_thread(
                self._build_cloud_snapshot_for_date,
                business_day,
                True,
            )
            message = GatewayMessage(
                type="cloud_snapshot",
                agent_id=self.agent_id,
                payload=encode_payload(
                    payload,
                    threshold_bytes=self.compress_threshold_bytes,
                ),
            )
            await websocket.send(message.model_dump_json())

            if offset % 10 == 0:
                LOGGER.info(
                    "История: отправлен день %s",
                    business_day.isoformat(),
                )

            await asyncio.sleep(0.08)

        LOGGER.info("Загрузка истории завершена")

    def _build_cloud_snapshot(self) -> dict[str, Any]:
        return self._build_cloud_snapshot_for_date(
            date.today(),
            False,
        )

    def _build_cloud_snapshot_for_date(
        self,
        business_day: date,
        historical: bool,
    ) -> dict[str, Any]:
        business_date = business_day.isoformat()
        period = {
            "date_from": business_date,
            "date_to": business_date,
        }

        summary_sql, summary_args = self.registry.build(
            "sales_summary",
            period,
        )
        summary = self._execute_query(summary_sql, summary_args)

        hourly_sql, hourly_args = self.registry.build(
            "sales_hourly",
            period,
        )
        hourly = self._execute_query(hourly_sql, hourly_args)

        menu_sql, menu_args = self.registry.build(
            "menu_items",
            period,
        )
        menu = self._execute_query(menu_sql, menu_args)

        revenue = 0
        checks_count = 0
        if summary.get("rows"):
            row = summary["rows"][0]
            columns = summary.get("columns") or []
            values = dict(zip(columns, row))
            revenue = values.get("revenue") or 0
            checks_count = values.get("checks_count") or 0

        average_check = (
            float(revenue) / int(checks_count)
            if checks_count
            else 0
        )

        return {
            "schema_version": 2,
            "agent_version": "31.1.0",
            "business_date": business_date,
            "captured_at": (
                f"{business_date}T23:59:59+00:00"
                if historical
                else utc_now()
            ),
            "revenue": revenue,
            "checks_count": checks_count,
            "average_check": round(average_check, 2),
            "hourly": {
                "columns": hourly.get("columns") or [],
                "rows": hourly.get("rows") or [],
            },
            "menu": {
                "columns": menu.get("columns") or [],
                "rows": menu.get("rows") or [],
            },
        }

    async def _handle_message(
        self,
        websocket: Any,
        raw_message: str,
    ) -> None:
        message = GatewayMessage.model_validate_json(raw_message)

        if message.type == "pong":
            self.state.update(
                gateway_status="connected",
                last_heartbeat_at=utc_now(),
                last_error=None,
            )
            return

        if message.type == "snapshot_ack":
            self.state.update(
                gateway_status="connected",
                last_error=None,
            )
            LOGGER.debug(
                "Gateway подтвердил облачный снимок: %s",
                message.payload.get("business_date"),
            )
            return

        if message.type == "snapshot_error":
            error = str(
                message.payload.get("error")
                or "Gateway не обработал снимок"
            )
            self.state.update(last_error=error)
            LOGGER.error("Gateway отклонил снимок: %s", error)
            return

        if message.type == "cache_clear":
            removed = self.cache.clear()
            response = GatewayMessage(
                type="control_result",
                request_id=message.request_id,
                agent_id=self.agent_id,
                payload={
                    "success": True,
                    "command": "cache_clear",
                    "removed_entries": removed,
                },
            )
            await websocket.send(response.model_dump_json())
            return

        if message.type == "capabilities_request":
            response = GatewayMessage(
                type="capabilities_result",
                request_id=message.request_id,
                agent_id=self.agent_id,
                payload={
                    "success": True,
                    "allowed_queries": self.registry.names(),
                    "capabilities": [
                        "named_queries",
                        "query_cache",
                        "gzip_results",
                        "cache_control",
                    ],
                },
            )
            await websocket.send(response.model_dump_json())
            return

        if message.type != "query_request":
            return

        query_name = str(message.payload.get("query_name") or "")
        parameters = dict(message.payload.get("parameters") or {})
        bypass_cache = bool(message.payload.get("bypass_cache", False))
        requested_ttl = message.payload.get("cache_ttl_seconds")
        cache_key = self.cache.build_key(query_name, parameters)

        try:
            cached = None if bypass_cache else self.cache.get(cache_key)
            if cached is not None:
                payload = {
                    **cached,
                    "from_cache": True,
                }
            else:
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
                ttl = (
                    int(requested_ttl)
                    if requested_ttl is not None
                    else None
                )
                self.cache.set(cache_key, payload, ttl)
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
        self.state.update(
            last_query_at=self.last_query_at,
            cache_entries=self.cache.size(),
            sql_status=("ok" if payload.get("success") else "error"),
            last_error=(
                None if payload.get("success")
                else str(payload.get("error") or "SQL query failed")
            ),
        )

        response = GatewayMessage(
            type="query_result",
            request_id=message.request_id,
            agent_id=self.agent_id,
            payload=encode_payload(
                payload,
                threshold_bytes=self.compress_threshold_bytes,
            ),
        )
        await websocket.send(response.model_dump_json())

    def _consume_local_commands(self) -> None:
        data_dir = Path(
            os.environ.get(
                "RESTAURANTOS_DATA_DIR",
                os.getcwd(),
            )
        )
        marker = data_dir / "clear_cache.request"
        if marker.exists():
            removed = self.cache.clear()
            try:
                marker.unlink()
            except OSError:
                pass
            self.state.update(cache_entries=0)
            LOGGER.info(
                "Локальная команда: кэш очищен, удалено %s записей",
                removed,
            )

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
