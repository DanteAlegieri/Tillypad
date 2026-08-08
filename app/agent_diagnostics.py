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

        # Focused, read-only samples for confirmed TillyPad payment tables.
        # We intentionally use SELECT * here because this diagnostic release is
        # meant to discover the real field names before production mapping.
        payment_samples: dict[str, Any] = {}

        def fetch_sample(table_name: str, limit: int) -> dict[str, Any]:
            cursor.execute(
                """
                SELECT TOP (?) *
                FROM dbo.%s
                """ % table_name,
                limit,
            )
            columns = [item[0] for item in cursor.description]
            sample_rows = []
            for db_row in cursor.fetchall():
                row_dict = {}
                for column, value in zip(columns, db_row):
                    if value is None or isinstance(value, (str, int, float, bool)):
                        safe_value = value
                    elif isinstance(value, (bytes, bytearray)):
                        safe_value = value.hex()
                    elif hasattr(value, "isoformat"):
                        safe_value = value.isoformat()
                    else:
                        safe_value = str(value)
                    row_dict[column] = safe_value
                sample_rows.append(row_dict)
            return {"columns": columns, "rows": sample_rows}

        for table_name, limit in (
            ("tp_PayTypes", 200),
            ("tp_CheckPayments", 50),
            ("tp_Checks", 50),
        ):
            try:
                payment_samples[table_name] = fetch_sample(table_name, limit)
            except Exception as exc:
                payment_samples[table_name] = {"error": str(exc)}

    return {
        "generated_at": datetime.now().isoformat(),
        "database": database,
        "keywords": list(keywords),
        "candidate_tables": tables,
        "relationships": relationships,
        "payment_samples": payment_samples,
    }



