from typing import Any

from app.db.sql_server import SqlServer, SqlServerInfo
from app.repositories.guest_repository import GuestRepository


class DashboardService:
    def __init__(self) -> None:
        self.database = SqlServer()
        self.guests = GuestRepository(self.database)

    def load(self) -> dict[str, Any]:
        return {
            "info": self.database.info(),
            "stats": self.guests.today_stats(),
            "recent": self.guests.recent(),
        }
