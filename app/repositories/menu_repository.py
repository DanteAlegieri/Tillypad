from datetime import date, timedelta
from typing import Any

from app.db.sql_server import SqlServer


class MenuRepository:
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

    def _menu_group_name_column(self) -> str | None:
        candidates = [
            "mgrp_Name",
            "mgrp_ShortName",
            "mgrp_Description",
        ]

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = 'dbo'
                  AND TABLE_NAME = 'tp_MenuGroups'
                """
            )
            columns = {str(row[0]) for row in cursor.fetchall()}

        for candidate in candidates:
            if candidate in columns:
                return candidate

        return None

    def groups(self) -> list[dict[str, Any]]:
        name_column = self._menu_group_name_column()

        if name_column is None:
            return []

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT
                    mgrp_ID AS group_id,
                    COALESCE(
                        NULLIF(LTRIM(RTRIM({name_column})), ''),
                        N'Без названия'
                    ) AS group_name
                FROM dbo.tp_MenuGroups
                ORDER BY group_name
                """
            )
            columns = [item[0] for item in cursor.description]
            return [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]

    def items(
        self,
        date_from: date | None,
        date_to: date | None,
        search: str = "",
        group_id: str = "",
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        start, end = self.normalize_period(date_from, date_to)
        end_exclusive = end + timedelta(days=1)
        clean_search = search.strip()
        search_pattern = f"%{clean_search}%"
        clean_group = group_id.strip()
        limit = max(1, min(limit, 2000))
        group_name_column = self._menu_group_name_column()

        if group_name_column:
            group_join = """
                LEFT JOIN dbo.tp_MenuGroups AS mg
                    ON mg.mgrp_ID = mi.mitm_mgrp_ID
            """
            group_select = f"""
                COALESCE(
                    NULLIF(LTRIM(RTRIM(mg.{group_name_column})), ''),
                    N'Без группы'
                ) AS group_name,
            """
            group_group_by = f"""
                COALESCE(
                    NULLIF(LTRIM(RTRIM(mg.{group_name_column})), ''),
                    N'Без группы'
                ),
            """
        else:
            group_join = ""
            group_select = "N'Без группы' AS group_name,"
            group_group_by = ""

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT TOP ({limit})
                    mi.mitm_ID AS item_id,
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(mi.mitm_Name)), ''),
                        N'Без названия'
                    ) AS item_name,
                    mi.mitm_Article AS article,
                    mi.mitm_Price AS current_price,
                    mi.mitm_IsDisabled AS is_disabled,
                    {group_select}
                    COALESCE(
                        SUM(
                            CASE
                                WHEN o.ordr_Date >= ?
                                 AND o.ordr_Date < ?
                                THEN CAST(oi.orit_Count AS decimal(18,4))
                                ELSE 0
                            END
                        ),
                        0
                    ) AS sold_quantity,
                    COALESCE(
                        SUM(
                            CASE
                                WHEN o.ordr_Date >= ?
                                 AND o.ordr_Date < ?
                                THEN
                                    CAST(oi.orit_Count AS decimal(18,4))
                                    * CAST(oi.orit_Price AS decimal(18,4))
                                ELSE 0
                            END
                        ),
                        0
                    ) AS revenue,
                    COUNT(
                        DISTINCT CASE
                            WHEN o.ordr_Date >= ?
                             AND o.ordr_Date < ?
                            THEN o.ordr_gest_ID
                            ELSE NULL
                        END
                    ) AS checks_count
                FROM dbo.tp_MenuItems AS mi
                LEFT JOIN dbo.tp_OrderItems AS oi
                    ON oi.orit_mitm_ID = mi.mitm_ID
                LEFT JOIN dbo.tp_Orders AS o
                    ON o.ordr_ID = oi.orit_ordr_ID
                {group_join}
                WHERE
                    (
                        ? = ''
                        OR mi.mitm_Name LIKE ?
                        OR mi.mitm_ShortName LIKE ?
                        OR mi.mitm_Article LIKE ?
                    )
                    AND (
                        ? = ''
                        OR CONVERT(nvarchar(36), mi.mitm_mgrp_ID) = ?
                    )
                GROUP BY
                    mi.mitm_ID,
                    mi.mitm_Name,
                    mi.mitm_Article,
                    mi.mitm_Price,
                    mi.mitm_IsDisabled,
                    {group_group_by}
                    mi.mitm_mgrp_ID
                ORDER BY
                    revenue DESC,
                    sold_quantity DESC,
                    item_name
                """,
                start,
                end_exclusive,
                start,
                end_exclusive,
                start,
                end_exclusive,
                clean_search,
                search_pattern,
                search_pattern,
                search_pattern,
                clean_group,
                clean_group,
            )
            columns = [item[0] for item in cursor.description]
            rows = [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]

        for row in rows:
            row["current_price"] = (
                float(row["current_price"])
                if row["current_price"] is not None
                else None
            )
            row["sold_quantity"] = float(row["sold_quantity"] or 0)
            row["revenue"] = float(row["revenue"] or 0)
            row["checks_count"] = int(row["checks_count"] or 0)
            row["is_disabled"] = bool(row["is_disabled"])

        return rows

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
                SELECT
                    COUNT(*) AS menu_items_count,
                    SUM(CASE WHEN mitm_IsDisabled = 1 THEN 1 ELSE 0 END) AS disabled_count
                FROM dbo.tp_MenuItems
                """
            )
            menu_row = cursor.fetchone()

            cursor.execute(
                """
                SELECT
                    COUNT(DISTINCT oi.orit_mitm_ID) AS sold_items_count,
                    COALESCE(
                        SUM(CAST(oi.orit_Count AS decimal(18,4))),
                        0
                    ) AS sold_quantity,
                    COALESCE(
                        SUM(
                            CAST(oi.orit_Count AS decimal(18,4))
                            * CAST(oi.orit_Price AS decimal(18,4))
                        ),
                        0
                    ) AS revenue
                FROM dbo.tp_OrderItems AS oi
                INNER JOIN dbo.tp_Orders AS o
                    ON o.ordr_ID = oi.orit_ordr_ID
                WHERE o.ordr_Date >= ?
                  AND o.ordr_Date < ?
                """,
                start,
                end_exclusive,
            )
            sales_row = cursor.fetchone()

        return {
            "date_from": start,
            "date_to": end,
            "menu_items_count": int(menu_row.menu_items_count or 0),
            "disabled_count": int(menu_row.disabled_count or 0),
            "sold_items_count": int(sales_row.sold_items_count or 0),
            "sold_quantity": float(sales_row.sold_quantity or 0),
            "revenue": float(sales_row.revenue or 0),
        }
