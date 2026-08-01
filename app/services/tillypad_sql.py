from dataclasses import dataclass
from typing import Any
import pyodbc
from app.core.config import get_settings

class TillypadSqlError(RuntimeError):
    pass

@dataclass
class SqlServerInfo:
    server_name: str
    database_name: str
    version: str

class TillypadSqlService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def connection_string(self) -> str:
        s = self.settings
        if not s.tillypad_sql_user or not s.tillypad_sql_password:
            raise TillypadSqlError("В .env не указаны TILLYPAD_SQL_USER и TILLYPAD_SQL_PASSWORD.")
        return (
            f"DRIVER={{{s.tillypad_sql_driver}}};"
            f"SERVER={s.tillypad_sql_server},{s.tillypad_sql_port};"
            f"DATABASE={s.tillypad_sql_database};"
            f"UID={s.tillypad_sql_user};PWD={s.tillypad_sql_password};"
            f"Encrypt={s.tillypad_sql_encrypt};"
            f"TrustServerCertificate={s.tillypad_sql_trust_certificate};"
            f"Connection Timeout={s.tillypad_sql_timeout};"
        )

    def connect(self):
        try:
            return pyodbc.connect(self.connection_string())
        except pyodbc.Error as exc:
            raise TillypadSqlError(f"Не удалось подключиться к SQL Server: {exc}") from exc

    def test_connection(self) -> SqlServerInfo:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT CAST(@@SERVERNAME AS nvarchar(255)), CAST(DB_NAME() AS nvarchar(255)), CAST(@@VERSION AS nvarchar(max))")
            row = cur.fetchone()
        return SqlServerInfo(str(row[0]), str(row[1]), str(row[2]))

    def guest_stats(self) -> dict[str, Any]:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='tp_Guests'")
            columns = {str(r[0]) for r in cur.fetchall()}
            required = {"gest_ID", "gest_DateOpen", "gest_gsst_ID"}
            missing = required - columns
            if missing:
                raise TillypadSqlError("В dbo.tp_Guests отсутствуют поля: " + ", ".join(sorted(missing)))

            parts = [
                "COUNT_BIG(*) AS checks_count",
                "SUM(CASE WHEN gest_gsst_ID=0 THEN 1 ELSE 0 END) AS open_count",
                "SUM(CASE WHEN gest_gsst_ID=1 THEN 1 ELSE 0 END) AS closed_count",
            ]
            if "gest_OrderSum" in columns:
                parts += [
                    "COALESCE(SUM(CAST(gest_OrderSum AS decimal(18,2))),0) AS order_sum",
                    "COALESCE(AVG(NULLIF(CAST(gest_OrderSum AS decimal(18,2)),0)),0) AS avg_check",
                ]
            else:
                parts += ["CAST(0 AS decimal(18,2)) AS order_sum","CAST(0 AS decimal(18,2)) AS avg_check"]
            parts += ["COALESCE(SUM(CAST(gest_PaySum AS decimal(18,2))),0) AS pay_sum" if "gest_PaySum" in columns else "CAST(0 AS decimal(18,2)) AS pay_sum"]

            cur.execute(f"""SELECT {", ".join(parts)} FROM dbo.tp_Guests
                WHERE gest_DateOpen >= CONVERT(date,GETDATE())
                  AND gest_DateOpen < DATEADD(day,1,CONVERT(date,GETDATE()))""")
            row = cur.fetchone()
            return {k: float(getattr(row,k) or 0) if k in {"order_sum","avg_check","pay_sum"} else int(getattr(row,k) or 0)
                    for k in ["checks_count","open_count","closed_count","order_sum","avg_check","pay_sum"]}

    def recent_guests(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(f"""SELECT TOP ({max(1,min(limit,100))})
                gest_ID,gest_Name,gest_DateOpen,gest_DateClose,gest_gsst_ID,gest_usr_ID,gest_dvsn_ID
                FROM dbo.tp_Guests ORDER BY gest_DateOpen DESC""")
            cols=[d[0] for d in cur.description]
            return [dict(zip(cols,row)) for row in cur.fetchall()]


def list_tables(self, search: str = "", limit: int = 300) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 1000))
    pattern = f"%{search.strip()}%"

    with self.connect() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT TOP ({limit})
                s.name AS schema_name,
                t.name AS table_name,
                SUM(CASE WHEN p.index_id IN (0,1) THEN p.rows ELSE 0 END) AS row_count
            FROM sys.tables t
            INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
            LEFT JOIN sys.partitions p ON p.object_id = t.object_id
            WHERE (? = '' OR t.name LIKE ? OR s.name LIKE ?)
            GROUP BY s.name, t.name
            ORDER BY t.name
            """,
            search.strip(),
            pattern,
            pattern,
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

def search_columns(self, search: str, limit: int = 500) -> list[dict[str, Any]]:
    search = search.strip()
    if not search:
        return []

    limit = max(1, min(limit, 2000))
    pattern = f"%{search}%"

    with self.connect() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT TOP ({limit})
                TABLE_SCHEMA AS schema_name,
                TABLE_NAME AS table_name,
                COLUMN_NAME AS column_name,
                DATA_TYPE AS data_type,
                CHARACTER_MAXIMUM_LENGTH AS max_length,
                IS_NULLABLE AS is_nullable
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE COLUMN_NAME LIKE ?
               OR TABLE_NAME LIKE ?
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            """,
            pattern,
            pattern,
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

def table_columns(self, schema_name: str, table_name: str) -> list[dict[str, Any]]:
    self._validate_identifier(schema_name)
    self._validate_identifier(table_name)

    with self.connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                COLUMN_NAME AS column_name,
                DATA_TYPE AS data_type,
                CHARACTER_MAXIMUM_LENGTH AS max_length,
                NUMERIC_PRECISION AS numeric_precision,
                NUMERIC_SCALE AS numeric_scale,
                IS_NULLABLE AS is_nullable,
                ORDINAL_POSITION AS ordinal_position
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = ?
              AND TABLE_NAME = ?
            ORDER BY ORDINAL_POSITION
            """,
            schema_name,
            table_name,
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

def table_preview(
    self,
    schema_name: str,
    table_name: str,
    limit: int = 20,
) -> dict[str, Any]:
    self._validate_identifier(schema_name)
    self._validate_identifier(table_name)
    limit = max(1, min(limit, 100))

    quoted_schema = f"[{schema_name}]"
    quoted_table = f"[{table_name}]"

    with self.connect() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT TOP ({limit}) * FROM {quoted_schema}.{quoted_table}")
        columns = [d[0] for d in cur.description]
        rows = []
        for row in cur.fetchall():
            converted = []
            for value in row:
                if value is None or isinstance(value, (str, int, float, bool)):
                    converted.append(value)
                else:
                    converted.append(str(value))
            rows.append(converted)

    return {"columns": columns, "rows": rows}

@staticmethod
def _validate_identifier(value: str) -> None:
    if not value or not all(ch.isalnum() or ch == "_" for ch in value):
        raise TillypadSqlError("Недопустимое имя таблицы или схемы.")
