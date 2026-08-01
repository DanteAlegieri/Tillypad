from typing import Any

from app.db.sql_server import SqlServer, SqlServerError


class GuestRepository:
    def __init__(self, database: SqlServer | None = None) -> None:
        self.database = database or SqlServer()

    def _columns(self) -> set[str]:
        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = 'dbo'
                  AND TABLE_NAME = 'tp_Guests'
                """
            )
            return {str(row[0]) for row in cursor.fetchall()}

    def today_stats(self) -> dict[str, int | float]:
        columns = self._columns()
        required = {"gest_ID", "gest_DateOpen", "gest_gsst_ID"}
        missing = required - columns

        if missing:
            raise SqlServerError(
                "В dbo.tp_Guests отсутствуют обязательные поля: "
                + ", ".join(sorted(missing))
            )

        parts = [
            "COUNT_BIG(*) AS checks_count",
            "SUM(CASE WHEN gest_gsst_ID = 0 THEN 1 ELSE 0 END) AS open_count",
            "SUM(CASE WHEN gest_gsst_ID = 1 THEN 1 ELSE 0 END) AS closed_count",
        ]

        if "gest_OrderSum" in columns:
            parts.extend(
                [
                    "COALESCE(SUM(CAST(gest_OrderSum AS decimal(18,2))), 0) "
                    "AS order_sum",
                    "COALESCE(AVG(NULLIF(CAST(gest_OrderSum AS decimal(18,2)), 0)), 0) "
                    "AS avg_check",
                ]
            )
        else:
            parts.extend(
                [
                    "CAST(0 AS decimal(18,2)) AS order_sum",
                    "CAST(0 AS decimal(18,2)) AS avg_check",
                ]
            )

        if "gest_PaySum" in columns:
            parts.append(
                "COALESCE(SUM(CAST(gest_PaySum AS decimal(18,2))), 0) "
                "AS pay_sum"
            )
        else:
            parts.append("CAST(0 AS decimal(18,2)) AS pay_sum")

        query = f"""
            SELECT {", ".join(parts)}
            FROM dbo.tp_Guests
            WHERE gest_DateOpen >= CONVERT(date, GETDATE())
              AND gest_DateOpen < DATEADD(day, 1, CONVERT(date, GETDATE()))
        """

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(query)
            row = cursor.fetchone()

        return {
            "checks_count": int(row.checks_count or 0),
            "open_count": int(row.open_count or 0),
            "closed_count": int(row.closed_count or 0),
            "order_sum": float(row.order_sum or 0),
            "avg_check": float(row.avg_check or 0),
            "pay_sum": float(row.pay_sum or 0),
        }

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 100))

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT TOP ({limit})
                    gest_ID,
                    gest_Name,
                    gest_DateOpen,
                    gest_DateClose,
                    gest_gsst_ID,
                    gest_usr_ID,
                    gest_dvsn_ID
                FROM dbo.tp_Guests
                ORDER BY gest_DateOpen DESC
                """
            )
            columns = [item[0] for item in cursor.description]

            return [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]
