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

    @staticmethod
    def _rows(cursor: Any) -> list[dict[str, Any]]:
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def summary(
        self,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        start, end = self.normalize_period(date_from, date_to)
        end_exclusive = end + timedelta(days=1)

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                WITH CheckTotals AS (
                    SELECT
                        c.chck_ID AS check_id,
                        c.chck_Date AS check_date,
                        SUM(
                            CAST(ci.chit_Count AS decimal(18,4))
                            * (
                                CAST(ci.chit_Price AS decimal(18,4))
                                - CAST(ci.chit_PriceDiscount AS decimal(18,4))
                                + CAST(ci.chit_PriceMargin AS decimal(18,4))
                            )
                        ) AS check_sum,
                        SUM(
                            CASE
                                WHEN ci.chit_Count > 0
                                THEN CAST(ci.chit_Count AS decimal(18,4))
                                ELSE 0
                            END
                        ) AS item_count
                    FROM dbo.tp_Checks AS c
                    INNER JOIN dbo.tp_CheckItems AS ci
                        ON ci.chit_chck_ID = c.chck_ID
                    WHERE c.chck_Date >= ?
                      AND c.chck_Date < ?
                    GROUP BY c.chck_ID, c.chck_Date
                )
                SELECT
                    COALESCE(
                        SUM(CASE WHEN check_sum > 0 THEN check_sum ELSE 0 END),
                        0
                    ) AS revenue,
                    SUM(CASE WHEN check_sum > 0 THEN 1 ELSE 0 END)
                        AS checks_count,
                    COALESCE(
                        AVG(CASE WHEN check_sum > 0 THEN check_sum END),
                        0
                    ) AS avg_check,
                    COALESCE(
                        SUM(CASE WHEN check_sum > 0 THEN item_count ELSE 0 END),
                        0
                    ) AS item_count,
                    COALESCE(
                        MAX(CASE WHEN check_sum > 0 THEN check_sum END),
                        0
                    ) AS max_check,
                    COALESCE(
                        MIN(CASE WHEN check_sum > 0 THEN check_sum END),
                        0
                    ) AS min_check,
                    ABS(
                        COALESCE(
                            SUM(CASE WHEN check_sum < 0 THEN check_sum ELSE 0 END),
                            0
                        )
                    ) AS refunds_sum,
                    SUM(CASE WHEN check_sum < 0 THEN 1 ELSE 0 END)
                        AS refunds_count
                FROM CheckTotals
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
            "max_check": float(row.max_check or 0),
            "min_check": float(row.min_check or 0),
            "refunds_sum": float(row.refunds_sum or 0),
            "refunds_count": int(row.refunds_count or 0),
        }

    def daily_sales(
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
                WITH CheckTotals AS (
                    SELECT
                        c.chck_ID AS check_id,
                        CONVERT(date, c.chck_Date) AS sale_date,
                        SUM(
                            CAST(ci.chit_Count AS decimal(18,4))
                            * (
                                CAST(ci.chit_Price AS decimal(18,4))
                                - CAST(ci.chit_PriceDiscount AS decimal(18,4))
                                + CAST(ci.chit_PriceMargin AS decimal(18,4))
                            )
                        ) AS check_sum
                    FROM dbo.tp_Checks AS c
                    INNER JOIN dbo.tp_CheckItems AS ci
                        ON ci.chit_chck_ID = c.chck_ID
                    WHERE c.chck_Date >= ?
                      AND c.chck_Date < ?
                    GROUP BY c.chck_ID, CONVERT(date, c.chck_Date)
                )
                SELECT
                    sale_date,
                    SUM(CASE WHEN check_sum > 0 THEN check_sum ELSE 0 END)
                        AS revenue,
                    SUM(CASE WHEN check_sum > 0 THEN 1 ELSE 0 END)
                        AS checks_count,
                    COALESCE(
                        AVG(CASE WHEN check_sum > 0 THEN check_sum END),
                        0
                    ) AS avg_check
                FROM CheckTotals
                GROUP BY sale_date
                ORDER BY sale_date
                """,
                start,
                end_exclusive,
            )
            rows = self._rows(cursor)

        for row in rows:
            row["sale_date"] = str(row["sale_date"])
            row["revenue"] = float(row.get("revenue") or 0)
            row["checks_count"] = int(row.get("checks_count") or 0)
            row["avg_check"] = float(row.get("avg_check") or 0)
        return rows

    def hourly_sales(
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
                WITH CheckTotals AS (
                    SELECT
                        c.chck_ID AS check_id,
                        DATEPART(hour, c.chck_Date) AS sale_hour,
                        SUM(
                            CAST(ci.chit_Count AS decimal(18,4))
                            * (
                                CAST(ci.chit_Price AS decimal(18,4))
                                - CAST(ci.chit_PriceDiscount AS decimal(18,4))
                                + CAST(ci.chit_PriceMargin AS decimal(18,4))
                            )
                        ) AS check_sum
                    FROM dbo.tp_Checks AS c
                    INNER JOIN dbo.tp_CheckItems AS ci
                        ON ci.chit_chck_ID = c.chck_ID
                    WHERE c.chck_Date >= ?
                      AND c.chck_Date < ?
                    GROUP BY c.chck_ID, DATEPART(hour, c.chck_Date)
                )
                SELECT
                    sale_hour,
                    SUM(CASE WHEN check_sum > 0 THEN check_sum ELSE 0 END)
                        AS revenue,
                    SUM(CASE WHEN check_sum > 0 THEN 1 ELSE 0 END)
                        AS checks_count,
                    COALESCE(
                        AVG(CASE WHEN check_sum > 0 THEN check_sum END),
                        0
                    ) AS avg_check
                FROM CheckTotals
                GROUP BY sale_hour
                ORDER BY sale_hour
                """,
                start,
                end_exclusive,
            )
            rows = self._rows(cursor)

        for row in rows:
            row["sale_hour"] = int(row.get("sale_hour") or 0)
            row["revenue"] = float(row.get("revenue") or 0)
            row["checks_count"] = int(row.get("checks_count") or 0)
            row["avg_check"] = float(row.get("avg_check") or 0)
        return rows

    def top_items(
        self,
        date_from: date | None,
        date_to: date | None,
        limit: int = 15,
    ) -> list[dict[str, Any]]:
        start, end = self.normalize_period(date_from, date_to)
        end_exclusive = end + timedelta(days=1)
        safe_limit = max(1, min(int(limit), 100))

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT TOP ({safe_limit})
                    mi.mitm_ID AS item_id,
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(mi.mitm_Name)), N''),
                        NULLIF(LTRIM(RTRIM(ci.chit_Comment)), N''),
                        N'Позиция без названия'
                    ) AS item_name,
                    SUM(
                        CASE WHEN ci.chit_Count > 0
                        THEN CAST(ci.chit_Count AS decimal(18,4))
                        ELSE 0 END
                    ) AS quantity,
                    SUM(
                        CASE WHEN ci.chit_Count > 0
                        THEN
                            CAST(ci.chit_Count AS decimal(18,4))
                            * (
                                CAST(ci.chit_Price AS decimal(18,4))
                                - CAST(ci.chit_PriceDiscount AS decimal(18,4))
                                + CAST(ci.chit_PriceMargin AS decimal(18,4))
                            )
                        ELSE 0 END
                    ) AS revenue,
                    COUNT(DISTINCT c.chck_ID) AS checks_count
                FROM dbo.tp_CheckItems AS ci
                INNER JOIN dbo.tp_Checks AS c
                    ON c.chck_ID = ci.chit_chck_ID
                LEFT JOIN dbo.tp_MenuItems AS mi
                    ON mi.mitm_ID = ci.chit_mitm_ID
                WHERE c.chck_Date >= ?
                  AND c.chck_Date < ?
                  AND ci.chit_Count > 0
                GROUP BY
                    mi.mitm_ID,
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(mi.mitm_Name)), N''),
                        NULLIF(LTRIM(RTRIM(ci.chit_Comment)), N''),
                        N'Позиция без названия'
                    )
                ORDER BY revenue DESC, quantity DESC
                """,
                start,
                end_exclusive,
            )
            rows = self._rows(cursor)

        for row in rows:
            row["quantity"] = float(row.get("quantity") or 0)
            row["revenue"] = float(row.get("revenue") or 0)
            row["checks_count"] = int(row.get("checks_count") or 0)
        return rows

    def top_groups(
        self,
        date_from: date | None,
        date_to: date | None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        start, end = self.normalize_period(date_from, date_to)
        end_exclusive = end + timedelta(days=1)
        safe_limit = max(1, min(int(limit), 50))

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT TOP ({safe_limit})
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(mg.mgrp_Name)), N''),
                        N'Без категории'
                    ) AS group_name,
                    SUM(
                        CAST(ci.chit_Count AS decimal(18,4))
                        * (
                            CAST(ci.chit_Price AS decimal(18,4))
                            - CAST(ci.chit_PriceDiscount AS decimal(18,4))
                            + CAST(ci.chit_PriceMargin AS decimal(18,4))
                        )
                    ) AS revenue,
                    SUM(CAST(ci.chit_Count AS decimal(18,4))) AS quantity
                FROM dbo.tp_CheckItems AS ci
                INNER JOIN dbo.tp_Checks AS c
                    ON c.chck_ID = ci.chit_chck_ID
                LEFT JOIN dbo.tp_MenuItems AS mi
                    ON mi.mitm_ID = ci.chit_mitm_ID
                LEFT JOIN dbo.tp_MenuGroups AS mg
                    ON mg.mgrp_ID = mi.mitm_mgrp_ID
                WHERE c.chck_Date >= ?
                  AND c.chck_Date < ?
                  AND ci.chit_Count > 0
                GROUP BY
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(mg.mgrp_Name)), N''),
                        N'Без категории'
                    )
                ORDER BY revenue DESC
                """,
                start,
                end_exclusive,
            )
            rows = self._rows(cursor)

        for row in rows:
            row["revenue"] = float(row.get("revenue") or 0)
            row["quantity"] = float(row.get("quantity") or 0)
        return rows

    def payment_mix(
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
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(pt.pytp_Name)), N''),
                        N'Не определено'
                    ) AS payment_name,
                    SUM(
                        CASE WHEN cp.chpy_Sum > 0
                        THEN cp.chpy_Sum ELSE 0 END
                    ) AS payment_sum,
                    COUNT(DISTINCT cp.chpy_chck_ID) AS checks_count
                FROM dbo.tp_CheckPayments AS cp
                INNER JOIN dbo.tp_Checks AS c
                    ON c.chck_ID = cp.chpy_chck_ID
                LEFT JOIN dbo.tp_PayTypes AS pt
                    ON pt.pytp_ID = cp.chpy_pytp_ID
                WHERE c.chck_Date >= ?
                  AND c.chck_Date < ?
                  AND cp.chpy_Sum > 0
                GROUP BY
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(pt.pytp_Name)), N''),
                        N'Не определено'
                    )
                ORDER BY payment_sum DESC
                """,
                start,
                end_exclusive,
            )
            rows = self._rows(cursor)

        for row in rows:
            row["payment_sum"] = float(row.get("payment_sum") or 0)
            row["checks_count"] = int(row.get("checks_count") or 0)
        return rows

    def recent_checks(
        self,
        date_from: date | None,
        date_to: date | None,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        start, end = self.normalize_period(date_from, date_to)
        end_exclusive = end + timedelta(days=1)
        safe_limit = max(1, min(int(limit), 100))

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                WITH CheckTotals AS (
                    SELECT
                        c.chck_ID AS check_id,
                        c.chck_Date AS check_date,
                        c.chck_Name AS check_name,
                        u.usr_Name AS cashier_name,
                        SUM(
                            CAST(ci.chit_Count AS decimal(18,4))
                            * (
                                CAST(ci.chit_Price AS decimal(18,4))
                                - CAST(ci.chit_PriceDiscount AS decimal(18,4))
                                + CAST(ci.chit_PriceMargin AS decimal(18,4))
                            )
                        ) AS check_sum,
                        SUM(
                            CASE WHEN ci.chit_Count > 0
                            THEN CAST(ci.chit_Count AS decimal(18,4))
                            ELSE 0 END
                        ) AS item_count
                    FROM dbo.tp_Checks AS c
                    INNER JOIN dbo.tp_CheckItems AS ci
                        ON ci.chit_chck_ID = c.chck_ID
                    LEFT JOIN dbo.tp_Users AS u
                        ON u.usr_ID = c.chck_usr_ID
                    WHERE c.chck_Date >= ?
                      AND c.chck_Date < ?
                    GROUP BY
                        c.chck_ID,
                        c.chck_Date,
                        c.chck_Name,
                        u.usr_Name
                )
                SELECT TOP ({safe_limit})
                    check_id,
                    check_date,
                    check_name,
                    cashier_name,
                    check_sum,
                    item_count
                FROM CheckTotals
                WHERE check_sum > 0
                ORDER BY check_date DESC
                """,
                start,
                end_exclusive,
            )
            rows = self._rows(cursor)

        for row in rows:
            row["check_sum"] = float(row.get("check_sum") or 0)
            row["item_count"] = float(row.get("item_count") or 0)
        return rows

    def comparison(
        self,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        start, end = self.normalize_period(date_from, date_to)
        period_days = (end - start).days + 1
        previous_end = start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=period_days - 1)

        current = self.summary(start, end)
        previous = self.summary(previous_start, previous_end)

        def change(
            current_value: float,
            previous_value: float,
        ) -> float | None:
            if previous_value == 0:
                return None
            return round(
                ((current_value - previous_value) / previous_value) * 100,
                1,
            )

        return {
            "previous_date_from": previous_start,
            "previous_date_to": previous_end,
            "previous": previous,
            "revenue_change": change(
                float(current["revenue"]),
                float(previous["revenue"]),
            ),
            "checks_change": change(
                float(current["checks_count"]),
                float(previous["checks_count"]),
            ),
            "avg_check_change": change(
                float(current["avg_check"]),
                float(previous["avg_check"]),
            ),
            "item_count_change": change(
                float(current["item_count"]),
                float(previous["item_count"]),
            ),
        }
