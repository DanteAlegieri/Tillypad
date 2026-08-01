from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

import pyodbc

from app.core.config import get_settings


class SqlServerError(RuntimeError):
    pass


@dataclass(frozen=True)
class SqlServerInfo:
    server_name: str
    database_name: str
    version: str


class SqlServer:
    def __init__(self) -> None:
        self.settings = get_settings()

    def connection_string(self) -> str:
        s = self.settings

        if not s.tillypad_sql_user or not s.tillypad_sql_password:
            raise SqlServerError(
                "В .env не указаны TILLYPAD_SQL_USER и "
                "TILLYPAD_SQL_PASSWORD."
            )

        return (
            f"DRIVER={{{s.tillypad_sql_driver}}};"
            f"SERVER={s.tillypad_sql_server},{s.tillypad_sql_port};"
            f"DATABASE={s.tillypad_sql_database};"
            f"UID={s.tillypad_sql_user};"
            f"PWD={s.tillypad_sql_password};"
            f"Encrypt={s.tillypad_sql_encrypt};"
            f"TrustServerCertificate={s.tillypad_sql_trust_certificate};"
            f"Connection Timeout={s.tillypad_sql_timeout};"
        )

    @contextmanager
    def connect(self) -> Iterator[pyodbc.Connection]:
        try:
            connection = pyodbc.connect(self.connection_string())
        except pyodbc.Error as exc:
            raise SqlServerError(
                f"Не удалось подключиться к SQL Server: {exc}"
            ) from exc

        try:
            yield connection
        finally:
            connection.close()

    def info(self) -> SqlServerInfo:
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    CAST(@@SERVERNAME AS nvarchar(255)),
                    CAST(DB_NAME() AS nvarchar(255)),
                    CAST(@@VERSION AS nvarchar(max))
                """
            )
            row = cursor.fetchone()

        return SqlServerInfo(
            server_name=str(row[0]),
            database_name=str(row[1]),
            version=str(row[2]),
        )
