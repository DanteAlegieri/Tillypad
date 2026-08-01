from typing import Any

from app.db.sql_server import SqlServer
from app.repositories.decision_repository import DecisionRepository


class DecisionService:
    def __init__(self) -> None:
        self.repository = DecisionRepository(SqlServer())

    def load(self) -> dict[str, Any]:
        return self.repository.executive()
