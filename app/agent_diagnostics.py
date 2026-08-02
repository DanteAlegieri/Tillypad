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
