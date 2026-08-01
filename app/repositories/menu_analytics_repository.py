from datetime import date, timedelta
from typing import Any

from app.db.sql_server import SqlServer


class MenuAnalyticsRepository:
    def __init__(self, database: SqlServer | None = None) -> None:
        self.database = database or SqlServer()

    @staticmethod
    def normalize_period(
        date_from: date | None,
        date_to: date | None,
    ) -> tuple[date, date]:
        today = date.today()
        end = date_to or today
        start = date_from or end.replace(day=1)
        if end < start:
            start, end = end, start
        return start, end

    @staticmethod
    def _rows(cursor: Any) -> list[dict[str, Any]]:
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def item_metrics(
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
                WITH ItemDaily AS (
                    SELECT
                        ci.chit_mitm_ID AS item_id,
                        CONVERT(date, c.chck_Date) AS sale_date,
                        SUM(CASE WHEN ci.chit_Count > 0
                            THEN CAST(ci.chit_Count AS decimal(18,4))
                            ELSE 0 END) AS quantity,
                        SUM(CASE WHEN ci.chit_Count > 0
                            THEN CAST(ci.chit_Count AS decimal(18,4))
                               * (
                                    CAST(ci.chit_Price AS decimal(18,4))
                                    - CAST(ci.chit_PriceDiscount AS decimal(18,4))
                                    + CAST(ci.chit_PriceMargin AS decimal(18,4))
                                 )
                            ELSE 0 END) AS revenue,
                        COUNT(DISTINCT c.chck_ID) AS checks_count
                    FROM dbo.tp_CheckItems AS ci
                    INNER JOIN dbo.tp_Checks AS c
                        ON c.chck_ID = ci.chit_chck_ID
                    WHERE c.chck_Date >= ?
                      AND c.chck_Date < ?
                      AND ci.chit_Count > 0
                    GROUP BY
                        ci.chit_mitm_ID,
                        CONVERT(date, c.chck_Date)
                ),
                DailyStats AS (
                    SELECT
                        item_id,
                        AVG(CAST(quantity AS float)) AS avg_daily_quantity,
                        STDEV(CAST(quantity AS float)) AS std_daily_quantity,
                        COUNT(*) AS active_days
                    FROM ItemDaily
                    GROUP BY item_id
                )
                SELECT
                    mi.mitm_ID AS item_id,
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(mi.mitm_Name)), N''),
                        N'Позиция без названия'
                    ) AS item_name,
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(mg.mgrp_Name)), N''),
                        N'Без категории'
                    ) AS group_name,
                    SUM(d.quantity) AS quantity,
                    SUM(d.revenue) AS revenue,
                    SUM(d.checks_count) AS checks_count,
                    CASE
                        WHEN SUM(d.quantity) > 0
                        THEN SUM(d.revenue) / SUM(d.quantity)
                        ELSE 0
                    END AS avg_price,
                    ds.avg_daily_quantity,
                    ds.std_daily_quantity,
                    ds.active_days
                FROM ItemDaily AS d
                INNER JOIN dbo.tp_MenuItems AS mi
                    ON mi.mitm_ID = d.item_id
                LEFT JOIN dbo.tp_MenuGroups AS mg
                    ON mg.mgrp_ID = mi.mitm_mgrp_ID
                LEFT JOIN DailyStats AS ds
                    ON ds.item_id = d.item_id
                GROUP BY
                    mi.mitm_ID,
                    mi.mitm_Name,
                    mg.mgrp_Name,
                    ds.avg_daily_quantity,
                    ds.std_daily_quantity,
                    ds.active_days
                ORDER BY revenue DESC
                """,
                start,
                end_exclusive,
            )
            return self._rows(cursor)

    def item_daily(
        self,
        item_id: str,
        date_from: date,
        date_to: date,
    ) -> list[dict[str, Any]]:
        end_exclusive = date_to + timedelta(days=1)

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    CONVERT(date, c.chck_Date) AS sale_date,
                    SUM(CAST(ci.chit_Count AS decimal(18,4))) AS quantity,
                    SUM(
                        CAST(ci.chit_Count AS decimal(18,4))
                        * (
                            CAST(ci.chit_Price AS decimal(18,4))
                            - CAST(ci.chit_PriceDiscount AS decimal(18,4))
                            + CAST(ci.chit_PriceMargin AS decimal(18,4))
                        )
                    ) AS revenue,
                    COUNT(DISTINCT c.chck_ID) AS checks_count
                FROM dbo.tp_CheckItems AS ci
                INNER JOIN dbo.tp_Checks AS c
                    ON c.chck_ID = ci.chit_chck_ID
                WHERE ci.chit_mitm_ID = ?
                  AND c.chck_Date >= ?
                  AND c.chck_Date < ?
                  AND ci.chit_Count > 0
                GROUP BY CONVERT(date, c.chck_Date)
                ORDER BY sale_date
                """,
                item_id,
                date_from,
                end_exclusive,
            )
            return self._rows(cursor)

    def item_hourly(
        self,
        item_id: str,
        date_from: date,
        date_to: date,
    ) -> list[dict[str, Any]]:
        end_exclusive = date_to + timedelta(days=1)

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    DATEPART(hour, c.chck_Date) AS sale_hour,
                    SUM(CAST(ci.chit_Count AS decimal(18,4))) AS quantity,
                    SUM(
                        CAST(ci.chit_Count AS decimal(18,4))
                        * (
                            CAST(ci.chit_Price AS decimal(18,4))
                            - CAST(ci.chit_PriceDiscount AS decimal(18,4))
                            + CAST(ci.chit_PriceMargin AS decimal(18,4))
                        )
                    ) AS revenue
                FROM dbo.tp_CheckItems AS ci
                INNER JOIN dbo.tp_Checks AS c
                    ON c.chck_ID = ci.chit_chck_ID
                WHERE ci.chit_mitm_ID = ?
                  AND c.chck_Date >= ?
                  AND c.chck_Date < ?
                  AND ci.chit_Count > 0
                GROUP BY DATEPART(hour, c.chck_Date)
                ORDER BY sale_hour
                """,
                item_id,
                date_from,
                end_exclusive,
            )
            return self._rows(cursor)

    def basket_pairs(
        self,
        item_id: str,
        date_from: date,
        date_to: date,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        end_exclusive = date_to + timedelta(days=1)
        safe_limit = max(1, min(limit, 30))

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                WITH BaseChecks AS (
                    SELECT DISTINCT ci.chit_chck_ID AS check_id
                    FROM dbo.tp_CheckItems AS ci
                    INNER JOIN dbo.tp_Checks AS c
                        ON c.chck_ID = ci.chit_chck_ID
                    WHERE ci.chit_mitm_ID = ?
                      AND c.chck_Date >= ?
                      AND c.chck_Date < ?
                      AND ci.chit_Count > 0
                ),
                PairCounts AS (
                    SELECT
                        ci.chit_mitm_ID AS pair_item_id,
                        COUNT(DISTINCT ci.chit_chck_ID) AS pair_checks
                    FROM dbo.tp_CheckItems AS ci
                    INNER JOIN BaseChecks AS bc
                        ON bc.check_id = ci.chit_chck_ID
                    WHERE ci.chit_mitm_ID <> ?
                      AND ci.chit_Count > 0
                    GROUP BY ci.chit_mitm_ID
                ),
                BaseCount AS (
                    SELECT COUNT(*) AS base_checks FROM BaseChecks
                )
                SELECT TOP ({safe_limit})
                    mi.mitm_ID AS item_id,
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(mi.mitm_Name)), N''),
                        N'Позиция без названия'
                    ) AS item_name,
                    pc.pair_checks,
                    bc.base_checks,
                    CASE
                        WHEN bc.base_checks > 0
                        THEN pc.pair_checks * 100.0 / bc.base_checks
                        ELSE 0
                    END AS attach_rate
                FROM PairCounts AS pc
                CROSS JOIN BaseCount AS bc
                INNER JOIN dbo.tp_MenuItems AS mi
                    ON mi.mitm_ID = pc.pair_item_id
                ORDER BY pc.pair_checks DESC
                """,
                item_id,
                date_from,
                end_exclusive,
                item_id,
            )
            return self._rows(cursor)

    def item_info(self, item_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT TOP (1)
                    mi.mitm_ID AS item_id,
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(mi.mitm_Name)), N''),
                        N'Позиция без названия'
                    ) AS item_name,
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(mg.mgrp_Name)), N''),
                        N'Без категории'
                    ) AS group_name,
                    mi.mitm_Description AS description
                FROM dbo.tp_MenuItems AS mi
                LEFT JOIN dbo.tp_MenuGroups AS mg
                    ON mg.mgrp_ID = mi.mitm_mgrp_ID
                WHERE mi.mitm_ID = ?
                """,
                item_id,
            )
            rows = self._rows(cursor)
            return rows[0] if rows else None
