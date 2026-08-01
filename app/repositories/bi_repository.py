from collections import defaultdict
from datetime import date, timedelta
from math import sqrt
from typing import Any

from app.db.sql_server import SqlServer


class BIRepository:
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

    def item_sales(
        self,
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
                    mi.mitm_ID AS item_id,
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(mi.mitm_Name)), ''),
                        N'Без названия'
                    ) AS item_name,
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
                LEFT JOIN dbo.tp_MenuItems AS mi
                    ON mi.mitm_ID = oi.orit_mitm_ID
                WHERE o.ordr_Date >= ?
                  AND o.ordr_Date < ?
                GROUP BY
                    mi.mitm_ID,
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(mi.mitm_Name)), ''),
                        N'Без названия'
                    ),
                    CONVERT(date, o.ordr_Date)
                ORDER BY item_name, sale_date
                """,
                start,
                end_exclusive,
            )
            columns = [item[0] for item in cursor.description]
            rows = [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]

        for row in rows:
            row["sale_date"] = str(row["sale_date"])
            row["quantity"] = float(row["quantity"] or 0)
            row["revenue"] = float(row["revenue"] or 0)
            row["checks_count"] = int(row["checks_count"] or 0)

        return rows

    def abc_xyz(
        self,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        start, end = self.normalize_period(date_from, date_to)
        period_days = (end - start).days + 1
        sales = self.item_sales(start, end)

        grouped: dict[str, dict[str, Any]] = {}
        for row in sales:
            item_id = str(row["item_id"])
            item = grouped.setdefault(
                item_id,
                {
                    "item_id": item_id,
                    "item_name": row["item_name"],
                    "revenue": 0.0,
                    "quantity": 0.0,
                    "checks_count": 0,
                    "daily": defaultdict(float),
                },
            )
            item["revenue"] += row["revenue"]
            item["quantity"] += row["quantity"]
            item["checks_count"] += row["checks_count"]
            item["daily"][row["sale_date"]] += row["quantity"]

        items = list(grouped.values())
        items.sort(key=lambda item: item["revenue"], reverse=True)

        total_revenue = sum(item["revenue"] for item in items)
        cumulative = 0.0

        for item in items:
            share = (
                (item["revenue"] / total_revenue) * 100
                if total_revenue
                else 0
            )
            cumulative += share

            if cumulative <= 80:
                abc = "A"
            elif cumulative <= 95:
                abc = "B"
            else:
                abc = "C"

            daily_values = [
                float(item["daily"].get(str(start + timedelta(days=offset)), 0))
                for offset in range(period_days)
            ]
            mean = (
                sum(daily_values) / len(daily_values)
                if daily_values
                else 0
            )
            variance = (
                sum((value - mean) ** 2 for value in daily_values)
                / len(daily_values)
                if daily_values
                else 0
            )
            std_dev = sqrt(variance)

            if mean == 0:
                variation = None
                xyz = "Z"
            else:
                variation = (std_dev / mean) * 100
                if variation <= 10:
                    xyz = "X"
                elif variation <= 25:
                    xyz = "Y"
                else:
                    xyz = "Z"

            item["share"] = round(share, 2)
            item["cumulative_share"] = round(cumulative, 2)
            item["abc"] = abc
            item["xyz"] = xyz
            item["matrix"] = abc + xyz
            item["variation"] = (
                round(variation, 1)
                if variation is not None
                else None
            )
            item["avg_daily_quantity"] = round(mean, 2)
            item.pop("daily", None)

        matrix_counts: dict[str, int] = defaultdict(int)
        for item in items:
            matrix_counts[item["matrix"]] += 1

        return {
            "date_from": start,
            "date_to": end,
            "period_days": period_days,
            "total_revenue": total_revenue,
            "items": items,
            "matrix_counts": dict(matrix_counts),
            "a_count": sum(1 for item in items if item["abc"] == "A"),
            "b_count": sum(1 for item in items if item["abc"] == "B"),
            "c_count": sum(1 for item in items if item["abc"] == "C"),
            "x_count": sum(1 for item in items if item["xyz"] == "X"),
            "y_count": sum(1 for item in items if item["xyz"] == "Y"),
            "z_count": sum(1 for item in items if item["xyz"] == "Z"),
        }

    def basket_pairs(
        self,
        date_from: date | None,
        date_to: date | None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        start, end = self.normalize_period(date_from, date_to)
        end_exclusive = end + timedelta(days=1)
        limit = max(1, min(limit, 100))

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                WITH basket AS (
                    SELECT DISTINCT
                        o.ordr_gest_ID AS guest_id,
                        COALESCE(
                            NULLIF(LTRIM(RTRIM(mi.mitm_Name)), ''),
                            N'Без названия'
                        ) AS item_name
                    FROM dbo.tp_OrderItems AS oi
                    INNER JOIN dbo.tp_Orders AS o
                        ON o.ordr_ID = oi.orit_ordr_ID
                    LEFT JOIN dbo.tp_MenuItems AS mi
                        ON mi.mitm_ID = oi.orit_mitm_ID
                    WHERE o.ordr_Date >= ?
                      AND o.ordr_Date < ?
                )
                SELECT TOP ({limit})
                    first_item.item_name AS item_a,
                    second_item.item_name AS item_b,
                    COUNT(*) AS pair_count
                FROM basket AS first_item
                INNER JOIN basket AS second_item
                    ON second_item.guest_id = first_item.guest_id
                   AND second_item.item_name > first_item.item_name
                GROUP BY
                    first_item.item_name,
                    second_item.item_name
                ORDER BY pair_count DESC, item_a, item_b
                """,
                start,
                end_exclusive,
            )
            columns = [item[0] for item in cursor.description]
            rows = [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]

        for row in rows:
            row["pair_count"] = int(row["pair_count"] or 0)

        return rows

    def weekday_sales(
        self,
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
                    COUNT(DISTINCT o.ordr_gest_ID) AS checks_count,
                    SUM(
                        CAST(oi.orit_Count AS decimal(18,4))
                        * CAST(oi.orit_Price AS decimal(18,4))
                    ) AS revenue
                FROM dbo.tp_OrderItems AS oi
                INNER JOIN dbo.tp_Orders AS o
                    ON o.ordr_ID = oi.orit_ordr_ID
                WHERE o.ordr_Date >= ?
                  AND o.ordr_Date < ?
                GROUP BY DATEPART(weekday, o.ordr_Date)
                ORDER BY weekday_number
                """,
                start,
                end_exclusive,
            )
            columns = [item[0] for item in cursor.description]
            rows = [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]

        names = {
            1: "Воскресенье",
            2: "Понедельник",
            3: "Вторник",
            4: "Среда",
            5: "Четверг",
            6: "Пятница",
            7: "Суббота",
        }

        result = []
        for row in rows:
            weekday_number = int(row["weekday_number"])
            result.append(
                {
                    "weekday_number": weekday_number,
                    "weekday_name": names.get(
                        weekday_number,
                        str(weekday_number),
                    ),
                    "checks_count": int(row["checks_count"] or 0),
                    "revenue": float(row["revenue"] or 0),
                }
            )

        return result

    def insights(
        self,
        date_from: date | None,
        date_to: date | None,
    ) -> list[dict[str, str]]:
        analysis = self.abc_xyz(date_from, date_to)
        items = analysis["items"]
        pairs = self.basket_pairs(date_from, date_to, limit=5)
        weekdays = self.weekday_sales(date_from, date_to)

        insights: list[dict[str, str]] = []

        if items:
            leader = items[0]
            insights.append(
                {
                    "level": "positive",
                    "title": "Лидер выручки",
                    "text": (
                        f'{leader["item_name"]} даёт '
                        f'{leader["share"]:.1f}% выручки периода.'
                    ),
                }
            )

        unstable_a = [
            item for item in items
            if item["abc"] == "A" and item["xyz"] == "Z"
        ]
        if unstable_a:
            item = unstable_a[0]
            insights.append(
                {
                    "level": "warning",
                    "title": "Важная, но нестабильная позиция",
                    "text": (
                        f'{item["item_name"]} относится к AZ: '
                        "высокая доля выручки, но нестабильный спрос."
                    ),
                }
            )

        stable_a = [
            item for item in items
            if item["matrix"] == "AX"
        ]
        if stable_a:
            item = stable_a[0]
            insights.append(
                {
                    "level": "positive",
                    "title": "Основа меню",
                    "text": (
                        f'{item["item_name"]} относится к AX: '
                        "высокая выручка и стабильный спрос."
                    ),
                }
            )

        if pairs:
            pair = pairs[0]
            insights.append(
                {
                    "level": "info",
                    "title": "Частая связка",
                    "text": (
                        f'{pair["item_a"]} + {pair["item_b"]} '
                        f'встречались вместе {pair["pair_count"]} раз.'
                    ),
                }
            )

        if weekdays:
            best_day = max(
                weekdays,
                key=lambda row: row["revenue"],
            )
            insights.append(
                {
                    "level": "info",
                    "title": "Лучший день недели",
                    "text": (
                        f'{best_day["weekday_name"]}: '
                        f'{best_day["revenue"]:,.0f} ₽ выручки.'
                    ).replace(",", " "),
                }
            )

        return insights
