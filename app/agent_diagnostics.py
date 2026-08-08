from __future__ import annotations

import json
import os
import socket
import ssl
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pyodbc


@dataclass
class CheckResult:
    name: str
    ok: bool
    message: str
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_env_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def test_sql(settings: dict[str, str]) -> CheckResult:
    started = time.perf_counter()
    try:
        server = settings.get("TILLYPAD_SQL_SERVER", "127.0.0.1")
        port = settings.get("TILLYPAD_SQL_PORT", "1433")
        database = settings.get("TILLYPAD_SQL_DATABASE", "")
        user = settings.get("TILLYPAD_SQL_USER", "")
        password = settings.get("TILLYPAD_SQL_PASSWORD", "")
        driver = settings.get(
            "TILLYPAD_SQL_DRIVER",
            "ODBC Driver 18 for SQL Server",
        )
        encrypt = settings.get("TILLYPAD_SQL_ENCRYPT", "no")
        trust = settings.get("TILLYPAD_SQL_TRUST_CERTIFICATE", "yes")
        timeout = int(settings.get("TILLYPAD_SQL_TIMEOUT", "10"))

        connection_string = (
            f"DRIVER={{{driver}}};"
            f"SERVER={server},{port};"
            f"DATABASE={database};"
            f"UID={user};PWD={password};"
            f"Encrypt={encrypt};"
            f"TrustServerCertificate={trust};"
            f"Connection Timeout={timeout};"
        )
        with pyodbc.connect(connection_string) as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT DB_NAME(), GETDATE(), "
                "(SELECT COUNT_BIG(*) FROM dbo.tp_Checks)"
            )
            db_name, server_time, checks = cursor.fetchone()

        elapsed = int((time.perf_counter() - started) * 1000)
        return CheckResult(
            name="SQL Server",
            ok=True,
            message=(
                f"База {db_name}; серверное время {server_time}; "
                f"чеков {checks}"
            ),
            duration_ms=elapsed,
        )
    except Exception as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        return CheckResult(
            name="SQL Server",
            ok=False,
            message=str(exc),
            duration_ms=elapsed,
        )


def test_gateway(settings: dict[str, str]) -> CheckResult:
    started = time.perf_counter()
    try:
        url = settings.get("TILLYPAD_WS_GATEWAY_URL", "")
        if not url:
            raise ValueError("Адрес Gateway не указан")

        parsed = urlparse(url)
        if parsed.scheme not in {"ws", "wss"}:
            raise ValueError("Адрес должен начинаться с ws:// или wss://")

        host = parsed.hostname
        if not host:
            raise ValueError("Не удалось определить адрес сервера")

        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        with socket.create_connection((host, port), timeout=8) as sock:
            if parsed.scheme == "wss":
                context = ssl.create_default_context()
                with context.wrap_socket(sock, server_hostname=host):
                    pass

        elapsed = int((time.perf_counter() - started) * 1000)
        return CheckResult(
            name="WebSocket Gateway",
            ok=True,
            message=f"Сервер {host}:{port} доступен",
            duration_ms=elapsed,
        )
    except Exception as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        return CheckResult(
            name="WebSocket Gateway",
            ok=False,
            message=str(exc),
            duration_ms=elapsed,
        )


def test_internet() -> CheckResult:
    started = time.perf_counter()
    try:
        with socket.create_connection(("1.1.1.1", 443), timeout=5):
            pass
        elapsed = int((time.perf_counter() - started) * 1000)
        return CheckResult(
            name="Интернет",
            ok=True,
            message="Исходящее подключение доступно",
            duration_ms=elapsed,
        )
    except Exception as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        return CheckResult(
            name="Интернет",
            ok=False,
            message=str(exc),
            duration_ms=elapsed,
        )


