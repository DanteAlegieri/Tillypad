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

                CREATE TABLE IF NOT EXISTS restaurant_settings (
                    agent_id TEXT PRIMARY KEY,
                    daily_revenue_plan REAL NOT NULL DEFAULT 10000,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS finance_operations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    operation_date TEXT NOT NULL,
                    operation_type TEXT NOT NULL,
                    category TEXT NOT NULL,
                    amount REAL NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS
                    idx_finance_operations_agent_date
                ON finance_operations(agent_id, operation_date);
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
            self._ensure_column(
                connection,
                "sales_snapshots",
                "payments_json",
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


    def get_restaurant_settings(
        self,
        agent_id: str,
    ) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT agent_id, daily_revenue_plan, updated_at
                FROM restaurant_settings
                WHERE agent_id = ?
                """,
                (agent_id,),
            ).fetchone()

            if row is None:
                now = utc_now()
                connection.execute(
                    """
                    INSERT INTO restaurant_settings (
                        agent_id,
                        daily_revenue_plan,
                        updated_at
                    )
                    VALUES (?, ?, ?)
                    """,
                    (agent_id, 10000, now),
                )
                return {
                    "agent_id": agent_id,
                    "daily_revenue_plan": 10000,
                    "updated_at": now,
                }

        return dict(row)

    def update_restaurant_settings(
        self,
        agent_id: str,
        *,
        daily_revenue_plan: float,
    ) -> dict[str, Any]:
        plan = round(float(daily_revenue_plan), 2)
        if plan < 0:
            raise ValueError(
                "Дневной план не может быть отрицательным"
            )
        if plan > 100_000_000:
            raise ValueError(
                "Дневной план слишком большой"
            )

        updated_at = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO restaurant_settings (
                    agent_id,
                    daily_revenue_plan,
                    updated_at
                )
                VALUES (?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    daily_revenue_plan =
                        excluded.daily_revenue_plan,
                    updated_at =
                        excluded.updated_at
                """,
                (agent_id, plan, updated_at),
            )

        return {
            "agent_id": agent_id,
            "daily_revenue_plan": plan,
            "updated_at": updated_at,
        }

    def list_finance_operations(
        self,
        agent_id: str,
        date_from: str,
        date_to: str,
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    agent_id,
                    operation_date,
                    operation_type,
                    category,
                    amount,
                    description,
                    created_at,
                    updated_at
                FROM finance_operations
                WHERE agent_id = ?
                  AND operation_date BETWEEN ? AND ?
                ORDER BY operation_date DESC, id DESC
                """,
                (agent_id, date_from, date_to),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_finance_operation(
        self,
        agent_id: str,
        *,
        operation_date: str,
        operation_type: str,
        category: str,
        amount: float,
        description: str = "",
    ) -> dict[str, Any]:
        operation_type = str(operation_type).strip().lower()
        if operation_type not in {"income", "expense"}:
            raise ValueError("Некорректный тип финансовой операции")

        category = str(category).strip()
        if not category:
            raise ValueError("Категория обязательна")

        amount = round(float(amount), 2)
        if amount <= 0:
            raise ValueError("Сумма должна быть больше нуля")

        now = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO finance_operations (
                    agent_id,
                    operation_date,
                    operation_type,
                    category,
                    amount,
                    description,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    operation_date,
                    operation_type,
                    category,
                    amount,
                    str(description or "").strip(),
                    now,
                    now,
                ),
            )
            operation_id = int(cursor.lastrowid)

        return self.get_finance_operation(
            agent_id,
            operation_id,
        )

    def get_finance_operation(
        self,
        agent_id: str,
        operation_id: int,
    ) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM finance_operations
                WHERE agent_id = ?
                  AND id = ?
                """,
                (agent_id, operation_id),
            ).fetchone()

        if row is None:
            raise KeyError("Финансовая операция не найдена")
        return dict(row)

    def update_finance_operation(
        self,
        agent_id: str,
        operation_id: int,
        *,
        operation_date: str,
        operation_type: str,
        category: str,
        amount: float,
        description: str = "",
    ) -> dict[str, Any]:
        operation_type = str(operation_type).strip().lower()
        if operation_type not in {"income", "expense"}:
            raise ValueError("Некорректный тип финансовой операции")

        category = str(category).strip()
        if not category:
            raise ValueError("Категория обязательна")

        amount = round(float(amount), 2)
        if amount <= 0:
            raise ValueError("Сумма должна быть больше нуля")

        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE finance_operations
                SET operation_date = ?,
                    operation_type = ?,
                    category = ?,
                    amount = ?,
                    description = ?,
                    updated_at = ?
                WHERE agent_id = ?
                  AND id = ?
                """,
                (
                    operation_date,
                    operation_type,
                    category,
                    amount,
                    str(description or "").strip(),
                    utc_now(),
                    agent_id,
                    operation_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError("Финансовая операция не найдена")

        return self.get_finance_operation(
            agent_id,
            operation_id,
        )

    def delete_finance_operation(
        self,
        agent_id: str,
        operation_id: int,
    ) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM finance_operations
                WHERE agent_id = ?
                  AND id = ?
                """,
                (agent_id, operation_id),
            )
        return cursor.rowcount > 0

    @staticmethod
    def _clean_payment_name(value: Any) -> str:
        text = str(value or "").replace("\x00", "")
        # TillyPad may store a multilingual packed string.
        # Prefer the first readable Russian fragment.
        known = (
            "Банковские карты",
            "Безналичные",
            "Наличные",
            "Личный счет",
            "Личный счёт",
            "Питание Персонала",
            "Собственники",
            "Перевод на карту",
            "Бонусы",
            "QR код",
        )
        for name in known:
            if name.lower() in text.lower():
                return name
        text = " ".join(text.split())
        return text[:120] or "Неизвестный тип"

    @staticmethod
    def _payment_bucket(
        payment_type_id: str,
        name: str,
        is_cash: bool,
    ) -> tuple[str, str]:
        pid = str(payment_type_id or "").upper()
        lowered = name.lower()

        if (
            is_cash
            or pid == "3C80A070-E7A6-4F91-B1F5-7B8F1643B89D"
            or "налич" in lowered
        ):
            return ("cash", "Наличные")

        if (
            pid == "69E60F44-033D-CA4C-AA92-4A165CA93587"
            or "банковские карт" in lowered
        ):
            return ("card", "Банковские карты")

        if (
            pid == "11E9ED3D-35F3-474D-A85D-FBE6207E749A"
            or "qr" in lowered
            or "сбп" in lowered
        ):
            return ("qr", "QR / СБП")

        if (
            pid == "BD5A3A47-1B8C-AF4A-96EC-B413032F85AF"
            or "перевод" in lowered
        ):
            return ("transfer", "Перевод на карту")

        if (
            pid == "A2670451-A8A7-2E4F-AD2A-DC770FD4DE19"
            or "бонус" in lowered
        ):
            return ("bonus", "Бонусы")

        return ("other", "Прочие")

    def payment_summary_history(
        self,
        agent_id: str,
        date_from: str,
        date_to: str,
    ) -> dict[str, Any]:
        snapshots = self.sales_history(
            agent_id,
            date_from,
            date_to,
        )

        buckets: dict[str, dict[str, Any]] = {
            "cash": {"key": "cash", "name": "Наличные", "amount": 0.0, "checks_count": 0},
            "card": {"key": "card", "name": "Банковские карты", "amount": 0.0, "checks_count": 0},
            "qr": {"key": "qr", "name": "QR / СБП", "amount": 0.0, "checks_count": 0},
            "transfer": {"key": "transfer", "name": "Перевод на карту", "amount": 0.0, "checks_count": 0},
            "bonus": {"key": "bonus", "name": "Бонусы", "amount": 0.0, "checks_count": 0},
            "other": {"key": "other", "name": "Прочие", "amount": 0.0, "checks_count": 0},
        }
        raw_types: dict[str, dict[str, Any]] = {}

        for snapshot in snapshots:
            payments = snapshot.get("payments") or {}
            columns = list(payments.get("columns") or [])
            rows = list(payments.get("rows") or [])

            for row in rows:
                values = dict(zip(columns, row))
                payment_type_id = str(
                    values.get("payment_type_id") or ""
                )
                clean_name = self._clean_payment_name(
                    values.get("payment_type_name")
                )
                is_cash = bool(
                    int(values.get("is_cash") or 0)
                )
                amount = float(values.get("amount") or 0)
                checks_count = int(
                    values.get("checks_count") or 0
                )

                bucket_key, bucket_name = self._payment_bucket(
                    payment_type_id,
                    clean_name,
                    is_cash,
                )
                bucket = buckets[bucket_key]
                bucket["amount"] = round(
                    float(bucket["amount"]) + amount,
                    2,
                )
                bucket["checks_count"] = int(
                    bucket["checks_count"]
                ) + checks_count

                raw_key = payment_type_id or clean_name
                raw = raw_types.setdefault(
                    raw_key,
                    {
                        "payment_type_id": payment_type_id,
                        "name": clean_name,
                        "bucket": bucket_key,
                        "amount": 0.0,
                        "checks_count": 0,
                    },
                )
                raw["amount"] = round(
                    float(raw["amount"]) + amount,
                    2,
                )
                raw["checks_count"] = int(
                    raw["checks_count"]
                ) + checks_count

        result_buckets = [
            item
            for item in buckets.values()
            if float(item["amount"]) != 0
            or int(item["checks_count"]) != 0
        ]
        total = round(
            sum(float(item["amount"]) for item in result_buckets),
            2,
        )

        for item in result_buckets:
            item["share"] = (
                round(float(item["amount"]) / total * 100, 1)
                if total
                else 0.0
            )

        return {
            "total": total,
            "items": result_buckets,
            "raw_types": sorted(
                raw_types.values(),
                key=lambda item: float(item["amount"]),
                reverse=True,
            ),
            "days_with_payment_data": sum(
                1
                for snapshot in snapshots
                if (snapshot.get("payments") or {}).get("rows")
            ),
            "days_in_period": len(snapshots),
        }

    def finance_summary(
        self,
        agent_id: str,
        date_from: str,
        date_to: str,
    ) -> dict[str, Any]:
        sales = self.sales_history(
            agent_id,
            date_from,
            date_to,
        )
        revenue = round(
            sum(float(item.get("revenue") or 0) for item in sales),
            2,
        )

        operations = self.list_finance_operations(
            agent_id,
            date_from,
            date_to,
        )
        manual_income = round(
            sum(
                float(item["amount"])
                for item in operations
                if item["operation_type"] == "income"
            ),
            2,
        )
        expenses = round(
            sum(
                float(item["amount"])
                for item in operations
                if item["operation_type"] == "expense"
            ),
            2,
        )
        operating_result = round(
            revenue + manual_income - expenses,
            2,
        )

        payments = self.payment_summary_history(
            agent_id,
            date_from,
            date_to,
        )
        payments_total = float(payments.get("total") or 0)
        payments_difference = round(
            payments_total - revenue,
            2,
        )
        payments["difference_to_revenue"] = payments_difference
        payments["matches_revenue"] = abs(
            payments_difference
        ) <= 1.0

        categories: dict[str, float] = {}
        for item in operations:
            if item["operation_type"] != "expense":
                continue
            category = str(item["category"])
            categories[category] = round(
                categories.get(category, 0.0)
                + float(item["amount"]),
                2,
            )

        daily: dict[str, dict[str, float]] = {}
        for item in sales:
            day = str(item.get("business_date") or "")
            if not day:
                continue
            daily.setdefault(
                day,
                {"revenue": 0.0, "income": 0.0, "expenses": 0.0},
            )
            daily[day]["revenue"] = round(
                daily[day]["revenue"]
                + float(item.get("revenue") or 0),
                2,
            )

        for item in operations:
            day = str(item["operation_date"])
            daily.setdefault(
                day,
                {"revenue": 0.0, "income": 0.0, "expenses": 0.0},
            )
            key = (
                "income"
                if item["operation_type"] == "income"
                else "expenses"
            )
            daily[day][key] = round(
                daily[day][key]
                + float(item["amount"]),
                2,
            )

        margin = (
            round(operating_result / revenue * 100, 1)
            if revenue > 0
            else None
        )

        return {
            "agent_id": agent_id,
            "date_from": date_from,
            "date_to": date_to,
            "revenue": revenue,
            "manual_income": manual_income,
            "expenses": expenses,
            "operating_result": operating_result,
            "operating_margin": margin,
            "cost_of_goods": None,
            "gross_profit": None,
            "payments": payments,
            "categories": [
                {"category": key, "amount": value}
                for key, value in sorted(
                    categories.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
            ],
            "daily": [
                {"date": day, **values}
                for day, values in sorted(daily.items())
            ],
            "operations": operations,
        }


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
                    payments_json,
                    payload_json,
                    received_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    json.dumps(
                        payload.get("payments") or {},
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
        result["payments"] = json.loads(
            result.pop("payments_json", "{}") or "{}"
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
            item["payments"] = json.loads(
                item.pop("payments_json", "{}") or "{}"
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
                WHERE agent_id = ?
                  AND captured_at < ?
                ORDER BY captured_at DESC
                LIMIT 1
                """,
                (agent_id, captured_at),
            ).fetchone()

        if row is None:
            return None

        result = dict(row)
        payload = json.loads(
            result.get("payload_json") or "{}"
        )
        payload.setdefault(
            "business_date",
            result.get("business_date"),
        )
        payload.setdefault(
            "captured_at",
            result.get("captured_at"),
        )
        payload.setdefault(
            "revenue",
            result.get("revenue"),
        )
        payload.setdefault(
            "checks_count",
            result.get("checks_count"),
        )
        payload.setdefault(
            "average_check",
            result.get("average_check"),
        )
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
