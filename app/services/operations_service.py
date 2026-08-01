from typing import Any

from app.db.sql_server import SqlServer
from app.repositories.operations_repository import OperationsRepository


class OperationsService:
    def __init__(self) -> None:
        self.repository = OperationsRepository(SqlServer())

    def load(self) -> dict[str, Any]:
        return {
            "overview": self.repository.overview(),
            "recent_checks": self.repository.recent_checks(),
        }
