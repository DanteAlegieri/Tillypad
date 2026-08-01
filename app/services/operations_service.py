from typing import Any

from app.db.sql_server import SqlServer
from app.repositories.operations_repository import OperationsRepository
from app.repositories.decision_repository import DecisionRepository


class OperationsService:
    def __init__(self) -> None:
        database = SqlServer()
        self.repository = OperationsRepository(database)
        self.decision_repository = DecisionRepository(database)

    def load(self) -> dict[str, Any]:
        return {
            "overview": self.repository.overview(),
            "recent_checks": self.repository.recent_checks(),
            "executive": self.decision_repository.executive(),
        }
