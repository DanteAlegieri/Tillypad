from collections import defaultdict
from datetime import date, timedelta
from math import sqrt
from typing import Any
import re

from app.db.sql_server import SqlServer


def normalize_item_name(name: str | None) -> str:
    if not name:
        return "Служебная позиция"
    clean = "".join(ch for ch in str(name) if ord(ch) >= 32)
    clean = re.sub(r"[■□]+", "", clean)
    clean = re.sub(r"\s{2,}", " ", clean).strip()
    if not clean or clean.lower() in {"без названия", "null", "none"}:
        return "Служебная позиция"
    return clean


class BIRepository:
    def __init__(self, database: SqlServer | None = None) -> None:
        self.database = database or SqlServer()

    @staticmethod
    def normalize_period(
        date_from: date | None,
        date_to: date | None,
    ) -> tuple[date, date]:
        today = date.today()
        start = date_from or today - timedelta(days=29)
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
                    mi.mitm_Name AS item_name,
                    CONVERT(date, o.ordr_Date) AS sale_date,
                    DATEPART(hour, o.ordr_Date) AS sale_hour,
                    DATEPART(weekday, o.ordr_Date) AS weekday_number,
                    SUM(CAST(oi.orit_Count AS decimal(18,4))) AS quantity,
                    SUM(CAST(oi.orit_Count AS decimal(18,4))
                        * CAST(oi.orit_Price AS decimal(18,4))) AS revenue,
                    COUNT(DISTINCT o.ordr_gest_ID) AS checks_count
                FROM dbo.tp_OrderItems AS oi
                INNER JOIN dbo.tp_Orders AS o
                    ON o.ordr_ID = oi.orit_ordr_ID
                LEFT JOIN dbo.tp_MenuItems AS mi
                    ON mi.mitm_ID = oi.orit_mitm_ID
                WHERE o.ordr_Date >= ? AND o.ordr_Date < ?
                GROUP BY
                    mi.mitm_ID,
                    mi.mitm_Name,
                    CONVERT(date, o.ordr_Date),
                    DATEPART(hour, o.ordr_Date),
                    DATEPART(weekday, o.ordr_Date)
                """,
                start,
                end_exclusive,
            )
            columns = [item[0] for item in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        for row in rows:
            row["item_name"] = normalize_item_name(row["item_name"])
            row["sale_date"] = str(row["sale_date"])
            row["sale_hour"] = int(row["sale_hour"])
            row["weekday_number"] = int(row["weekday_number"])
            row["quantity"] = float(row["quantity"] or 0)
            row["revenue"] = float(row["revenue"] or 0)
            row["checks_count"] = int(row["checks_count"] or 0)
        return rows

    @staticmethod
    def _classic_xyz(variation: float | None) -> str:
        if variation is None:
            return "Z"
        if variation <= 10:
            return "X"
        if variation <= 25:
            return "Y"
        return "Z"

    @staticmethod
    def _adaptive_xyz(items: list[dict[str, Any]]) -> None:
        valid = sorted(
            [item for item in items if item["variation"] is not None],
            key=lambda item: item["variation"],
        )
        if not valid:
            for item in items:
                item["xyz"] = "Z"
                item["matrix"] = item["abc"] + "Z"
            return
        first = max(1, round(len(valid) / 3))
        second = max(first + 1, round(len(valid) * 2 / 3))
        for index, item in enumerate(valid):
            item["xyz"] = "X" if index < first else ("Y" if index < second else "Z")
            item["matrix"] = item["abc"] + item["xyz"]

    def abc_xyz(
        self,
        date_from: date | None,
        date_to: date | None,
        xyz_mode: str = "adaptive",
    ) -> dict[str, Any]:
        start, end = self.normalize_period(date_from, date_to)
        period_days = (end - start).days + 1
        sales = self.item_sales(start, end)
        grouped: dict[str, dict[str, Any]] = {}
        for row in sales:
            key = str(row["item_id"])
            item = grouped.setdefault(
                key,
                {
                    "item_id": key,
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

        items = sorted(grouped.values(), key=lambda item: item["revenue"], reverse=True)
        total_revenue = sum(item["revenue"] for item in items)
        cumulative = 0.0

        for item in items:
            share = item["revenue"] / total_revenue * 100 if total_revenue else 0
            cumulative += share
            abc = "A" if cumulative <= 80 else ("B" if cumulative <= 95 else "C")
            values = [
                float(item["daily"].get(str(start + timedelta(days=offset)), 0))
                for offset in range(period_days)
            ]
            mean = sum(values) / len(values) if values else 0
            variance = sum((value - mean) ** 2 for value in values) / len(values) if values else 0
            variation = sqrt(variance) / mean * 100 if mean else None
            item.update({
                "share": round(share, 2),
                "cumulative_share": round(cumulative, 2),
                "abc": abc,
                "variation": round(variation, 1) if variation is not None else None,
                "avg_daily_quantity": round(mean, 2),
                "xyz": self._classic_xyz(variation),
            })
            item["matrix"] = abc + item["xyz"]
            item.pop("daily", None)

        mode = "classic" if xyz_mode == "classic" else "adaptive"
        if mode == "adaptive":
            self._adaptive_xyz(items)

        counts: dict[str, int] = defaultdict(int)
        for item in items:
            counts[item["matrix"]] += 1

        return {
            "date_from": start,
            "date_to": end,
            "period_days": period_days,
            "xyz_mode": mode,
            "total_revenue": total_revenue,
            "items": items,
            "matrix_counts": dict(counts),
            "a_count": sum(item["abc"] == "A" for item in items),
            "b_count": sum(item["abc"] == "B" for item in items),
            "c_count": sum(item["abc"] == "C" for item in items),
            "x_count": sum(item["xyz"] == "X" for item in items),
            "y_count": sum(item["xyz"] == "Y" for item in items),
            "z_count": sum(item["xyz"] == "Z" for item in items),
        }

    def basket_pairs(
        self,
        date_from: date | None,
        date_to: date | None,
        limit: int = 30,
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
                        mi.mitm_Name AS item_name
                    FROM dbo.tp_OrderItems AS oi
                    INNER JOIN dbo.tp_Orders AS o
                        ON o.ordr_ID = oi.orit_ordr_ID
                    LEFT JOIN dbo.tp_MenuItems AS mi
                        ON mi.mitm_ID = oi.orit_mitm_ID
                    WHERE o.ordr_Date >= ? AND o.ordr_Date < ?
                ),
                totals AS (
                    SELECT COUNT(DISTINCT guest_id) AS total_guests FROM basket
                ),
                item_counts AS (
                    SELECT item_name, COUNT(DISTINCT guest_id) AS item_guests
                    FROM basket GROUP BY item_name
                ),
                pairs AS (
                    SELECT
                        a.item_name AS item_a,
                        b.item_name AS item_b,
                        COUNT(*) AS pair_count
                    FROM basket AS a
                    INNER JOIN basket AS b
                        ON b.guest_id = a.guest_id
                       AND CONVERT(nvarchar(max), b.item_name)
                           > CONVERT(nvarchar(max), a.item_name)
                    GROUP BY a.item_name, b.item_name
                )
                SELECT TOP ({limit})
                    pairs.item_a,
                    pairs.item_b,
                    pairs.pair_count,
                    ca.item_guests AS item_a_guests,
                    cb.item_guests AS item_b_guests,
                    totals.total_guests
                FROM pairs
                INNER JOIN item_counts AS ca
                    ON (ca.item_name = pairs.item_a OR (ca.item_name IS NULL AND pairs.item_a IS NULL))
                INNER JOIN item_counts AS cb
                    ON (cb.item_name = pairs.item_b OR (cb.item_name IS NULL AND pairs.item_b IS NULL))
                CROSS JOIN totals
                ORDER BY pairs.pair_count DESC
                """,
                start,
                end_exclusive,
            )
            columns = [item[0] for item in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        result = []
        for row in rows:
            pair = int(row["pair_count"] or 0)
            count_a = int(row["item_a_guests"] or 0)
            count_b = int(row["item_b_guests"] or 0)
            total = int(row["total_guests"] or 0)
            support = pair / total if total else 0
            confidence = pair / count_a if count_a else 0
            expected = (count_a / total) * (count_b / total) if total else 0
            lift = support / expected if expected else 0
            result.append({
                "item_a": normalize_item_name(row["item_a"]),
                "item_b": normalize_item_name(row["item_b"]),
                "pair_count": pair,
                "support": round(support * 100, 1),
                "confidence_a_to_b": round(confidence * 100, 1),
                "lift": round(lift, 2),
            })
        return result

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
                    SUM(CAST(oi.orit_Count AS decimal(18,4))
                        * CAST(oi.orit_Price AS decimal(18,4))) AS revenue
                FROM dbo.tp_OrderItems AS oi
                INNER JOIN dbo.tp_Orders AS o ON o.ordr_ID = oi.orit_ordr_ID
                WHERE o.ordr_Date >= ? AND o.ordr_Date < ?
                GROUP BY DATEPART(weekday, o.ordr_Date)
                ORDER BY weekday_number
                """,
                start,
                end_exclusive,
            )
            columns = [item[0] for item in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        names = {
            1: "Воскресенье", 2: "Понедельник", 3: "Вторник",
            4: "Среда", 5: "Четверг", 6: "Пятница", 7: "Суббота",
        }
        return [{
            "weekday_number": int(row["weekday_number"]),
            "weekday_name": names[int(row["weekday_number"])],
            "checks_count": int(row["checks_count"] or 0),
            "revenue": float(row["revenue"] or 0),
        } for row in rows]

    def heatmap(
        self,
        date_from: date | None,
        date_to: date | None,
    ) -> list[dict[str, Any]]:
        grouped: dict[tuple[int, int], float] = defaultdict(float)
        for row in self.item_sales(date_from, date_to):
            grouped[(row["weekday_number"], row["sale_hour"])] += row["revenue"]
        maximum = max(grouped.values(), default=0)
        names = {1: "Вс", 2: "Пн", 3: "Вт", 4: "Ср", 5: "Чт", 6: "Пт", 7: "Сб"}
        return [{
            "weekday_number": weekday,
            "weekday_name": names[weekday],
            "hour": hour,
            "revenue": round(grouped.get((weekday, hour), 0), 2),
            "intensity": round(grouped.get((weekday, hour), 0) / maximum * 100, 1) if maximum else 0,
        } for weekday in range(1, 8) for hour in range(24)]

    def insights(
        self,
        date_from: date | None,
        date_to: date | None,
        xyz_mode: str = "adaptive",
    ) -> list[dict[str, str]]:
        analysis = self.abc_xyz(date_from, date_to, xyz_mode)
        items = analysis["items"]
        pairs = self.basket_pairs(date_from, date_to, 5)
        weekdays = self.weekday_sales(date_from, date_to)
        heatmap = self.heatmap(date_from, date_to)
        insights: list[dict[str, str]] = []

        if items:
            leader = items[0]
            insights.append({
                "level": "positive",
                "title": "Лидер выручки",
                "text": f'{leader["item_name"]} даёт {leader["share"]:.1f}% выручки периода.',
            })
        ax = next((item for item in items if item["matrix"] == "AX"), None)
        if ax:
            insights.append({
                "level": "positive",
                "title": "Основа меню",
                "text": f'{ax["item_name"]}: высокая выручка и наиболее стабильный спрос.',
            })
        az = next((item for item in items if item["matrix"] == "AZ"), None)
        if az:
            insights.append({
                "level": "warning",
                "title": "Нестабильный лидер",
                "text": f'{az["item_name"]}: высокая выручка, но спрос нестабилен.',
            })
        if pairs:
            pair = max(pairs, key=lambda row: (row["lift"], row["pair_count"]))
            insights.append({
                "level": "info",
                "title": "Сильная связка",
                "text": (
                    f'{pair["item_a"]} + {pair["item_b"]}: '
                    f'достоверность {pair["confidence_a_to_b"]:.1f}%, lift {pair["lift"]:.2f}.'
                ),
            })
        if weekdays:
            best = max(weekdays, key=lambda row: row["revenue"])
            insights.append({
                "level": "info",
                "title": "Лучший день недели",
                "text": f'{best["weekday_name"]}: {best["revenue"]:,.0f} ₽.'.replace(",", " "),
            })
        active = [cell for cell in heatmap if cell["revenue"] > 0]
        if active:
            peak = max(active, key=lambda cell: cell["revenue"])
            insights.append({
                "level": "info",
                "title": "Пиковое окно",
                "text": (
                    f'{peak["weekday_name"]}, {peak["hour"]:02d}:00–'
                    f'{peak["hour"] + 1:02d}:00: {peak["revenue"]:,.0f} ₽.'
                ).replace(",", " "),
            })
        weak = next((item for item in reversed(items) if item["quantity"] <= 2), None)
        if weak:
            insights.append({
                "level": "warning",
                "title": "Слабая позиция",
                "text": f'{weak["item_name"]}: только {weak["quantity"]:.0f} продаж за период.',
            })
        return insights
