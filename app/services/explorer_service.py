from typing import Any

from app.db.sql_server import SqlServer
from app.repositories.explorer_repository import ExplorerRepository


class ExplorerService:
    def __init__(self) -> None:
        self.repository = ExplorerRepository(SqlServer())

    def search(
        self,
        table_search: str,
        column_search: str,
    ) -> dict[str, Any]:
        return {
            "tables": self.repository.list_tables(table_search),
            "columns": self.repository.search_columns(column_search),
        }

    def table(
        self,
        schema_name: str,
        table_name: str,
        limit: int,
    ) -> dict[str, Any]:
        return {
            "structure": self.repository.table_columns(
                schema_name,
                table_name,
            ),
            "preview": self.repository.table_preview(
                schema_name,
                table_name,
                limit,
            ),
        }
