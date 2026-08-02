from __future__ import annotations

import re
import time
from typing import Any

import pyodbc
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings
from app.db.sql_server import _decode_value, _encode_value


class QueryRequest(BaseModel):
    sql: str
    params: list[Any] = []


app = FastAPI(
    title="TillyPad Relay Agent",
    version="15.1.0",
)

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|create|truncate|exec(?:ute)?|"
    r"grant|revoke|deny|backup|restore|dbcc|kill|shutdown|use)\b",
    re.IGNORECASE,
)


def _validate_read_only(sql: str) -> None:
    normalized = re.sub(r"--.*?$|/\*.*?\*/", " ", sql, flags=re.M | re.S).strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Пустой SQL-запрос")
    if _FORBIDDEN.search(normalized):
        raise HTTPException(status_code=403, detail="Разрешены только запросы чтения")
    first = normalized.split(None, 1)[0].lower()
    if first not in {"select", "with"}:
        raise HTTPException(status_code=403, detail="Запрос должен начинаться с SELECT или WITH")


def _check_key(key: str | None) -> None:
    expected = get_settings().tillypad_relay_api_key
    if not expected:
        raise HTTPException(status_code=503, detail="На агенте не задан TILLYPAD_RELAY_API_KEY")
    if key != expected:
        raise HTTPException(status_code=401, detail="Неверный ключ Relay Agent")


@app.get("/v1/health")
def health(x_relay_key: str | None = Header(default=None)) -> dict[str, Any]:
    _check_key(x_relay_key)
    s = get_settings()
    started = time.perf_counter()
    try:
        connection = pyodbc.connect(
            (
                f"DRIVER={{{s.tillypad_sql_driver}}};"
                f"SERVER={s.tillypad_sql_server},{s.tillypad_sql_port};"
                f"DATABASE={s.tillypad_sql_database};"
                f"UID={s.tillypad_sql_user};"
                f"PWD={s.tillypad_sql_password};"
                f"Encrypt={s.tillypad_sql_encrypt};"
                f"TrustServerCertificate={s.tillypad_sql_trust_certificate};"
                f"Connection Timeout={s.tillypad_sql_timeout};"
            )
        )
        cursor = connection.cursor()
        cursor.execute("SELECT CAST(DB_NAME() AS nvarchar(255))")
        database_name = str(cursor.fetchone()[0])
        connection.close()
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail=f"SQL Server недоступен: {exc}") from exc
    return {
        "ok": True,
        "database": database_name,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    }


@app.post("/v1/query")
def query(
    request: QueryRequest,
    x_relay_key: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_key(x_relay_key)
    _validate_read_only(request.sql)
    s = get_settings()
    started = time.perf_counter()
    try:
        connection = pyodbc.connect(
            (
                f"DRIVER={{{s.tillypad_sql_driver}}};"
                f"SERVER={s.tillypad_sql_server},{s.tillypad_sql_port};"
                f"DATABASE={s.tillypad_sql_database};"
                f"UID={s.tillypad_sql_user};"
                f"PWD={s.tillypad_sql_password};"
                f"Encrypt={s.tillypad_sql_encrypt};"
                f"TrustServerCertificate={s.tillypad_sql_trust_certificate};"
                f"Connection Timeout={s.tillypad_sql_timeout};"
            )
        )
        cursor = connection.cursor()
        params = [_decode_value(value) for value in request.params]
        cursor.execute(request.sql, *params)
        columns = [str(item[0]) for item in (cursor.description or [])]
        rows = [
            [_encode_value(value) for value in row]
            for row in cursor.fetchall()
        ] if cursor.description else []
        connection.close()
    except pyodbc.Error as exc:
        raise HTTPException(status_code=500, detail=f"Ошибка SQL Server: {exc}") from exc
    return {
        "ok": True,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
    }