def discover_food_cost_schema(
    settings: dict[str, str],
) -> dict[str, Any]:
    """Read-only targeted probe of TillyPad StoreEngine for actual food cost."""
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
    trust = settings.get(
        "TILLYPAD_SQL_TRUST_CERTIFICATE",
        "yes",
    )
    timeout = int(
        settings.get("TILLYPAD_SQL_TIMEOUT", "10")
    )

    connection_string = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server},{port};"
        f"DATABASE={database};"
        f"UID={user};PWD={password};"
        f"Encrypt={encrypt};"
        f"TrustServerCertificate={trust};"
        f"Connection Timeout={timeout};"
    )

    def safe_value(value: Any) -> Any:
        if value is None or isinstance(
            value,
            (str, int, float, bool),
        ):
            return value
        if isinstance(value, (bytes, bytearray)):
            return value.hex()
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    with pyodbc.connect(connection_string) as connection:
        cursor = connection.cursor()

        target_tables = (
            "tp_StoreEngine",
            "tp_ProductItems",
            "tp_Stores",
            "tp_SaleDocuments",
            "tp_SaleDocumentItems",
            "tp_WriteOffDocuments",
            "tp_WriteOffDocumentItems",
        )

        placeholders = ",".join("?" for _ in target_tables)
        cursor.execute(
            f"""
            SELECT
                s.name AS schema_name,
                t.name AS table_name,
                c.column_id,
                c.name AS column_name,
                ty.name AS data_type,
                c.max_length,
                c.precision,
                c.scale,
                c.is_nullable
            FROM sys.tables AS t
            JOIN sys.schemas AS s
              ON s.schema_id = t.schema_id
            JOIN sys.columns AS c
              ON c.object_id = t.object_id
            JOIN sys.types AS ty
              ON ty.user_type_id = c.user_type_id
            WHERE t.name IN ({placeholders})
            ORDER BY s.name, t.name, c.column_id
            """,
            *target_tables,
        )

        structures: dict[str, dict[str, Any]] = {
            table: {
                "table": table,
                "exists": False,
                "columns": [],
            }
            for table in target_tables
        }

        for row in cursor.fetchall():
            table = str(row.table_name)
            if table not in structures:
                continue
            item = structures[table]
            item["exists"] = True
            item["schema"] = str(row.schema_name)
            item["columns"].append(
                {
                    "name": str(row.column_name),
                    "data_type": str(row.data_type),
                    "max_length": int(row.max_length),
                    "precision": int(row.precision),
                    "scale": int(row.scale),
                    "nullable": bool(row.is_nullable),
                }
            )

        store_engine = structures["tp_StoreEngine"]
        if not store_engine["exists"]:
            return {
                "generated_at": datetime.now().isoformat(),
                "database": database,
                "mode": "store_engine_food_cost_probe",
                "read_only": True,
                "error": "tp_StoreEngine not found",
                "structures": list(structures.values()),
            }

        sten_columns = {
            column["name"]
            for column in store_engine["columns"]
        }

        # Determine useful columns dynamically because TillyPad builds may
        # differ. The probe never guesses non-existing fields.
        preferred = [
            "sten_ID",
            "sten_Date",
            "sten_pitm_ID",
            "sten_stor_ID",
            "sten_Volume",
            "sten_Price",
            "sten_Sum",
            "sten_DocumentID",
            "sten_DocumentItemID",
            "sten_dtyp_ID",
            "sten_Type",
            "sten_OperationType",
            "sten_SourceType",
            "sten_State",
            "sten_Done",
            "sten_IsDeleted",
        ]
        selected_sten = [
            name for name in preferred
            if name in sten_columns
        ]

        # Also include any other StoreEngine fields that may identify
        # source document/type/operation.
        for name in sorted(sten_columns):
            lname = name.lower()
            if name in selected_sten:
                continue
            if any(
                token in lname
                for token in (
                    "doc",
                    "type",
                    "oper",
                    "sale",
                    "write",
                    "output",
                    "input",
                    "return",
                    "move",
                    "compound",
                    "decompose",
                    "state",
                    "done",
                    "deleted",
                    "parent",
                    "source",
                    "target",
                )
            ):
                selected_sten.append(name)

        product_columns = {
            column["name"]
            for column in structures[
                "tp_ProductItems"
            ]["columns"]
        }
        store_columns = {
            column["name"]
            for column in structures[
                "tp_Stores"
            ]["columns"]
        }

        join_product = (
            "sten_pitm_ID" in sten_columns
            and "pitm_ID" in product_columns
        )
        join_store = (
            "sten_stor_ID" in sten_columns
            and "stor_ID" in store_columns
        )

        select_parts = [
            f"se.[{name}] AS [{name}]"
            for name in selected_sten
        ]

        if join_product:
            for name in (
                "pitm_Name",
                "pitm_Article",
                "pitm_picl_ID",
            ):
                if name in product_columns:
                    select_parts.append(
                        f"p.[{name}] AS [{name}]"
                    )

        if join_store:
            for name in (
                "stor_Name",
                "stor_Description",
            ):
                if name in store_columns:
                    select_parts.append(
                        f"s.[{name}] AS [{name}]"
                    )

        join_sql = ""
        if join_product:
            join_sql += (
                "\nLEFT JOIN dbo.tp_ProductItems AS p "
                "ON p.pitm_ID = se.sten_pitm_ID"
            )
        if join_store:
            join_sql += (
                "\nLEFT JOIN dbo.tp_Stores AS s "
                "ON s.stor_ID = se.sten_stor_ID"
            )

        order_sql = ""
        if "sten_Date" in sten_columns:
            order_sql = " ORDER BY se.sten_Date DESC"
        elif "sten_ID" in sten_columns:
            order_sql = " ORDER BY se.sten_ID DESC"

        rows = []
        query_error = None
        if select_parts:
            query = (
                "SELECT TOP (500)\n    "
                + ",\n    ".join(select_parts)
                + "\nFROM dbo.tp_StoreEngine AS se"
                + join_sql
                + order_sql
            )
            try:
                cursor.execute(query)
                columns = [
                    description[0]
                    for description in cursor.description
                ]
                for db_row in cursor.fetchall():
                    rows.append(
                        {
                            column: safe_value(value)
                            for column, value in zip(
                                columns,
                                db_row,
                            )
                        }
                    )
            except Exception as exc:
                query_error = str(exc)

        # Summary by date using the exact StoreEngine cost fields if present.
        daily_summary = []
        if all(
            name in sten_columns
            for name in (
                "sten_Date",
                "sten_Sum",
            )
        ):
            try:
                cursor.execute("""
                    SELECT TOP (30)
                        CAST(se.sten_Date AS date) AS business_date,
                        COUNT_BIG(*) AS rows_count,
                        SUM(CAST(se.sten_Sum AS decimal(38, 6))) AS sum_total
                    FROM dbo.tp_StoreEngine AS se
                    GROUP BY CAST(se.sten_Date AS date)
                    ORDER BY business_date DESC
                """)
                for row in cursor.fetchall():
                    daily_summary.append(
                        {
                            "business_date": safe_value(
                                row.business_date
                            ),
                            "rows_count": int(
                                row.rows_count
                            ),
                            "sum_total": safe_value(
                                row.sum_total
                            ),
                        }
                    )
            except Exception as exc:
                daily_summary = [
                    {"error": str(exc)}
                ]

        # Enumerate distinct combinations of likely source/type fields.
        discriminator_columns = [
            name
            for name in selected_sten
            if any(
                token in name.lower()
                for token in (
                    "type",
                    "oper",
                    "doc",
                    "state",
                    "done",
                    "deleted",
                    "source",
                )
            )
        ][:6]

        discriminator_samples = []
        if discriminator_columns:
            group_cols = ", ".join(
                f"se.[{name}]"
                for name in discriminator_columns
            )
            select_cols = ", ".join(
                f"se.[{name}] AS [{name}]"
                for name in discriminator_columns
            )
            try:
                cursor.execute(
                    "SELECT TOP (100) "
                    + select_cols
                    + ", COUNT_BIG(*) AS rows_count "
                    "FROM dbo.tp_StoreEngine AS se "
                    "GROUP BY "
                    + group_cols
                    + " ORDER BY rows_count DESC"
                )
                columns = [
                    description[0]
                    for description in cursor.description
                ]
                for db_row in cursor.fetchall():
                    discriminator_samples.append(
                        {
                            column: safe_value(value)
                            for column, value in zip(
                                columns,
                                db_row,
                            )
                        }
                    )
            except Exception as exc:
                discriminator_samples = [
                    {"error": str(exc)}
                ]

        # Relevant FK relationships only.
        cursor.execute("""
            SELECT
                OBJECT_SCHEMA_NAME(
                    fk.parent_object_id
                ) AS parent_schema,
                OBJECT_NAME(
                    fk.parent_object_id
                ) AS parent_table,
                pc.name AS parent_column,
                OBJECT_SCHEMA_NAME(
                    fk.referenced_object_id
                ) AS referenced_schema,
                OBJECT_NAME(
                    fk.referenced_object_id
                ) AS referenced_table,
                rc.name AS referenced_column
            FROM sys.foreign_keys AS fk
            JOIN sys.foreign_key_columns AS fkc
              ON fkc.constraint_object_id = fk.object_id
            JOIN sys.columns AS pc
              ON pc.object_id = fkc.parent_object_id
             AND pc.column_id = fkc.parent_column_id
            JOIN sys.columns AS rc
              ON rc.object_id = fkc.referenced_object_id
             AND rc.column_id = fkc.referenced_column_id
            WHERE
                OBJECT_NAME(fk.parent_object_id) = 'tp_StoreEngine'
                OR OBJECT_NAME(
                    fk.referenced_object_id
                ) = 'tp_StoreEngine'
            ORDER BY
                parent_table,
                parent_column,
                referenced_table,
                referenced_column
        """)
        relationships = [
            {
                "parent_schema": str(row.parent_schema),
                "parent_table": str(row.parent_table),
                "parent_column": str(
                    row.parent_column
                ),
                "referenced_schema": str(
                    row.referenced_schema
                ),
                "referenced_table": str(
                    row.referenced_table
                ),
                "referenced_column": str(
                    row.referenced_column
                ),
            }
            for row in cursor.fetchall()
        ]

    return {
        "generated_at": datetime.now().isoformat(),
        "database": database,
        "mode": "store_engine_food_cost_probe",
        "read_only": True,
        "structures": [
            structures[table]
            for table in target_tables
        ],
        "store_engine_selected_columns": selected_sten,
        "store_engine_rows": {
            "limit": 500,
            "rows": rows,
            "error": query_error,
        },
        "daily_summary": daily_summary,
        "discriminator_columns": discriminator_columns,
        "discriminator_samples": discriminator_samples,
        "relationships": relationships,
    }


def save_food_cost_schema_report(report: dict[str, Any], target: Path) -> Path:
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target

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
