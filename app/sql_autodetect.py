from __future__ import annotations

import os
import re
import socket
import winreg
from dataclasses import dataclass
from typing import Iterable

import pyodbc


TILLYPAD_SIGNATURES = (
    "dbo.orit",
    "dbo.ordr",
    "dbo.mitm",
    "dbo.tp_GuestDeliveries",
)


@dataclass
class SqlCandidate:
    server: str
    port: str
    database: str
    driver: str
    score: int
    details: str


def installed_odbc_drivers() -> list[str]:
    drivers = [
        item for item in pyodbc.drivers()
        if "SQL Server" in item
    ]
    preferred = sorted(
        drivers,
        key=lambda value: (
            "18" not in value,
            "17" not in value,
            value,
        ),
    )
    return preferred


def _registry_instances() -> set[str]:
    result: set[str] = set()
    locations = (
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Microsoft SQL Server\Instance Names\SQL",
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Microsoft\Microsoft SQL Server\Instance Names\SQL",
        ),
    )

    for hive, path in locations:
        try:
            with winreg.OpenKey(hive, path) as key:
                index = 0
                while True:
                    try:
                        name, _, _ = winreg.EnumValue(key, index)
                        result.add(name)
                        index += 1
                    except OSError:
                        break
        except OSError:
            continue

    return result


def local_server_candidates() -> list[str]:
    hostname = socket.gethostname()
    candidates = {
        "127.0.0.1",
        "localhost",
        hostname,
    }

    for instance in _registry_instances():
        if instance.upper() == "MSSQLSERVER":
            candidates.add("127.0.0.1")
            candidates.add(hostname)
        else:
            candidates.add(fr".\{instance}")
            candidates.add(fr"{hostname}\{instance}")

    # Частые локальные имена.
    candidates.add(r".\SQLEXPRESS")
    candidates.add(fr"{hostname}\SQLEXPRESS")

    return sorted(candidates)


def _connection_string(
    *,
    server: str,
    database: str,
    user: str,
    password: str,
    driver: str,
    timeout: int = 4,
) -> str:
    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={user};PWD={password};"
        "Encrypt=no;"
        "TrustServerCertificate=yes;"
        f"Connection Timeout={timeout};"
    )


def list_databases(
    *,
    server: str,
    user: str,
    password: str,
    driver: str,
) -> list[str]:
    connection_string = _connection_string(
        server=server,
        database="master",
        user=user,
        password=password,
        driver=driver,
    )
    with pyodbc.connect(connection_string) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT name
            FROM sys.databases
            WHERE state_desc = 'ONLINE'
              AND database_id > 4
            ORDER BY name
            """
        )
        return [row[0] for row in cursor.fetchall()]


def score_database(
    *,
    server: str,
    database: str,
    user: str,
    password: str,
    driver: str,
) -> SqlCandidate | None:
    connection_string = _connection_string(
        server=server,
        database=database,
        user=user,
        password=password,
        driver=driver,
    )
    with pyodbc.connect(connection_string) as connection:
        cursor = connection.cursor()
        found: list[str] = []
        for table_name in TILLYPAD_SIGNATURES:
            schema, table = table_name.split(".", 1)
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM sys.tables AS t
                INNER JOIN sys.schemas AS s
                    ON s.schema_id = t.schema_id
                WHERE s.name = ? AND t.name = ?
                """,
                schema,
                table,
            )
            if cursor.fetchone()[0]:
                found.append(table_name)

        if not found:
            return None

        score = len(found) * 25
        details = "Найдены таблицы: " + ", ".join(found)
        return SqlCandidate(
            server=server,
            port="1433",
            database=database,
            driver=driver,
            score=score,
            details=details,
        )


def find_tillypad(
    *,
    user: str,
    password: str,
    progress=None,
) -> list[SqlCandidate]:
    drivers = installed_odbc_drivers()
    if not drivers:
        raise RuntimeError(
            "Не найден ODBC Driver for SQL Server."
        )

    results: list[SqlCandidate] = []
    errors: list[str] = []

    for driver in drivers[:2]:
        for server in local_server_candidates():
            if progress:
                progress(f"Проверка {server} через {driver}")

            try:
                databases = list_databases(
                    server=server,
                    user=user,
                    password=password,
                    driver=driver,
                )
            except Exception as exc:
                errors.append(f"{server}: {exc}")
                continue

            for database in databases:
                if progress:
                    progress(f"Проверка базы {database}")
                try:
                    candidate = score_database(
                        server=server,
                        database=database,
                        user=user,
                        password=password,
                        driver=driver,
                    )
                except Exception:
                    continue

                if candidate is not None:
                    results.append(candidate)

    unique: dict[tuple[str, str], SqlCandidate] = {}
    for item in results:
        key = (item.server.lower(), item.database.lower())
        previous = unique.get(key)
        if previous is None or item.score > previous.score:
            unique[key] = item

    return sorted(
        unique.values(),
        key=lambda item: (-item.score, item.server, item.database),
    )
