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

                CREATE TABLE IF NOT EXISTS sales_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    business_date TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    revenue REAL NOT NULL DEFAULT 0,
                    checks_count INTEGER NOT NULL DEFAULT 0,
                    average_check REAL NOT NULL DEFAULT 0,
                    hourly_json TEXT NOT NULL DEFAULT '{}',
                    payload_json TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    UNIQUE(agent_id, business_date, captured_at)
                );

                CREATE INDEX IF NOT EXISTS
                    idx_sales_snapshots_agent_date
                ON sales_snapshots(agent_id, business_date, captured_at);


                CREATE TABLE IF NOT EXISTS health_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    business_date TEXT NOT NULL,
                    calculated_at TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    factors_json TEXT NOT NULL,
                    revenue_delta REAL,
                    average_check_delta REAL,
                    UNIQUE(agent_id, business_date, calculated_at)
                );

                CREATE INDEX IF NOT EXISTS
                    idx_health_scores_agent_date
                ON health_scores(agent_id, business_date, calculated_at);
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
            self._ensure_column(
                connection,
                "sales_snapshots",
                "menu_json",
                "TEXT NOT NULL DEFAULT '{}'",
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

    def save_sales_snapshot(
        self,
        agent_id: str,
        payload: dict[str, Any],
    ) -> None:
        business_date = str(payload.get("business_date") or "")
        captured_at = str(payload.get("captured_at") or utc_now())
        revenue = float(payload.get("revenue") or 0)
        checks_count = int(payload.get("checks_count") or 0)
        average_check = float(payload.get("average_check") or 0)
        hourly = payload.get("hourly") or {}

        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO sales_snapshots (
                    agent_id,
                    business_date,
                    captured_at,
                    revenue,
                    checks_count,
                    average_check,
                    hourly_json,
                    menu_json,
                    payload_json,
                    received_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    business_date,
                    captured_at,
                    revenue,
                    checks_count,
                    average_check,
                    json.dumps(hourly, ensure_ascii=False),
                    json.dumps(
                        payload.get("menu") or {},
                        ensure_ascii=False,
                    ),
                    json.dumps(payload, ensure_ascii=False),
                    utc_now(),
                ),
            )

    def latest_sales_snapshot(
        self,
        agent_id: str,
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM sales_snapshots
                WHERE agent_id = ?
                ORDER BY captured_at DESC
                LIMIT 1
                """,
                (agent_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["hourly"] = json.loads(result.pop("hourly_json"))
        result["menu"] = json.loads(
            result.pop("menu_json") or "{}"
        )
        result["payload"] = json.loads(result.pop("payload_json"))
        return result

    def sales_history(
        self,
        agent_id: str,
        date_from: str,
        date_to: str,
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT s.*
                FROM sales_snapshots AS s
                INNER JOIN (
                    SELECT
                        business_date,
                        MAX(captured_at) AS captured_at
                    FROM sales_snapshots
                    WHERE agent_id = ?
                      AND business_date BETWEEN ? AND ?
                    GROUP BY business_date
                ) AS latest
                    ON latest.business_date = s.business_date
                   AND latest.captured_at = s.captured_at
                WHERE s.agent_id = ?
                ORDER BY s.business_date
                """,
                (agent_id, date_from, date_to, agent_id),
            ).fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["hourly"] = json.loads(item.pop("hourly_json"))
            item["menu"] = json.loads(
                item.pop("menu_json") or "{}"
            )
            item.pop("payload_json", None)
            result.append(item)
        return result

    def menu_sales_history(
        self,
        agent_id: str,
        date_from: str,
        date_to: str,
    ) -> list[dict[str, Any]]:
        snapshots = self.sales_history(agent_id, date_from, date_to)
        aggregated: dict[str, dict[str, Any]] = {}

        for snapshot in snapshots:
            menu = snapshot.get("menu") or {}
            columns = list(menu.get("columns") or [])
            rows = list(menu.get("rows") or [])

            for row in rows:
                values = dict(zip(columns, row))
                item_key = str(
                    values.get("item_id")
                    or values.get("item_name")
                    or ""
                )
                if not item_key:
                    continue

                item = aggregated.setdefault(
                    item_key,
                    {
                        "item_id": values.get("item_id"),
                        "item_name": values.get("item_name")
                        or "Без названия",
                        "quantity": 0.0,
                        "revenue": 0.0,
                    },
                )
                item["quantity"] += float(values.get("quantity") or 0)
                item["revenue"] += float(values.get("revenue") or 0)

        result = sorted(
            aggregated.values(),
            key=lambda item: item["revenue"],
            reverse=True,
        )
        total_revenue = sum(item["revenue"] for item in result)
        cumulative = 0.0

        for item in result:
            cumulative += item["revenue"]
            share = item["revenue"] / total_revenue * 100 if total_revenue else 0
            cumulative_share = cumulative / total_revenue * 100 if total_revenue else 0
            item["revenue_share"] = round(share, 2)
            item["cumulative_share"] = round(cumulative_share, 2)
            item["abc_class"] = (
                "A" if cumulative_share <= 80
                else "B" if cumulative_share <= 95
                else "C"
            )

        return result

    def save_health_score(
        self,
        agent_id: str,
        business_date: str,
        report: dict[str, Any],
    ) -> None:
        health = report.get("health") or {}
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO health_scores (
                    agent_id,
                    business_date,
                    calculated_at,
                    score,
                    status,
                    factors_json,
                    revenue_delta,
                    average_check_delta
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    business_date,
                    utc_now(),
                    int(health.get("score") or 0),
                    str(health.get("status") or "attention"),
                    json.dumps(
                        health.get("factors") or [],
                        ensure_ascii=False,
                    ),
                    health.get("revenue_delta"),
                    health.get("average_check_delta"),
                ),
            )

    def health_score_history(
        self,
        agent_id: str,
        date_from: str,
        date_to: str,
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT h.*
                FROM health_scores AS h
                INNER JOIN (
                    SELECT
                        business_date,
                        MAX(calculated_at) AS calculated_at
                    FROM health_scores
                    WHERE agent_id = ?
                      AND business_date BETWEEN ? AND ?
                    GROUP BY business_date
                ) AS latest
                    ON latest.business_date = h.business_date
                   AND latest.calculated_at = h.calculated_at
                WHERE h.agent_id = ?
                ORDER BY h.business_date
                """,
                (agent_id, date_from, date_to, agent_id),
            ).fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["factors"] = json.loads(
                item.pop("factors_json") or "[]"
            )
            result.append(item)
        return result

    def latest_health_score(
        self,
        agent_id: str,
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM health_scores
                WHERE agent_id = ?
                ORDER BY calculated_at DESC
                LIMIT 1
                """,
                (agent_id,),
            ).fetchone()

        if row is None:
            return None

        result = dict(row)
        result["factors"] = json.loads(
            result.pop("factors_json") or "[]"
        )
        return result


def previous_sales_snapshot(
    self,
    agent_id: str,
    captured_at: str,
) -> dict[str, Any] | None:
    with self.connect() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM sales_snapshots
            WHERE agent_id = ? AND captured_at < ?
            ORDER BY captured_at DESC LIMIT 1
            """,
            (agent_id, captured_at),
        ).fetchone()
    if row is None:
        return None
    result = dict(row)
    payload = json.loads(result.get("payload_json") or "{}")
    payload.setdefault("business_date", result.get("business_date"))
    payload.setdefault("captured_at", result.get("captured_at"))
    payload.setdefault("revenue", result.get("revenue"))
    payload.setdefault("checks_count", result.get("checks_count"))
    payload.setdefault("average_check", result.get("average_check"))
    return payload

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
