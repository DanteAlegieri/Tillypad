from typing import Any
from app.db.sql_server import SqlServer
from app.repositories.database_explorer_repository import DatabaseExplorerRepository

class DatabaseExplorerService:
    def __init__(self) -> None:
        self.repository = DatabaseExplorerRepository(SqlServer())

    def index(self, search: str = "") -> dict[str, Any]:
        tables = self.repository.list_tables(search)
        return {"tables": tables, "search": search, "count": len(tables)}

    def table(self, schema_name: str, table_name: str, limit: int = 50) -> dict[str, Any]:
        return {
            "schema_name": schema_name,
            "table_name": table_name,
            "structure": self.repository.structure(schema_name, table_name),
            "relations": self.repository.relations(schema_name, table_name),
            "preview": self.repository.preview(schema_name, table_name, limit),
        }
