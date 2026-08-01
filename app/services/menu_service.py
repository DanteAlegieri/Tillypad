from datetime import date
from typing import Any

from app.db.sql_server import SqlServer
from app.repositories.menu_repository import MenuRepository


class MenuService:
    def __init__(self) -> None:
        self.repository = MenuRepository(SqlServer())

    def load(
        self,
        date_from: date | None,
        date_to: date | None,
        search: str,
        group_id: str,
    ) -> dict[str, Any]:
        return {
            "summary": self.repository.summary(date_from, date_to),
            "groups": self.repository.groups(),
            "items": self.repository.items(
                date_from,
                date_to,
                search,
                group_id,
            ),
        }
