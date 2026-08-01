from typing import Any
from app.db.sql_server import SqlServer

class SchemaMapRepository:
    def __init__(self, database: SqlServer | None = None) -> None:
        self.database = database or SqlServer()

    def tables(self, search: str = "") -> list[dict[str, Any]]:
        clean_search = search.strip()
        pattern = f"%{clean_search}%"
        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    s.name AS schema_name,
                    t.name AS table_name,
                    SUM(CASE WHEN p.index_id IN (0,1) THEN p.rows ELSE 0 END) AS row_count,
                    COUNT(DISTINCT c.column_id) AS column_count
                FROM sys.tables AS t
                INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id
                LEFT JOIN sys.partitions AS p ON p.object_id = t.object_id
                LEFT JOIN sys.columns AS c ON c.object_id = t.object_id
                WHERE (? = '') OR t.name LIKE ? OR s.name LIKE ?
                GROUP BY s.name, t.name
                ORDER BY t.name
                """,
                clean_search, pattern, pattern,
            )
            columns = [item[0] for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def foreign_keys(self, search: str = "") -> list[dict[str, Any]]:
        clean_search = search.strip()
        pattern = f"%{clean_search}%"
        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    fk.name AS relation_name,
                    ps.name AS source_schema,
                    pt.name AS source_table,
                    pc.name AS source_column,
                    rs.name AS target_schema,
                    rt.name AS target_table,
                    rc.name AS target_column
                FROM sys.foreign_key_columns AS fkc
                INNER JOIN sys.foreign_keys AS fk ON fk.object_id = fkc.constraint_object_id
                INNER JOIN sys.tables AS pt ON pt.object_id = fkc.parent_object_id
                INNER JOIN sys.schemas AS ps ON ps.schema_id = pt.schema_id
                INNER JOIN sys.columns AS pc
                    ON pc.object_id = fkc.parent_object_id
                   AND pc.column_id = fkc.parent_column_id
                INNER JOIN sys.tables AS rt ON rt.object_id = fkc.referenced_object_id
                INNER JOIN sys.schemas AS rs ON rs.schema_id = rt.schema_id
                INNER JOIN sys.columns AS rc
                    ON rc.object_id = fkc.referenced_object_id
                   AND rc.column_id = fkc.referenced_column_id
                WHERE
                    (? = '')
                    OR pt.name LIKE ?
                    OR rt.name LIKE ?
                    OR pc.name LIKE ?
                    OR rc.name LIKE ?
                ORDER BY pt.name, pc.name
                """,
                clean_search, pattern, pattern, pattern, pattern,
            )
            columns = [item[0] for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def key_columns(self, search: str = "") -> list[dict[str, Any]]:
        clean_search = search.strip()
        pattern = f"%{clean_search}%"
        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    c.TABLE_SCHEMA AS schema_name,
                    c.TABLE_NAME AS table_name,
                    c.COLUMN_NAME AS column_name,
                    c.DATA_TYPE AS data_type,
                    c.IS_NULLABLE AS is_nullable,
                    CASE WHEN pk.COLUMN_NAME IS NOT NULL THEN 1 ELSE 0 END AS is_primary_key
                FROM INFORMATION_SCHEMA.COLUMNS AS c
                LEFT JOIN (
                    SELECT ku.TABLE_SCHEMA, ku.TABLE_NAME, ku.COLUMN_NAME
                    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
                    INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS ku
                        ON ku.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
                       AND ku.TABLE_SCHEMA = tc.TABLE_SCHEMA
                       AND ku.TABLE_NAME = tc.TABLE_NAME
                    WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                ) AS pk
                    ON pk.TABLE_SCHEMA = c.TABLE_SCHEMA
                   AND pk.TABLE_NAME = c.TABLE_NAME
                   AND pk.COLUMN_NAME = c.COLUMN_NAME
                WHERE
                    (c.COLUMN_NAME LIKE '%[_]ID' OR c.COLUMN_NAME LIKE '%ID' OR pk.COLUMN_NAME IS NOT NULL)
                    AND ((? = '') OR c.TABLE_NAME LIKE ? OR c.COLUMN_NAME LIKE ?)
                ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION
                """,
                clean_search, pattern, pattern,
            )
            columns = [item[0] for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def summary(self) -> dict[str, int]:
        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM sys.tables) AS table_count,
                    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS) AS column_count,
                    (SELECT COUNT(*) FROM sys.foreign_key_columns) AS foreign_key_count,
                    (
                        SELECT COUNT(*)
                        FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
                        WHERE CONSTRAINT_TYPE = 'PRIMARY KEY'
                    ) AS primary_key_count
                """
            )
            row = cursor.fetchone()
        return {
            "table_count": int(row.table_count or 0),
            "column_count": int(row.column_count or 0),
            "foreign_key_count": int(row.foreign_key_count or 0),
            "primary_key_count": int(row.primary_key_count or 0),
        }