def discover_payment_schema(
    settings: dict[str, str],
) -> dict[str, Any]:
    """
    Read-only inspection of SQL Server metadata.
    Does not assume TillyPad payment table names.
    """
    server = settings.get("TILLYPAD_SQL_SERVER", "127.0.0.1")
    port = settings.get("TILLYPAD_SQL_PORT", "1433")
    database = settings.get("TILLYPAD_SQL_DATABASE", "")
    user = settings.get("TILLYPAD_SQL_USER", "")
    password = settings.get("TILLYPAD_SQL_PASSWORD", "")
    driver = settings.get(
        "TILLYPAD_SQL_DRIVER",
        "ODBC Driver 18 for SQL Server",
    )
    encrypt = settings.get("TILLYPAD_SQL_ENCRYPT", "no")
    trust = settings.get("TILLYPAD_SQL_TRUST_CERTIFICATE", "yes")
    timeout = int(settings.get("TILLYPAD_SQL_TIMEOUT", "10"))

    connection_string = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server},{port};"
        f"DATABASE={database};"
        f"UID={user};PWD={password};"
        f"Encrypt={encrypt};"
        f"TrustServerCertificate={trust};"
        f"Connection Timeout={timeout};"
    )

    keywords = (
        "pay",
        "cash",
        "tender",
        "card",
        "money",
        "fiscal",
        "amount",
        "payment",
        "settle",
    )

    with pyodbc.connect(connection_string) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT
                s.name AS schema_name,
                t.name AS table_name,
                c.column_id,
                c.name AS column_name,
                ty.name AS data_type,
                c.max_length,
                c.is_nullable
            FROM sys.tables AS t
            INNER JOIN sys.schemas AS s
                ON s.schema_id = t.schema_id
            INNER JOIN sys.columns AS c
                ON c.object_id = t.object_id
            INNER JOIN sys.types AS ty
                ON ty.user_type_id = c.user_type_id
            ORDER BY s.name, t.name, c.column_id
            """
        )
        rows = cursor.fetchall()

        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            schema_name = str(row.schema_name)
            table_name = str(row.table_name)
            column_name = str(row.column_name)

            table_lower = table_name.lower()
            column_lower = column_name.lower()

            matched = [
                keyword
                for keyword in keywords
                if keyword in table_lower
                or keyword in column_lower
            ]
            if not matched:
                continue

            key = f"{schema_name}.{table_name}"
            item = grouped.setdefault(
                key,
                {
                    "schema": schema_name,
                    "table": table_name,
                    "matched_keywords": set(),
                    "columns": [],
                },
            )
            item["matched_keywords"].update(matched)
            item["columns"].append(
                {
                    "name": column_name,
                    "data_type": str(row.data_type),
                    "max_length": int(row.max_length),
                    "nullable": bool(row.is_nullable),
                }
            )

        # Keep all columns for each candidate table, not just matching ones.
        candidate_names = {
            (item["schema"], item["table"])
            for item in grouped.values()
        }

        all_columns: dict[tuple[str, str], list[dict[str, Any]]] = {
            name: []
            for name in candidate_names
        }
        for row in rows:
            name = (
                str(row.schema_name),
                str(row.table_name),
            )
            if name not in all_columns:
                continue
            all_columns[name].append(
                {
                    "name": str(row.column_name),
                    "data_type": str(row.data_type),
                    "max_length": int(row.max_length),
                    "nullable": bool(row.is_nullable),
                }
            )

        tables: list[dict[str, Any]] = []
        for item in grouped.values():
            name = (item["schema"], item["table"])
            tables.append(
                {
                    "schema": item["schema"],
                    "table": item["table"],
                    "matched_keywords": sorted(
                        item["matched_keywords"]
                    ),
                    "columns": all_columns.get(name, []),
                }
            )

        tables.sort(
            key=lambda item: (
                -len(item["matched_keywords"]),
                item["schema"],
                item["table"],
            )
        )

        # Additional focused search for FK relationships around candidate tables.
        relationships: list[dict[str, Any]] = []
        if tables:
            cursor.execute(
                """
                SELECT
                    OBJECT_SCHEMA_NAME(fk.parent_object_id) AS parent_schema,
                    OBJECT_NAME(fk.parent_object_id) AS parent_table,
                    pc.name AS parent_column,
                    OBJECT_SCHEMA_NAME(fk.referenced_object_id) AS referenced_schema,
                    OBJECT_NAME(fk.referenced_object_id) AS referenced_table,
                    rc.name AS referenced_column
                FROM sys.foreign_keys AS fk
                INNER JOIN sys.foreign_key_columns AS fkc
                    ON fkc.constraint_object_id = fk.object_id
                INNER JOIN sys.columns AS pc
                    ON pc.object_id = fkc.parent_object_id
                   AND pc.column_id = fkc.parent_column_id
                INNER JOIN sys.columns AS rc
                    ON rc.object_id = fkc.referenced_object_id
                   AND rc.column_id = fkc.referenced_column_id
                ORDER BY parent_schema, parent_table
                """
            )
            for row in cursor.fetchall():
                parent = (
                    str(row.parent_schema),
                    str(row.parent_table),
                )
                referenced = (
                    str(row.referenced_schema),
                    str(row.referenced_table),
                )
                if (
                    parent not in candidate_names
                    and referenced not in candidate_names
                ):
                    continue
                relationships.append(
                    {
                        "parent_schema": str(row.parent_schema),
                        "parent_table": str(row.parent_table),
                        "parent_column": str(row.parent_column),
                        "referenced_schema": str(row.referenced_schema),
                        "referenced_table": str(row.referenced_table),
                        "referenced_column": str(row.referenced_column),
                    }
                )

    return {
        "generated_at": datetime.now().isoformat(),
        "database": database,
        "keywords": list(keywords),
        "candidate_tables": tables,
        "relationships": relationships,
    }


def save_payment_schema_report(
    report: dict[str, Any],
    target: Path,
) -> Path:
    target.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return target


def run_all(settings: dict[str, str]) -> list[CheckResult]:
    return [
        test_internet(),
        test_sql(settings),
        test_gateway(settings),
    ]


def export_support_report(
    settings: dict[str, str],
    results: list[CheckResult],
    target: Path,
) -> Path:
    safe_settings = dict(settings)
    for key in (
        "TILLYPAD_SQL_PASSWORD",
        "TILLYPAD_WS_API_KEY",
        "TILLYPAD_RELAY_API_KEY",
    ):
        if key in safe_settings:
            safe_settings[key] = "***"

    payload = {
        "generated_at": datetime.now().isoformat(),
        "hostname": socket.gethostname(),
        "settings": safe_settings,
        "checks": [item.to_dict() for item in results],
    }
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target
