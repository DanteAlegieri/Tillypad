from collections import defaultdict
from datetime import date, timedelta
from math import sqrt
from typing import Any

from app.db.sql_server import SqlServer
from app.repositories.bi_repository import normalize_item_name


class ItemRepository:
    def __init__(self, database: SqlServer | None = None) -> None:
        self.database = database or SqlServer()

    @staticmethod
    def normalize_period(
        date_from: date | None,
        date_to: date | None,
    ) -> tuple[date, date]:
        today = date.today()
        start = date_from or (today - timedelta(days=29))
        end = date_to or today
        if end < start:
            start, end = end, start
        return start, end

    def item_info(self, item_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT TOP (1)
                    mitm_ID AS item_id,
                    mitm_Name AS item_name,
                    mitm_ShortName AS short_name,
                    mitm_Article AS article,
                    mitm_Description AS description,
                    mitm_Price AS current_price,
                    mitm_IsDisabled AS is_disabled,
                    mitm_mgrp_ID AS group_id
                FROM dbo.tp_MenuItems
                WHERE CONVERT(nvarchar(36), mitm_ID) = ?
                """,
                item_id,
            )
            row = cursor.fetchone()

        if not row:
            return None

        return {
            "item_id": str(row.item_id),
            "item_name": normalize_item_name(row.item_name),
            "short_name": row.short_name,
            "article": row.article,
            "description": row.description,
            "current_price": (
                float(row.current_price)
                if row.current_price is not None
                else None
            ),
            "is_disabled": bool(row.is_disabled),
            "group_id": str(row.group_id) if row.group_id else None,
        }

    def summary(
        self,
        item_id: str,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        start, end = self.normalize_period(date_from, date_to)
        end_exclusive = end + timedelta(days=1)
        previous_end = start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=(end - start).days)

        with self.database.connect() as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT
                    COALESCE(SUM(CAST(oi.orit_Count AS decimal(18,4))), 0) AS quantity,
                    COALESCE(SUM(
                        CAST(oi.orit_Count AS decimal(18,4))
                        * CAST(oi.orit_Price AS decimal(18,4))
                    ), 0) AS revenue,
                    COUNT(DISTINCT o.ordr_gest_ID) AS checks_count,
                    COALESCE(AVG(NULLIF(CAST(oi.orit_Price AS decimal(18,4)), 0)), 0) AS avg_price,
                    MAX(o.ordr_Date) AS last_sale
                FROM dbo.tp_OrderItems AS oi
                INNER JOIN dbo.tp_Orders AS o
                    ON o.ordr_ID = oi.orit_ordr_ID
                WHERE CONVERT(nvarchar(36), oi.orit_mitm_ID) = ?
                  AND o.ordr_Date >= ?
                  AND o.ordr_Date < ?
                """,
                item_id,
                start,
                end_exclusive,
            )
            current = cursor.fetchone()

            cursor.execute(
                """
                SELECT
                    COALESCE(SUM(CAST(oi.orit_Count AS decimal(18,4))), 0) AS quantity,
                    COALESCE(SUM(
                        CAST(oi.orit_Count AS decimal(18,4))
                        * CAST(oi.orit_Price AS decimal(18,4))
                    ), 0) AS revenue
                FROM dbo.tp_OrderItems AS oi
                INNER JOIN dbo.tp_Orders AS o
                    ON o.ordr_ID = oi.orit_ordr_ID
                WHERE CONVERT(nvarchar(36), oi.orit_mitm_ID) = ?
                  AND o.ordr_Date >= ?
                  AND o.ordr_Date < ?
                """,
                item_id,
                previous_start,
                previous_end + timedelta(days=1),
            )
            previous = cursor.fetchone()

        quantity = float(current.quantity or 0)
        revenue = float(current.revenue or 0)
        checks_count = int(current.checks_count or 0)
        period_days = (end - start).days + 1

        def change(current_value: float, previous_value: float) -> float | None:
            if previous_value == 0:
                return None
            return round(
                ((current_value - previous_value) / previous_value) * 100,
                1,
            )

        return {
            "date_from": start,
            "date_to": end,
            "period_days": period_days,
            "quantity": quantity,
            "revenue": revenue,
            "checks_count": checks_count,
            "avg_price": float(current.avg_price or 0),
            "avg_daily_quantity": quantity / period_days if period_days else 0,
            "last_sale": current.last_sale,
            "previous_quantity": float(previous.quantity or 0),
            "previous_revenue": float(previous.revenue or 0),
            "quantity_change": change(
                quantity,
                float(previous.quantity or 0),
            ),
            "revenue_change": change(
                revenue,
                float(previous.revenue or 0),
            ),
        }

    def daily_sales(
        self,
        item_id: str,
        date_from: date | None,
        date_to: date | None,
    ) -> list[dict[str, Any]]:
        start, end = self.normalize_period(date_from, date_to)
        end_exclusive = end + timedelta(days=1)

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    CONVERT(date, o.ordr_Date) AS sale_date,
                    SUM(CAST(oi.orit_Count AS decimal(18,4))) AS quantity,
                    SUM(
                        CAST(oi.orit_Count AS decimal(18,4))
                        * CAST(oi.orit_Price AS decimal(18,4))
                    ) AS revenue,
                    COUNT(DISTINCT o.ordr_gest_ID) AS checks_count
                FROM dbo.tp_OrderItems AS oi
                INNER JOIN dbo.tp_Orders AS o
                    ON o.ordr_ID = oi.orit_ordr_ID
                WHERE CONVERT(nvarchar(36), oi.orit_mitm_ID) = ?
                  AND o.ordr_Date >= ?
                  AND o.ordr_Date < ?
                GROUP BY CONVERT(date, o.ordr_Date)
                ORDER BY sale_date
                """,
                item_id,
                start,
                end_exclusive,
            )
            columns = [item[0] for item in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        return [
            {
                "sale_date": str(row["sale_date"]),
                "quantity": float(row["quantity"] or 0),
                "revenue": float(row["revenue"] or 0),
                "checks_count": int(row["checks_count"] or 0),
            }
            for row in rows
        ]

    def hourly_sales(
        self,
        item_id: str,
        date_from: date | None,
        date_to: date | None,
    ) -> list[dict[str, Any]]:
        start, end = self.normalize_period(date_from, date_to)
        end_exclusive = end + timedelta(days=1)

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    DATEPART(hour, o.ordr_Date) AS sale_hour,
                    SUM(CAST(oi.orit_Count AS decimal(18,4))) AS quantity,
                    SUM(
                        CAST(oi.orit_Count AS decimal(18,4))
                        * CAST(oi.orit_Price AS decimal(18,4))
                    ) AS revenue
                FROM dbo.tp_OrderItems AS oi
                INNER JOIN dbo.tp_Orders AS o
                    ON o.ordr_ID = oi.orit_ordr_ID
                WHERE CONVERT(nvarchar(36), oi.orit_mitm_ID) = ?
                  AND o.ordr_Date >= ?
                  AND o.ordr_Date < ?
                GROUP BY DATEPART(hour, o.ordr_Date)
                ORDER BY sale_hour
                """,
                item_id,
                start,
                end_exclusive,
            )
            columns = [item[0] for item in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        return [
            {
                "sale_hour": int(row["sale_hour"]),
                "quantity": float(row["quantity"] or 0),
                "revenue": float(row["revenue"] or 0),
            }
            for row in rows
        ]

    def heatmap(
        self,
        item_id: str,
        date_from: date | None,
        date_to: date | None,
    ) -> list[dict[str, Any]]:
        start, end = self.normalize_period(date_from, date_to)
        end_exclusive = end + timedelta(days=1)

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    DATEPART(weekday, o.ordr_Date) AS weekday_number,
                    DATEPART(hour, o.ordr_Date) AS sale_hour,
                    SUM(CAST(oi.orit_Count AS decimal(18,4))) AS quantity,
                    SUM(
                        CAST(oi.orit_Count AS decimal(18,4))
                        * CAST(oi.orit_Price AS decimal(18,4))
                    ) AS revenue
                FROM dbo.tp_OrderItems AS oi
                INNER JOIN dbo.tp_Orders AS o
                    ON o.ordr_ID = oi.orit_ordr_ID
                WHERE CONVERT(nvarchar(36), oi.orit_mitm_ID) = ?
                  AND o.ordr_Date >= ?
                  AND o.ordr_Date < ?
                GROUP BY
                    DATEPART(weekday, o.ordr_Date),
                    DATEPART(hour, o.ordr_Date)
                """,
                item_id,
                start,
                end_exclusive,
            )
            columns = [item[0] for item in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        grouped = {
            (int(row["weekday_number"]), int(row["sale_hour"])): {
                "quantity": float(row["quantity"] or 0),
                "revenue": float(row["revenue"] or 0),
            }
            for row in rows
        }
        maximum = max(
            (value["quantity"] for value in grouped.values()),
            default=0,
        )

        result = []
        for weekday in range(1, 8):
            for hour in range(0, 24):
                data = grouped.get(
                    (weekday, hour),
                    {"quantity": 0.0, "revenue": 0.0},
                )
                result.append(
                    {
                        "weekday_number": weekday,
                        "hour": hour,
                        "quantity": data["quantity"],
                        "revenue": data["revenue"],
                        "intensity": (
                            round((data["quantity"] / maximum) * 100, 1)
                            if maximum
                            else 0
                        ),
                    }
                )

        return result

    def basket_links(
        self,
        item_id: str,
        date_from: date | None,
        date_to: date | None,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        start, end = self.normalize_period(date_from, date_to)
        end_exclusive = end + timedelta(days=1)
        limit = max(1, min(limit, 50))

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                WITH target_guests AS (
                    SELECT DISTINCT o.ordr_gest_ID AS guest_id
                    FROM dbo.tp_OrderItems AS oi
                    INNER JOIN dbo.tp_Orders AS o
                        ON o.ordr_ID = oi.orit_ordr_ID
                    WHERE CONVERT(nvarchar(36), oi.orit_mitm_ID) = ?
                      AND o.ordr_Date >= ?
                      AND o.ordr_Date < ?
                ),
                related AS (
                    SELECT
                        oi.orit_mitm_ID AS related_id,
                        mi.mitm_Name AS related_name,
                        COUNT(DISTINCT o.ordr_gest_ID) AS pair_checks
                    FROM dbo.tp_OrderItems AS oi
                    INNER JOIN dbo.tp_Orders AS o
                        ON o.ordr_ID = oi.orit_ordr_ID
                    INNER JOIN target_guests AS tg
                        ON tg.guest_id = o.ordr_gest_ID
                    LEFT JOIN dbo.tp_MenuItems AS mi
                        ON mi.mitm_ID = oi.orit_mitm_ID
                    WHERE CONVERT(nvarchar(36), oi.orit_mitm_ID) <> ?
                      AND o.ordr_Date >= ?
                      AND o.ordr_Date < ?
                    GROUP BY
                        oi.orit_mitm_ID,
                        mi.mitm_Name
                ),
                target_total AS (
                    SELECT COUNT(*) AS target_checks FROM target_guests
                )
                SELECT TOP ({limit})
                    related.related_id,
                    related.related_name,
                    related.pair_checks,
                    target_total.target_checks
                FROM related
                CROSS JOIN target_total
                ORDER BY related.pair_checks DESC
                """,
                item_id,
                start,
                end_exclusive,
                item_id,
                start,
                end_exclusive,
            )
            columns = [item[0] for item in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        result = []
        for row in rows:
            pair_checks = int(row["pair_checks"] or 0)
            target_checks = int(row["target_checks"] or 0)
            result.append(
                {
                    "related_id": str(row["related_id"]),
                    "related_name": normalize_item_name(row["related_name"]),
                    "pair_checks": pair_checks,
                    "confidence": (
                        round((pair_checks / target_checks) * 100, 1)
                        if target_checks
                        else 0
                    ),
                }
            )
        return result

    def classification(
        self,
        item_id: str,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        start, end = self.normalize_period(date_from, date_to)
        period_days = (end - start).days + 1
        daily = self.daily_sales(item_id, start, end)
        all_items = self._all_item_revenue(start, end)

        target = next(
            (
                item
                for item in all_items
                if item["item_id"].lower() == item_id.lower()
            ),
            None,
        )

        values_by_date = {
            row["sale_date"]: row["quantity"]
            for row in daily
        }
        values = [
            values_by_date.get(
                str(start + timedelta(days=offset)),
                0,
            )
            for offset in range(period_days)
        ]
        mean = sum(values) / len(values) if values else 0
        variance = (
            sum((value - mean) ** 2 for value in values) / len(values)
            if values
            else 0
        )
        variation = sqrt(variance) / mean * 100 if mean else None

        sorted_by_variation = sorted(
            all_items,
            key=lambda item: item.get("variation", 999999),
        )
        index = next(
            (
                position
                for position, item in enumerate(sorted_by_variation)
                if item["item_id"].lower() == item_id.lower()
            ),
            len(sorted_by_variation) - 1,
        )
        count = max(len(sorted_by_variation), 1)
        xyz = (
            "X"
            if index < round(count / 3)
            else "Y"
            if index < round(count * 2 / 3)
            else "Z"
        )

        return {
            "abc": target["abc"] if target else "C",
            "xyz": xyz,
            "matrix": (target["abc"] if target else "C") + xyz,
            "share": target["share"] if target else 0,
            "variation": round(variation, 1) if variation is not None else None,
            "rank": target["rank"] if target else len(all_items),
            "items_count": len(all_items),
        }

    def _all_item_revenue(
        self,
        date_from: date,
        date_to: date,
    ) -> list[dict[str, Any]]:
        end_exclusive = date_to + timedelta(days=1)
        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    CONVERT(nvarchar(36), oi.orit_mitm_ID) AS item_id,
                    SUM(
                        CAST(oi.orit_Count AS decimal(18,4))
                        * CAST(oi.orit_Price AS decimal(18,4))
                    ) AS revenue
                FROM dbo.tp_OrderItems AS oi
                INNER JOIN dbo.tp_Orders AS o
                    ON o.ordr_ID = oi.orit_ordr_ID
                WHERE o.ordr_Date >= ?
                  AND o.ordr_Date < ?
                GROUP BY oi.orit_mitm_ID
                ORDER BY revenue DESC
                """,
                date_from,
                end_exclusive,
            )
            rows = cursor.fetchall()

        items = [
            {
                "item_id": str(row[0]),
                "revenue": float(row[1] or 0),
            }
            for row in rows
        ]
        total = sum(item["revenue"] for item in items)
        cumulative = 0.0

        for rank, item in enumerate(items, start=1):
            share = item["revenue"] / total * 100 if total else 0
            cumulative += share
            item["share"] = round(share, 2)
            item["abc"] = (
                "A"
                if cumulative <= 80
                else "B"
                if cumulative <= 95
                else "C"
            )
            item["rank"] = rank
            item["variation"] = rank

        return items
