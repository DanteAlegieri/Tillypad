from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GatewayStorage:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    api_key_hash TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT,
                    last_status TEXT,
                    hostname TEXT,
                    database_name TEXT,
                    agent_version TEXT
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column(
                connection,
                "agents",
                "last_query_at",
                "TEXT",
            )
            self._ensure_column(
                connection,
                "agents",
                "cache_entries",
                "INTEGER",
            )
            self._ensure_column(
                connection,
                "agents",
                "capabilities_json",
                "TEXT",
            )
            self._ensure_column(
                connection,
                "agents",
                "allowed_queries_json",
                "TEXT",
            )

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        sql_type: str,
    ) -> None:
        columns = {
            row["name"]
            for row in connection.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()
        }
        if column not in columns:
            connection.execute(
                f"ALTER TABLE {table} "
                f"ADD COLUMN {column} {sql_type}"
            )

    @staticmethod
    def hash_key(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def create_agent(
        self,
        agent_id: str,
        name: str,
    ) -> dict[str, str]:
        api_key = secrets.token_urlsafe(48)
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO agents (
                    agent_id,
                    name,
                    api_key_hash,
                    enabled,
                    created_at
                )
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    name = excluded.name,
                    api_key_hash = excluded.api_key_hash,
                    enabled = 1
                """,
                (
                    agent_id,
                    name,
                    self.hash_key(api_key),
                    utc_now(),
                ),
            )
        return {
            "agent_id": agent_id,
            "name": name,
            "api_key": api_key,
        }

    def authenticate(self, agent_id: str, api_key: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT api_key_hash, enabled
                FROM agents
                WHERE agent_id = ?
                """,
                (agent_id,),
            ).fetchone()
        if row is None or not row["enabled"]:
            return False
        return secrets.compare_digest(
            row["api_key_hash"],
            self.hash_key(api_key),
        )

    def update_seen(
        self,
        agent_id: str,
        *,
        status: str,
        hostname: str | None = None,
        database_name: str | None = None,
        agent_version: str | None = None,
        last_query_at: str | None = None,
        cache_entries: int | None = None,
        capabilities: list[str] | None = None,
        allowed_queries: list[str] | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE agents
                SET last_seen_at = ?,
                    last_status = ?,
                    hostname = COALESCE(?, hostname),
                    database_name = COALESCE(?, database_name),
                    agent_version = COALESCE(?, agent_version),
                    last_query_at = COALESCE(?, last_query_at),
                    cache_entries = COALESCE(?, cache_entries),
                    capabilities_json = COALESCE(?, capabilities_json),
                    allowed_queries_json = COALESCE(?, allowed_queries_json)
                WHERE agent_id = ?
                """,
                (
                    utc_now(),
                    status,
                    hostname,
                    database_name,
                    agent_version,
                    last_query_at,
                    cache_entries,
                    (
                        json.dumps(capabilities, ensure_ascii=False)
                        if capabilities is not None
                        else None
                    ),
                    (
                        json.dumps(allowed_queries, ensure_ascii=False)
                        if allowed_queries is not None
                        else None
                    ),
                    agent_id,
                ),
            )

    def list_agents(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    agent_id,
                    name,
                    enabled,
                    created_at,
                    last_seen_at,
                    last_status,
                    hostname,
                    database_name,
                    agent_version,
                    last_query_at,
                    cache_entries,
                    capabilities_json,
                    allowed_queries_json
                FROM agents
                ORDER BY name, agent_id
                """
            ).fetchall()
        return [dict(row) for row in rows]
