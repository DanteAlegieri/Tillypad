from datetime import date
from typing import Any

from app.db.sql_server import SqlServer
from app.repositories.finance_repository import FinanceRepository


class FinanceService:
    def __init__(self) -> None:
        self.repository = FinanceRepository(SqlServer())

    def load(
        self,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        return {
            "summary": self.repository.summary(date_from, date_to),
            "pay_types": self.repository.by_pay_type(date_from, date_to),
            "daily": self.repository.daily(date_from, date_to),
            "hourly": self.repository.hourly(date_from, date_to),
            "recent": self.repository.recent_payments(
                date_from,
                date_to,
            ),
        }
