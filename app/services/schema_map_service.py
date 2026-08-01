from typing import Any
from app.db.sql_server import SqlServer
from app.repositories.schema_map_repository import SchemaMapRepository

class SchemaMapService:
    def __init__(self) -> None:
        self.repository = SchemaMapRepository(SqlServer())

    def load(self, search: str = "") -> dict[str, Any]:
        return {
            "summary": self.repository.summary(),
            "tables": self.repository.tables(search),
            "foreign_keys": self.repository.foreign_keys(search),
            "key_columns": self.repository.key_columns(search),
        }
