from datetime import date, timedelta
from typing import Any

from app.core.config import get_settings
from app.db.sql_server import SqlServer
from app.repositories.finance_repository import normalize_paytype


class OperationsRepository:
    def __init__(self, database: SqlServer | None = None) -> None:
        self.database = database or SqlServer()
        self.settings = get_settings()

    def _payment_summary(self, day: date) -> dict[str, Any]:
        next_day = day + timedelta(days=1)

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    COALESCE(SUM(cp.chpy_Sum), 0) AS paid_total,
                    COALESCE(
                        SUM(CASE WHEN pt.pytp_IsCash = 1 THEN cp.chpy_Sum ELSE 0 END),
                        0
                    ) AS cash_total,
                    COALESCE(
                        SUM(CASE WHEN pt.pytp_IsCash = 0 THEN cp.chpy_Sum ELSE 0 END),
                        0
                    ) AS cashless_total,
                    COUNT(DISTINCT c.chck_ID) AS checks_count
                FROM dbo.tp_CheckPayments AS cp
                INNER JOIN dbo.tp_Checks AS c
                    ON c.chck_ID = cp.chpy_chck_ID
                INNER JOIN dbo.tp_PayTypes AS pt
                    ON pt.pytp_ID = cp.chpy_pytp_ID
                WHERE c.chck_Date >= ?
                  AND c.chck_Date < ?
                """,
                day,
                next_day,
            )
            row = cursor.fetchone()

        total = float(row.paid_total or 0)
        checks = int(row.checks_count or 0)

        return {
            "paid_total": total,
            "cash_total": float(row.cash_total or 0),
            "cashless_total": float(row.cashless_total or 0),
            "checks_count": checks,
            "avg_check": total / checks if checks else 0,
        }

    @staticmethod
    def _percent_change(current: float, previous: float) -> float | None:
        if previous == 0:
            return None
        return round(((current - previous) / previous) * 100, 1)

    def overview(self) -> dict[str, Any]:
        today = date.today()
        tomorrow = today + timedelta(days=1)
        yesterday = today - timedelta(days=1)

        today_payments = self._payment_summary(today)
        yesterday_payments = self._payment_summary(yesterday)

        with self.database.connect() as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT
                    COUNT(*) AS guest_count,
                    SUM(CASE WHEN gest_DateClose IS NULL THEN 1 ELSE 0 END) AS open_count,
                    SUM(CASE WHEN gest_DateClose IS NOT NULL THEN 1 ELSE 0 END) AS closed_count,
                    COALESCE(
                        AVG(
                            CASE
                                WHEN gest_DateClose IS NOT NULL
                                THEN DATEDIFF(minute, gest_DateOpen, gest_DateClose)
                                ELSE NULL
                            END
                        ),
                        0
                    ) AS avg_service_minutes
                FROM dbo.tp_Guests
                WHERE gest_DateOpen >= ?
                  AND gest_DateOpen < ?
                """,
                today,
                tomorrow,
            )
            guests = cursor.fetchone()

            cursor.execute(
                """
                SELECT TOP (1)
                    chck_Name AS check_name,
                    chck_Date AS check_date
                FROM dbo.tp_Checks
                WHERE chck_Date >= ?
                  AND chck_Date < ?
                ORDER BY chck_Date DESC
                """,
                today,
                tomorrow,
            )
            last_check = cursor.fetchone()

            cursor.execute(
                """
                SELECT TOP (1)
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(mi.mitm_Name)), ''),
                        N'Без названия'
                    ) AS item_name,
                    SUM(CAST(oi.orit_Count AS decimal(18,4))) AS quantity,
                    SUM(
                        CAST(oi.orit_Count AS decimal(18,4))
                        * CAST(oi.orit_Price AS decimal(18,4))
                    ) AS revenue
                FROM dbo.tp_OrderItems AS oi
                INNER JOIN dbo.tp_Orders AS o
                    ON o.ordr_ID = oi.orit_ordr_ID
                LEFT JOIN dbo.tp_MenuItems AS mi
                    ON mi.mitm_ID = oi.orit_mitm_ID
                WHERE o.ordr_Date >= ?
                  AND o.ordr_Date < ?
                GROUP BY
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(mi.mitm_Name)), ''),
                        N'Без названия'
                    )
                ORDER BY quantity DESC, revenue DESC
                """,
                today,
                tomorrow,
            )
            leader = cursor.fetchone()

            cursor.execute(
                """
                SELECT
                    DATEPART(hour, c.chck_Date) AS sale_hour,
                    COALESCE(SUM(cp.chpy_Sum), 0) AS amount,
                    COUNT(DISTINCT c.chck_ID) AS checks_count
                FROM dbo.tp_CheckPayments AS cp
                INNER JOIN dbo.tp_Checks AS c
                    ON c.chck_ID = cp.chpy_chck_ID
                WHERE c.chck_Date >= ?
                  AND c.chck_Date < ?
                GROUP BY DATEPART(hour, c.chck_Date)
                ORDER BY sale_hour
                """,
                today,
                tomorrow,
            )
            hourly_columns = [item[0] for item in cursor.description]
            hourly = [
                dict(zip(hourly_columns, row))
                for row in cursor.fetchall()
            ]

        target = float(self.settings.daily_revenue_target or 0)
        paid_total = float(today_payments["paid_total"])
        target_progress = round((paid_total / target) * 100, 1) if target else 0
        remaining_to_target = max(target - paid_total, 0)

        return {
            "date": today,
            **today_payments,
            "yesterday_paid_total": float(yesterday_payments["paid_total"]),
            "yesterday_checks_count": int(yesterday_payments["checks_count"]),
            "revenue_change": self._percent_change(
                paid_total,
                float(yesterday_payments["paid_total"]),
            ),
            "checks_change": self._percent_change(
                float(today_payments["checks_count"]),
                float(yesterday_payments["checks_count"]),
            ),
            "daily_target": target,
            "target_progress": min(target_progress, 100),
            "target_progress_raw": target_progress,
            "remaining_to_target": remaining_to_target,
            "target_reached": bool(target and paid_total >= target),
            "guest_count": int(guests.guest_count or 0),
            "open_count": int(guests.open_count or 0),
            "closed_count": int(guests.closed_count or 0),
            "avg_service_minutes": float(guests.avg_service_minutes or 0),
            "last_check_name": last_check.check_name if last_check else None,
            "last_check_date": last_check.check_date if last_check else None,
            "leader_name": leader.item_name if leader else None,
            "leader_quantity": float(leader.quantity or 0) if leader else 0,
            "leader_revenue": float(leader.revenue or 0) if leader else 0,
            "hourly": [
                {
                    "sale_hour": int(row["sale_hour"]),
                    "amount": float(row["amount"] or 0),
                    "checks_count": int(row["checks_count"] or 0),
                }
                for row in hourly
            ],
        }

    def recent_checks(self, limit: int = 12) -> list[dict[str, Any]]:
        today = date.today()
        tomorrow = today + timedelta(days=1)
        limit = max(1, min(limit, 50))

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT TOP ({limit})
                    c.chck_Name AS check_name,
                    c.chck_Date AS check_date,
                    pt.pytp_Name AS pay_type_name,
                    cp.chpy_Sum AS amount
                FROM dbo.tp_CheckPayments AS cp
                INNER JOIN dbo.tp_Checks AS c
                    ON c.chck_ID = cp.chpy_chck_ID
                INNER JOIN dbo.tp_PayTypes AS pt
                    ON pt.pytp_ID = cp.chpy_pytp_ID
                WHERE c.chck_Date >= ?
                  AND c.chck_Date < ?
                ORDER BY c.chck_Date DESC
                """,
                today,
                tomorrow,
            )
            columns = [item[0] for item in cursor.description]
            rows = [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]

        for row in rows:
            row["amount"] = float(row["amount"] or 0)
            row["pay_type_name"] = normalize_paytype(row["pay_type_name"])

        return rows
