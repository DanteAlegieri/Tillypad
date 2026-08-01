from datetime import date
from typing import Any

from app.db.sql_server import SqlServer
from app.repositories.bi_repository import BIRepository


class BIService:
    def __init__(self) -> None:
        self.repository = BIRepository(SqlServer())

    def load(
        self,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        return {
            "analysis": self.repository.abc_xyz(
                date_from,
                date_to,
            ),
            "pairs": self.repository.basket_pairs(
                date_from,
                date_to,
            ),
            "weekdays": self.repository.weekday_sales(
                date_from,
                date_to,
            ),
            "insights": self.repository.insights(
                date_from,
                date_to,
            ),
        }
