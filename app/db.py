import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DB_PATH = Path("data/tillypad.db")


def init_db() -> None:
    DB_PATH.parent.mkdir(exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS divisions (
                dvsn_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                purse_id TEXT,
                raw_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS guests (
                gest_id TEXT PRIMARY KEY,
                division_id TEXT,
                name TEXT,
                state_id INTEGER,
                state TEXT,
                date_open TEXT,
                date_close TEXT,
                client_name TEXT,
                client_phone TEXT,
                order_sum REAL NOT NULL DEFAULT 0,
                pay_sum REAL NOT NULL DEFAULT 0,
                raw_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT,
                rows_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def normalize_list(data: Any) -> list[dict]:
    if data is None:
        return []
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def upsert_divisions(rows: list[dict]) -> int:
    count = 0
    with connect() as conn:
        for row in rows:
            dvsn_id = row.get("dvsn_ID") or row.get("dvsn_id")
            if not dvsn_id:
                continue
            conn.execute(
                """
                INSERT INTO divisions (dvsn_id, name, purse_id, raw_json, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(dvsn_id) DO UPDATE SET
                    name = excluded.name,
                    purse_id = excluded.purse_id,
                    raw_json = excluded.raw_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    str(dvsn_id),
                    str(row.get("dvsn_Name") or row.get("dvsn_name") or ""),
                    row.get("dvsn_mitm_ID_Purse") or row.get("mitm_ID_Purse"),
                    json.dumps(row, ensure_ascii=False),
                ),
            )
            count += 1
        conn.commit()
    return count


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def upsert_guests(rows: list[dict]) -> int:
    count = 0
    with connect() as conn:
        for row in rows:
            gest_id = row.get("gest_ID") or row.get("gest_id")
            if not gest_id:
                continue
            conn.execute(
                """
                INSERT INTO guests (
                    gest_id, division_id, name, state_id, state,
                    date_open, date_close, client_name, client_phone,
                    order_sum, pay_sum, raw_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(gest_id) DO UPDATE SET
                    division_id = excluded.division_id,
                    name = excluded.name,
                    state_id = excluded.state_id,
                    state = excluded.state,
                    date_open = excluded.date_open,
                    date_close = excluded.date_close,
                    client_name = excluded.client_name,
                    client_phone = excluded.client_phone,
                    order_sum = excluded.order_sum,
                    pay_sum = excluded.pay_sum,
                    raw_json = excluded.raw_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    str(gest_id),
                    row.get("gest_dvsn_ID") or row.get("gest_dvsn_id"),
                    row.get("gest_Name") or row.get("gest_name"),
                    row.get("gest_gsst_ID"),
                    row.get("gest_state"),
                    row.get("gest_DateOpen"),
                    row.get("gest_DateClose"),
                    row.get("gest_ClientName"),
                    str(row.get("gest_ClientPhone") or ""),
                    _as_float(row.get("gest_OrderSum")),
                    _as_float(row.get("gest_PaySum")),
                    json.dumps(row, ensure_ascii=False),
                ),
            )
            count += 1
        conn.commit()
    return count


def add_sync_log(target: str, status: str, message: str, rows_count: int = 0) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO sync_log (target, status, message, rows_count)
            VALUES (?, ?, ?, ?)
            """,
            (target, status, message, rows_count),
        )
        conn.commit()


def dashboard_stats(date_prefix: str | None = None) -> dict:
    where = ""
    params: tuple = ()
    if date_prefix:
        where = "WHERE date_open LIKE ?"
        params = (f"{date_prefix}%",)

    with connect() as conn:
        row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS checks_count,
                COALESCE(SUM(order_sum), 0) AS order_sum,
                COALESCE(SUM(pay_sum), 0) AS pay_sum,
                COALESCE(AVG(NULLIF(order_sum, 0)), 0) AS avg_check,
                SUM(CASE WHEN state_id = 0 THEN 1 ELSE 0 END) AS open_count,
                SUM(CASE WHEN state_id = 1 THEN 1 ELSE 0 END) AS closed_count
            FROM guests
            {where}
            """,
            params,
        ).fetchone()

        recent = conn.execute(
            f"""
            SELECT gest_id, name, date_open, date_close, client_name,
                   order_sum, pay_sum, state_id, state
            FROM guests
            {where}
            ORDER BY COALESCE(date_open, updated_at) DESC
            LIMIT 20
            """,
            params,
        ).fetchall()

        divisions = conn.execute(
            "SELECT dvsn_id, name FROM divisions ORDER BY name"
        ).fetchall()

        last_sync = conn.execute(
            """
            SELECT target, status, message, rows_count, created_at
            FROM sync_log
            ORDER BY id DESC
            LIMIT 10
            """
        ).fetchall()

    return {
        "checks_count": int(row["checks_count"] or 0),
        "order_sum": float(row["order_sum"] or 0),
        "pay_sum": float(row["pay_sum"] or 0),
        "avg_check": float(row["avg_check"] or 0),
        "open_count": int(row["open_count"] or 0),
        "closed_count": int(row["closed_count"] or 0),
        "recent": [dict(r) for r in recent],
        "divisions": [dict(r) for r in divisions],
        "last_sync": [dict(r) for r in last_sync],
    }
