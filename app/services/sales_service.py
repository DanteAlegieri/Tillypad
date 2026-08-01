from datetime import date
from typing import Any

from app.db.sql_server import SqlServer
from app.repositories.sales_repository import SalesRepository


class SalesService:
    def __init__(self) -> None:
        self.repository = SalesRepository(SqlServer())

    def dashboard(
        self,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        return {
            "summary": self.repository.summary(date_from, date_to),
            "hourly": self.repository.hourly_sales(date_from, date_to),
            "top_items": self.repository.top_items(date_from, date_to),
            "recent_checks": self.repository.recent_checks(date_from, date_to),
        }
