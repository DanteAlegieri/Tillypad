from datetime import date, timedelta
from typing import Any

from app.db.sql_server import SqlServer


class SalesRepository:
    def __init__(self, database: SqlServer | None = None) -> None:
        self.database = database or SqlServer()

    @staticmethod
    def normalize_period(
        date_from: date | None,
        date_to: date | None,
    ) -> tuple[date, date]:
        today = date.today()
        start = date_from or today
        end = date_to or start
        if end < start:
            start, end = end, start
        return start, end

    def summary(self, date_from: date | None, date_to: date | None) -> dict[str, Any]:
        start, end = self.normalize_period(date_from, date_to)
        end_exclusive = end + timedelta(days=1)
        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                WITH sales AS (
                    SELECT
                        o.ordr_gest_ID AS guest_id,
                        SUM(CAST(oi.orit_Count AS decimal(18,4)) * CAST(oi.orit_Price AS decimal(18,4))) AS guest_revenue,
                        SUM(CAST(oi.orit_Count AS decimal(18,4))) AS item_count
                    FROM dbo.tp_OrderItems AS oi
                    INNER JOIN dbo.tp_Orders AS o ON o.ordr_ID = oi.orit_ordr_ID
                    WHERE o.ordr_Date >= ? AND o.ordr_Date < ?
                    GROUP BY o.ordr_gest_ID
                )
                SELECT
                    COALESCE(SUM(guest_revenue), 0) AS revenue,
                    COUNT(*) AS checks_count,
                    COALESCE(AVG(NULLIF(guest_revenue, 0)), 0) AS avg_check,
                    COALESCE(SUM(item_count), 0) AS item_count
                FROM sales
                """,
                start,
                end_exclusive,
            )
            row = cursor.fetchone()
        return {
            "date_from": start,
            "date_to": end,
            "revenue": float(row.revenue or 0),
            "checks_count": int(row.checks_count or 0),
            "avg_check": float(row.avg_check or 0),
            "item_count": float(row.item_count or 0),
        }

    def hourly_sales(self, date_from: date | None, date_to: date | None) -> list[dict[str, Any]]:
        start, end = self.normalize_period(date_from, date_to)
        end_exclusive = end + timedelta(days=1)
        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    DATEPART(hour, o.ordr_Date) AS sale_hour,
                    COUNT(DISTINCT o.ordr_gest_ID) AS checks_count,
                    SUM(CAST(oi.orit_Count AS decimal(18,4)) * CAST(oi.orit_Price AS decimal(18,4))) AS revenue
                FROM dbo.tp_OrderItems AS oi
                INNER JOIN dbo.tp_Orders AS o ON o.ordr_ID = oi.orit_ordr_ID
                WHERE o.ordr_Date >= ? AND o.ordr_Date < ?
                GROUP BY DATEPART(hour, o.ordr_Date)
                ORDER BY sale_hour
                """,
                start,
                end_exclusive,
            )
            columns = [item[0] for item in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        maximum = max((float(row["revenue"] or 0) for row in rows), default=0)
        for row in rows:
            revenue = float(row["revenue"] or 0)
            row["revenue"] = revenue
            row["checks_count"] = int(row["checks_count"] or 0)
            row["bar_percent"] = round((revenue / maximum) * 100, 1) if maximum else 0
        return rows

    def daily_sales(self, date_from: date | None, date_to: date | None) -> list[dict[str, Any]]:
        start, end = self.normalize_period(date_from, date_to)
        end_exclusive = end + timedelta(days=1)
        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    CONVERT(date, o.ordr_Date) AS sale_date,
                    COUNT(DISTINCT o.ordr_gest_ID) AS checks_count,
                    SUM(CAST(oi.orit_Count AS decimal(18,4)) * CAST(oi.orit_Price AS decimal(18,4))) AS revenue
                FROM dbo.tp_OrderItems AS oi
                INNER JOIN dbo.tp_Orders AS o ON o.ordr_ID = oi.orit_ordr_ID
                WHERE o.ordr_Date >= ? AND o.ordr_Date < ?
                GROUP BY CONVERT(date, o.ordr_Date)
                ORDER BY sale_date
                """,
                start,
                end_exclusive,
            )
            columns = [item[0] for item in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        for row in rows:
            row["sale_date"] = str(row["sale_date"])
            row["revenue"] = float(row["revenue"] or 0)
            row["checks_count"] = int(row["checks_count"] or 0)
        return rows

    def comparison(self, date_from: date | None, date_to: date | None) -> dict[str, Any]:
        start, end = self.normalize_period(date_from, date_to)
        period_days = (end - start).days + 1
        previous_end = start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=period_days - 1)
        current = self.summary(start, end)
        previous = self.summary(previous_start, previous_end)

        def change(current_value: float, previous_value: float) -> float | None:
            if previous_value == 0:
                return None
            return round(((current_value - previous_value) / previous_value) * 100, 1)

        return {
            "previous_date_from": previous_start,
            "previous_date_to": previous_end,
            "previous": previous,
            "revenue_change": change(float(current["revenue"]), float(previous["revenue"])),
            "checks_change": change(float(current["checks_count"]), float(previous["checks_count"])),
            "avg_check_change": change(float(current["avg_check"]), float(previous["avg_check"])),
            "item_count_change": change(float(current["item_count"]), float(previous["item_count"])),
        }

    def top_items(self, date_from: date | None, date_to: date | None, limit: int = 20) -> list[dict[str, Any]]:
        start, end = self.normalize_period(date_from, date_to)
        end_exclusive = end + timedelta(days=1)
        limit = max(1, min(limit, 100))
        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT TOP ({limit})
                    COALESCE(NULLIF(LTRIM(RTRIM(mi.mitm_Name)), ''), N'Без названия') AS item_name,
                    SUM(CAST(oi.orit_Count AS decimal(18,4))) AS quantity,
                    SUM(CAST(oi.orit_Count AS decimal(18,4)) * CAST(oi.orit_Price AS decimal(18,4))) AS revenue,
                    COUNT(DISTINCT o.ordr_gest_ID) AS checks_count
                FROM dbo.tp_OrderItems AS oi
                INNER JOIN dbo.tp_Orders AS o ON o.ordr_ID = oi.orit_ordr_ID
                LEFT JOIN dbo.tp_MenuItems AS mi ON mi.mitm_ID = oi.orit_mitm_ID
                WHERE o.ordr_Date >= ? AND o.ordr_Date < ?
                GROUP BY COALESCE(NULLIF(LTRIM(RTRIM(mi.mitm_Name)), ''), N'Без названия')
                ORDER BY revenue DESC, quantity DESC
                """,
                start,
                end_exclusive,
            )
            columns = [item[0] for item in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        for row in rows:
            row["quantity"] = float(row["quantity"] or 0)
            row["revenue"] = float(row["revenue"] or 0)
            row["checks_count"] = int(row["checks_count"] or 0)
        return rows

    def recent_checks(self, date_from: date | None, date_to: date | None, limit: int = 30) -> list[dict[str, Any]]:
        start, end = self.normalize_period(date_from, date_to)
        end_exclusive = end + timedelta(days=1)
        limit = max(1, min(limit, 100))
        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT TOP ({limit})
                    g.gest_ID,
                    g.gest_Name,
                    MIN(o.ordr_Date) AS first_order_time,
                    MAX(o.ordr_Date) AS last_order_time,
                    SUM(CAST(oi.orit_Count AS decimal(18,4)) * CAST(oi.orit_Price AS decimal(18,4))) AS check_sum,
                    SUM(CAST(oi.orit_Count AS decimal(18,4))) AS item_count
                FROM dbo.tp_OrderItems AS oi
                INNER JOIN dbo.tp_Orders AS o ON o.ordr_ID = oi.orit_ordr_ID
                INNER JOIN dbo.tp_Guests AS g ON g.gest_ID = o.ordr_gest_ID
                WHERE o.ordr_Date >= ? AND o.ordr_Date < ?
                GROUP BY g.gest_ID, g.gest_Name
                ORDER BY MAX(o.ordr_Date) DESC
                """,
                start,
                end_exclusive,
            )
            columns = [item[0] for item in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        for row in rows:
            row["check_sum"] = float(row["check_sum"] or 0)
            row["item_count"] = float(row["item_count"] or 0)
        return rows
