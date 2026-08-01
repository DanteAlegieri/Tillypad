from typing import Any

from app.db.sql_server import SqlServer, SqlServerError


class ExplorerRepository:
    def __init__(self, database: SqlServer | None = None) -> None:
        self.database = database or SqlServer()

    @staticmethod
    def validate_identifier(value: str) -> None:
        if not value or not all(
            character.isalnum() or character == "_"
            for character in value
        ):
            raise SqlServerError(
                "Недопустимое имя схемы или таблицы."
            )

    def list_tables(
        self,
        search: str = "",
        limit: int = 300,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 1000))
        clean_search = search.strip()
        pattern = f"%{clean_search}%"

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT TOP ({limit})
                    schema_data.name AS schema_name,
                    table_data.name AS table_name,
                    SUM(
                        CASE
                            WHEN partition_data.index_id IN (0, 1)
                            THEN partition_data.rows
                            ELSE 0
                        END
                    ) AS row_count
                FROM sys.tables AS table_data
                INNER JOIN sys.schemas AS schema_data
                    ON schema_data.schema_id = table_data.schema_id
                LEFT JOIN sys.partitions AS partition_data
                    ON partition_data.object_id = table_data.object_id
                WHERE
                    (? = '')
                    OR table_data.name LIKE ?
                    OR schema_data.name LIKE ?
                GROUP BY schema_data.name, table_data.name
                ORDER BY table_data.name
                """,
                clean_search,
                pattern,
                pattern,
            )
            columns = [item[0] for item in cursor.description]

            return [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]

    def search_columns(
        self,
        search: str,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        clean_search = search.strip()

        if not clean_search:
            return []

        limit = max(1, min(limit, 2000))
        pattern = f"%{clean_search}%"

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
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
            columns = [item[0] for item in cursor.description]

            return [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]

    def table_columns(
        self,
        schema_name: str,
        table_name: str,
    ) -> list[dict[str, Any]]:
        self.validate_identifier(schema_name)
        self.validate_identifier(table_name)

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
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
            columns = [item[0] for item in cursor.description]

            return [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]

    def table_preview(
        self,
        schema_name: str,
        table_name: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        self.validate_identifier(schema_name)
        self.validate_identifier(table_name)

        limit = max(1, min(limit, 100))
        quoted_schema = f"[{schema_name}]"
        quoted_table = f"[{table_name}]"

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT TOP ({limit}) *
                FROM {quoted_schema}.{quoted_table}
                """
            )
            columns = [item[0] for item in cursor.description]
            rows: list[list[Any]] = []

            for row in cursor.fetchall():
                converted: list[Any] = []
                for value in row:
                    if value is None or isinstance(
                        value,
                        (str, int, float, bool),
                    ):
                        converted.append(value)
                    else:
                        converted.append(str(value))
                rows.append(converted)

        return {
            "columns": columns,
            "rows": rows,
        }
