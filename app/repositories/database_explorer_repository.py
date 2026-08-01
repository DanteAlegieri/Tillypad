from typing import Any
from app.db.sql_server import SqlServer

class DatabaseExplorerRepository:
    def __init__(self, database: SqlServer | None = None) -> None:
        self.database = database or SqlServer()

    def list_tables(self, search: str = "") -> list[dict[str, Any]]:
        pattern = f"%{search.strip()}%"
        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                '''
                SELECT
                    s.name AS schema_name,
                    t.name AS table_name,
                    SUM(CASE WHEN p.index_id IN (0, 1) THEN p.rows ELSE 0 END) AS rows_count
                FROM sys.tables AS t
                JOIN sys.schemas AS s ON s.schema_id = t.schema_id
                LEFT JOIN sys.partitions AS p ON p.object_id = t.object_id
                WHERE t.name LIKE 'tp[_]%'
                  AND (? = '%%' OR t.name LIKE ?)
                GROUP BY s.name, t.name
                ORDER BY t.name
                ''',
                pattern, pattern,
            )
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def structure(self, schema_name: str, table_name: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                '''
                SELECT
                    c.column_id,
                    c.name AS column_name,
                    ty.name AS data_type,
                    c.max_length,
                    c.precision,
                    c.scale,
                    c.is_nullable
                FROM sys.tables AS t
                JOIN sys.schemas AS s ON s.schema_id = t.schema_id
                JOIN sys.columns AS c ON c.object_id = t.object_id
                JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
                WHERE s.name = ? AND t.name = ?
                ORDER BY c.column_id
                ''',
                schema_name, table_name,
            )
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def relations(self, schema_name: str, table_name: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                '''
                SELECT
                    fk.name AS foreign_key_name,
                    OBJECT_NAME(fk.parent_object_id) AS source_table,
                    pc.name AS source_column,
                    OBJECT_NAME(fk.referenced_object_id) AS target_table,
                    rc.name AS target_column
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
                    (OBJECT_SCHEMA_NAME(fk.parent_object_id) = ?
                     AND OBJECT_NAME(fk.parent_object_id) = ?)
                    OR
                    (OBJECT_SCHEMA_NAME(fk.referenced_object_id) = ?
                     AND OBJECT_NAME(fk.referenced_object_id) = ?)
                ORDER BY source_table, source_column
                ''',
                schema_name, table_name, schema_name, table_name,
            )
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def preview(self, schema_name: str, table_name: str, limit: int = 50) -> dict[str, Any]:
        allowed = {(x["schema_name"], x["table_name"]) for x in self.list_tables()}
        if (schema_name, table_name) not in allowed:
            raise ValueError("Таблица не найдена")

        safe_schema = schema_name.replace("]", "]]")
        safe_table = table_name.replace("]", "]]")
        safe_limit = max(1, min(int(limit), 100))
        sql = f"SELECT TOP ({safe_limit}) * FROM [{safe_schema}].[{safe_table}]"

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql)
            cols = [d[0] for d in cursor.description]
            rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        return {"columns": cols, "rows": rows, "limit": safe_limit}
