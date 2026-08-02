from __future__ import annotations

import base64
import hashlib
import json
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

import pyodbc

from app.core.config import get_settings


class SqlServerError(RuntimeError):
    pass


@dataclass(frozen=True)
class SqlServerInfo:
    server_name: str
    database_name: str
    version: str


def _encode_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return {"__type__": "decimal", "value": str(value)}
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    if isinstance(value, UUID):
        return {"__type__": "uuid", "value": str(value)}
    if isinstance(value, bytes):
        return {
            "__type__": "bytes",
            "value": base64.b64encode(value).decode("ascii"),
        }
    return {"__type__": "string", "value": str(value)}


def _decode_value(value: Any) -> Any:
    if not isinstance(value, dict) or "__type__" not in value:
        return value
    kind = value.get("__type__")
    raw = value.get("value")
    if kind == "decimal":
        return Decimal(raw)
    if kind == "datetime":
        return datetime.fromisoformat(raw)
    if kind == "date":
        return date.fromisoformat(raw)
    if kind == "uuid":
        return UUID(raw)
    if kind == "bytes":
        return base64.b64decode(raw)
    return raw


class RelayCursor:
    def __init__(self, connection: "RelayConnection") -> None:
        self.connection = connection
        self.description: list[tuple[str]] = []
        self._rows: list[tuple[Any, ...]] = []
        self._position = 0

    def execute(self, sql: str, *params: Any) -> "RelayCursor":
        payload = self.connection.execute(sql, list(params))
        self.description = [(str(name),) for name in payload.get("columns", [])]
        self._rows = [
            tuple(_decode_value(value) for value in row)
            for row in payload.get("rows", [])
        ]
        self._position = 0
        return self

    def fetchall(self) -> list[tuple[Any, ...]]:
        rows = self._rows[self._position:]
        self._position = len(self._rows)
        return rows

    def fetchone(self) -> tuple[Any, ...] | None:
        if self._position >= len(self._rows):
            return None
        row = self._rows[self._position]
        self._position += 1
        return row

    def close(self) -> None:
        return None


class RelayConnection:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.cache_dir = Path(self.settings.tillypad_relay_cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def cursor(self) -> RelayCursor:
        return RelayCursor(self)

    def close(self) -> None:
        return None

    def _cache_path(self, body: bytes) -> Path:
        key = hashlib.sha256(body).hexdigest()
        return self.cache_dir / f"{key}.json"

    def _request(self, body: bytes) -> dict[str, Any]:
        s = self.settings
        url = s.tillypad_relay_url.rstrip("/") + "/v1/query"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        }
        if s.tillypad_relay_api_key:
            headers["X-Relay-Key"] = s.tillypad_relay_api_key

        request = Request(url, data=body, headers=headers, method="POST")
        with urlopen(request, timeout=s.tillypad_relay_timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def execute(self, sql: str, params: list[Any]) -> dict[str, Any]:
        request_payload = {
            "sql": sql,
            "params": [_encode_value(value) for value in params],
        }
        body = json.dumps(
            request_payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        cache_path = self._cache_path(body)
        errors: list[str] = []

        for attempt in range(self.settings.tillypad_relay_retries + 1):
            try:
                payload = self._request(body)
                if not payload.get("ok", False):
                    raise SqlServerError(payload.get("error") or "Ошибка Relay Agent")
                cache_path.write_text(
                    json.dumps(payload, ensure_ascii=False),
                    encoding="utf-8",
                )
                return payload
            except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError, SqlServerError) as exc:
                errors.append(str(exc))
                if attempt < self.settings.tillypad_relay_retries:
                    time.sleep(0.4 * (attempt + 1))

        if self.settings.tillypad_relay_allow_stale_cache and cache_path.exists():
            try:
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
                payload["served_from_cache"] = True
                return payload
            except (OSError, json.JSONDecodeError):
                pass

        raise SqlServerError(
            "Промежуточный сервис TillyPad недоступен. "
            + " | ".join(errors[-3:])
        )


class SqlServer:
    def __init__(self) -> None:
        self.settings = get_settings()

    def connection_string(self) -> str:
        s = self.settings
        if not s.tillypad_sql_user or not s.tillypad_sql_password:
            raise SqlServerError(
                "В .env не указаны TILLYPAD_SQL_USER и "
                "TILLYPAD_SQL_PASSWORD."
            )
        return (
            f"DRIVER={{{s.tillypad_sql_driver}}};"
            f"SERVER={s.tillypad_sql_server},{s.tillypad_sql_port};"
            f"DATABASE={s.tillypad_sql_database};"
            f"UID={s.tillypad_sql_user};"
            f"PWD={s.tillypad_sql_password};"
            f"Encrypt={s.tillypad_sql_encrypt};"
            f"TrustServerCertificate={s.tillypad_sql_trust_certificate};"
            f"Connection Timeout={s.tillypad_sql_timeout};"
        )

    @contextmanager
    def connect(self) -> Iterator[Any]:
        mode = self.settings.tillypad_connection_mode.strip().lower()
        if mode == "relay":
            connection = RelayConnection()
            try:
                yield connection
            finally:
                connection.close()
            return

        if mode != "direct":
            raise SqlServerError(
                "TILLYPAD_CONNECTION_MODE должен быть direct или relay."
            )

        try:
            connection = pyodbc.connect(self.connection_string())
        except pyodbc.Error as exc:
            raise SqlServerError(
                f"Не удалось подключиться к SQL Server: {exc}"
            ) from exc
        try:
            yield connection
        finally:
            connection.close()

    def info(self) -> SqlServerInfo:
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    CAST(@@SERVERNAME AS nvarchar(255)),
                    CAST(DB_NAME() AS nvarchar(255)),
                    CAST(@@VERSION AS nvarchar(max))
                """
            )
            row = cursor.fetchone()
        return SqlServerInfo(
            server_name=str(row[0]),
            database_name=str(row[1]),
            version=str(row[2]),
        )
