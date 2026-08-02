from datetime import date, timedelta
from typing import Any

from app.db.sql_server import SqlServer


class MarketingRepository:
    def __init__(self, database: SqlServer | None = None) -> None:
        self.database = database or SqlServer()

    @staticmethod
    def _rows(cursor: Any) -> list[dict[str, Any]]:
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def hourly_sales(
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
                    DATEPART(HOUR, c.chck_Date) AS sale_hour,
                    COUNT(DISTINCT c.chck_ID) AS checks_count,
                    SUM(
                        CAST(ci.chit_Count AS decimal(18,4))
                        * (
                            CAST(ci.chit_Price AS decimal(18,4))
                            - CAST(ci.chit_PriceDiscount AS decimal(18,4))
                            + CAST(ci.chit_PriceMargin AS decimal(18,4))
                        )
                    ) AS revenue
                FROM dbo.tp_Checks AS c
                INNER JOIN dbo.tp_CheckItems AS ci
                    ON ci.chit_chck_ID = c.chck_ID
                WHERE c.chck_Date >= ?
                  AND c.chck_Date < ?
                  AND ci.chit_Count > 0
                GROUP BY DATEPART(HOUR, c.chck_Date)
                ORDER BY sale_hour
                """,
                date_from,
                end_exclusive,
            )
            rows = self._rows(cursor)

        for row in rows:
            row["sale_hour"] = int(row.get("sale_hour") or 0)
            row["checks_count"] = int(row.get("checks_count") or 0)
            row["revenue"] = float(row.get("revenue") or 0)
        return rows

    def period_summary(
        self,
        date_from: date,
        date_to: date,
    ) -> dict[str, Any]:
        end_exclusive = date_to + timedelta(days=1)

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    COUNT(DISTINCT c.chck_ID) AS checks_count,
                    COALESCE(SUM(
                        CAST(ci.chit_Count AS decimal(18,4))
                        * (
                            CAST(ci.chit_Price AS decimal(18,4))
                            - CAST(ci.chit_PriceDiscount AS decimal(18,4))
                            + CAST(ci.chit_PriceMargin AS decimal(18,4))
                        )
                    ), 0) AS revenue
                FROM dbo.tp_Checks AS c
                INNER JOIN dbo.tp_CheckItems AS ci
                    ON ci.chit_chck_ID = c.chck_ID
                WHERE c.chck_Date >= ?
                  AND c.chck_Date < ?
                  AND ci.chit_Count > 0
                """,
                date_from,
                end_exclusive,
            )
            row = self._rows(cursor)[0]

        checks = int(row.get("checks_count") or 0)
        revenue = float(row.get("revenue") or 0)
        return {
            "checks_count": checks,
            "revenue": revenue,
            "avg_check": revenue / checks if checks else 0,
        }

    def top_items(
        self,
        date_from: date,
        date_to: date,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        end_exclusive = date_to + timedelta(days=1)
        safe_limit = max(1, min(int(limit), 20))

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT TOP ({safe_limit})
                    ci.chit_mitm_ID AS item_id,
                    mi.mitm_Name AS item_name,
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
                INNER JOIN dbo.tp_MenuItems AS mi
                    ON mi.mitm_ID = ci.chit_mitm_ID
                WHERE c.chck_Date >= ?
                  AND c.chck_Date < ?
                  AND ci.chit_Count > 0
                GROUP BY ci.chit_mitm_ID, mi.mitm_Name
                ORDER BY revenue DESC
                """,
                date_from,
                end_exclusive,
            )
            rows = self._rows(cursor)

        for row in rows:
            row["quantity"] = float(row.get("quantity") or 0)
            row["revenue"] = float(row.get("revenue") or 0)
        return rows


    def basket_opportunities(
        self,
        date_from: date,
        date_to: date,
        limit: int = 15,
    ) -> list[dict[str, Any]]:
        end_exclusive = date_to + timedelta(days=1)
        safe_limit = max(1, min(int(limit), 50))

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                WITH PositiveItems AS (
                    SELECT DISTINCT
                        c.chck_ID AS check_id,
                        ci.chit_mitm_ID AS item_id
                    FROM dbo.tp_CheckItems AS ci
                    INNER JOIN dbo.tp_Checks AS c
                        ON c.chck_ID = ci.chit_chck_ID
                    INNER JOIN dbo.tp_MenuItems AS mi
                        ON mi.mitm_ID = ci.chit_mitm_ID
                    WHERE c.chck_Date >= ?
                      AND c.chck_Date < ?
                      AND ci.chit_Count > 0
                      AND LOWER(LTRIM(RTRIM(COALESCE(mi.mitm_Name, N''))))
                          NOT IN (
                              N'доставка',
                              N'доставка курьером',
                              N'стоимость доставки',
                              N'самовывоз'
                          )
                ),
                ItemCounts AS (
                    SELECT
                        item_id,
                        COUNT(DISTINCT check_id) AS base_checks
                    FROM PositiveItems
                    GROUP BY item_id
                ),
                PairCounts AS (
                    SELECT
                        a.item_id AS base_item_id,
                        b.item_id AS pair_item_id,
                        COUNT(DISTINCT a.check_id) AS pair_checks
                    FROM PositiveItems AS a
                    INNER JOIN PositiveItems AS b
                        ON b.check_id = a.check_id
                       AND b.item_id <> a.item_id
                    GROUP BY a.item_id, b.item_id
                ),
                AveragePrices AS (
                    SELECT
                        ci.chit_mitm_ID AS item_id,
                        SUM(
                            CAST(ci.chit_Count AS decimal(18,4))
                            * (
                                CAST(ci.chit_Price AS decimal(18,4))
                                - CAST(ci.chit_PriceDiscount AS decimal(18,4))
                                + CAST(ci.chit_PriceMargin AS decimal(18,4))
                            )
                        ) / NULLIF(
                            SUM(CAST(ci.chit_Count AS decimal(18,4))),
                            0
                        ) AS avg_price
                    FROM dbo.tp_CheckItems AS ci
                    INNER JOIN dbo.tp_Checks AS c
                        ON c.chck_ID = ci.chit_chck_ID
                    INNER JOIN dbo.tp_MenuItems AS mi
                        ON mi.mitm_ID = ci.chit_mitm_ID
                    WHERE c.chck_Date >= ?
                      AND c.chck_Date < ?
                      AND ci.chit_Count > 0
                      AND LOWER(LTRIM(RTRIM(COALESCE(mi.mitm_Name, N''))))
                          NOT IN (
                              N'доставка',
                              N'доставка курьером',
                              N'стоимость доставки',
                              N'самовывоз'
                          )
                    GROUP BY ci.chit_mitm_ID
                ),
                RankedPairs AS (
                    SELECT
                        pc.base_item_id,
                        pc.pair_item_id,
                        pc.pair_checks,
                        ic.base_checks,
                        ROW_NUMBER() OVER (
                            PARTITION BY pc.base_item_id
                            ORDER BY pc.pair_checks DESC
                        ) AS pair_rank
                    FROM PairCounts AS pc
                    INNER JOIN ItemCounts AS ic
                        ON ic.item_id = pc.base_item_id
                    WHERE ic.base_checks >= 3
                )
                SELECT TOP ({safe_limit})
                    rp.base_item_id,
                    base_item.mitm_Name AS base_item_name,
                    rp.pair_item_id,
                    pair_item.mitm_Name AS pair_item_name,
                    rp.base_checks,
                    rp.pair_checks,
                    rp.base_checks - rp.pair_checks AS missing_checks,
                    rp.pair_checks * 100.0
                        / NULLIF(rp.base_checks, 0) AS attach_rate,
                    COALESCE(ap.avg_price, 0) AS pair_avg_price,
                    (
                        rp.base_checks - rp.pair_checks
                    ) * COALESCE(ap.avg_price, 0) * 0.15
                        AS estimated_potential
                FROM RankedPairs AS rp
                INNER JOIN dbo.tp_MenuItems AS base_item
                    ON base_item.mitm_ID = rp.base_item_id
                INNER JOIN dbo.tp_MenuItems AS pair_item
                    ON pair_item.mitm_ID = rp.pair_item_id
                LEFT JOIN AveragePrices AS ap
                    ON ap.item_id = rp.pair_item_id
                WHERE rp.pair_rank = 1
                  AND rp.base_checks > rp.pair_checks
                ORDER BY estimated_potential DESC
                """,
                date_from,
                end_exclusive,
                date_from,
                end_exclusive,
            )
            rows = self._rows(cursor)

        excluded_service_names = {
            "доставка",
            "доставка курьером",
            "стоимость доставки",
            "самовывоз",
        }
        clean_rows = []

        for row in rows:
            base_name = str(row.get("base_item_name") or "").strip().lower()
            pair_name = str(row.get("pair_item_name") or "").strip().lower()
            if (
                base_name in excluded_service_names
                or pair_name in excluded_service_names
            ):
                continue

            for key in (
                "attach_rate",
                "pair_avg_price",
                "estimated_potential",
            ):
                row[key] = float(row.get(key) or 0)
            for key in ("base_checks", "pair_checks", "missing_checks"):
                row[key] = int(row.get(key) or 0)
            clean_rows.append(row)

        return clean_rows
