from __future__ import annotations

from datetime import date
from typing import Any


class QueryRegistryError(ValueError):
    pass


class QueryRegistry:
    """
    Разрешённые именованные запросы.
    Произвольный SQL по WebSocket не принимается.
    """

    @staticmethod
    def _require_date(value: Any, name: str) -> date:
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value))
        except (TypeError, ValueError) as exc:
            raise QueryRegistryError(
                f"Параметр {name} должен быть датой YYYY-MM-DD"
            ) from exc

    def handlers(self) -> dict[str, Any]:
        return {
            "sales_summary": self.sales_summary,
            "sales_hourly": self.sales_hourly,
            "menu_items": self.menu_items,
            "latest_sale": self.latest_sale,
            "payment_summary": self.payment_summary,
            "purchases_summary": self.purchases_summary,
            "delivery_summary": self.delivery_summary,
            "basket_pairs": self.basket_pairs,
            "health_check": self.health_check,
        }

    def names(self) -> list[str]:
        return sorted(self.handlers())

    def build(
        self,
        query_name: str,
        parameters: dict[str, Any],
    ) -> tuple[str, list[Any]]:
        handler = self.handlers().get(query_name)
        if handler is None:
            raise QueryRegistryError(
                f"Запрос '{query_name}' не разрешён"
            )
        return handler(parameters)

    def health_check(
        self,
        parameters: dict[str, Any],
    ) -> tuple[str, list[Any]]:
        return (
            """
            SELECT
                DB_NAME() AS database_name,
                GETDATE() AS server_time,
                1 AS ok
            """,
            [],
        )

    def sales_summary(
        self,
        parameters: dict[str, Any],
    ) -> tuple[str, list[Any]]:
        date_from = self._require_date(parameters.get("date_from"), "date_from")
        date_to = self._require_date(parameters.get("date_to"), "date_to")

        return (
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
              AND c.chck_Date < DATEADD(day, 1, ?)
              AND ci.chit_Count > 0
            """,
            [date_from, date_to],
        )

    def sales_hourly(
        self,
        parameters: dict[str, Any],
    ) -> tuple[str, list[Any]]:
        date_from = self._require_date(parameters.get("date_from"), "date_from")
        date_to = self._require_date(parameters.get("date_to"), "date_to")

        return (
            """
            SELECT
                DATEPART(hour, c.chck_Date) AS sale_hour,
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
              AND c.chck_Date < DATEADD(day, 1, ?)
              AND ci.chit_Count > 0
            GROUP BY DATEPART(hour, c.chck_Date)
            ORDER BY sale_hour
            """,
            [date_from, date_to],
        )

    def menu_items(
        self,
        parameters: dict[str, Any],
    ) -> tuple[str, list[Any]]:
        date_from = self._require_date(parameters.get("date_from"), "date_from")
        date_to = self._require_date(parameters.get("date_to"), "date_to")

        return (
            """
            SELECT
                mi.mitm_ID AS item_id,
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
              AND c.chck_Date < DATEADD(day, 1, ?)
              AND ci.chit_Count > 0
            GROUP BY mi.mitm_ID, mi.mitm_Name
            ORDER BY revenue DESC
            """,
            [date_from, date_to],
        )

    def latest_sale(
        self,
        parameters: dict[str, Any],
    ) -> tuple[str, list[Any]]:
        date_from = self._require_date(parameters.get("date_from"), "date_from")
        date_to = self._require_date(parameters.get("date_to"), "date_to")

        return (
            """
            SELECT TOP (1)
                mi.mitm_ID AS item_id,
                mi.mitm_Name AS item_name,
                c.chck_Date AS sale_at,
                CAST(ci.chit_Count AS decimal(18,4)) AS quantity,
                CAST(ci.chit_Count AS decimal(18,4))
                * (
                    CAST(ci.chit_Price AS decimal(18,4))
                    - CAST(ci.chit_PriceDiscount AS decimal(18,4))
                    + CAST(ci.chit_PriceMargin AS decimal(18,4))
                ) AS amount
            FROM dbo.tp_CheckItems AS ci
            INNER JOIN dbo.tp_Checks AS c
                ON c.chck_ID = ci.chit_chck_ID
            INNER JOIN dbo.tp_MenuItems AS mi
                ON mi.mitm_ID = ci.chit_mitm_ID
            WHERE c.chck_Date >= ?
              AND c.chck_Date < DATEADD(day, 1, ?)
              AND ci.chit_Count > 0
            ORDER BY c.chck_Date DESC, ci.chit_ID DESC
            """,
            [date_from, date_to],
        )

    def payment_summary(
        self,
        parameters: dict[str, Any],
    ) -> tuple[str, list[Any]]:
        date_from = self._require_date(
            parameters.get("date_from"),
            "date_from",
        )
        date_to = self._require_date(
            parameters.get("date_to"),
            "date_to",
        )

        return (
            """
            SELECT
                p.pytp_ID AS payment_type_id,
                p.pytp_Name AS payment_type_name,
                CAST(p.pytp_IsCash AS int) AS is_cash,
                COUNT(DISTINCT cp.chpy_chck_ID) AS checks_count,
                COALESCE(
                    SUM(CAST(cp.chpy_Sum AS decimal(18,4))),
                    0
                ) AS amount
            FROM dbo.tp_CheckPayments AS cp
            INNER JOIN dbo.tp_Checks AS c
                ON c.chck_ID = cp.chpy_chck_ID
            LEFT JOIN dbo.tp_PayTypes AS p
                ON p.pytp_ID = cp.chpy_pytp_ID
            WHERE c.chck_Date >= ?
              AND c.chck_Date < DATEADD(day, 1, ?)
            GROUP BY
                p.pytp_ID,
                p.pytp_Name,
                p.pytp_IsCash
            ORDER BY amount DESC
            """,
            [date_from, date_to],
        )


    def purchases_summary(
        self,
        parameters: dict[str, Any],
    ) -> tuple[str, list[Any]]:
        date_from = self._require_date(
            parameters.get("date_from"),
            "date_from",
        )
        date_to = self._require_date(
            parameters.get("date_to"),
            "date_to",
        )

        return (
            """
            SELECT
                d.idoc_ID AS document_id,
                CONVERT(date, d.idoc_Date) AS document_date,
                d.idoc_Name AS document_name,
                d.idoc_ExternalName AS external_name,
                d.idoc_part_ID AS supplier_id,
                p.part_Name AS supplier_name,
                d.idoc_stor_ID AS store_id,
                d.idoc_idst_ID AS document_state,
                COUNT(i.idit_ID) AS items_count,
                COALESCE(
                    SUM(
                        CASE
                            WHEN ISNULL(i.idit_IsDeleted, 0) = 0
                            THEN CAST(i.idit_Sum AS decimal(18,4))
                            ELSE 0
                        END
                    ),
                    0
                ) AS amount,
                COALESCE(
                    SUM(
                        CASE
                            WHEN ISNULL(i.idit_IsDeleted, 0) = 0
                            THEN CAST(i.idit_SumVAT AS decimal(18,4))
                            ELSE 0
                        END
                    ),
                    0
                ) AS vat_amount
            FROM dbo.tp_InputDocuments AS d
            INNER JOIN dbo.tp_InputDocumentItems AS i
                ON i.idit_idoc_ID = d.idoc_ID
            LEFT JOIN dbo.tp_Partners AS p
                ON p.part_ID = d.idoc_part_ID
            WHERE d.idoc_Date >= ?
              AND d.idoc_Date < DATEADD(day, 1, ?)
              AND d.idoc_idst_ID = 1
            GROUP BY
                d.idoc_ID,
                CONVERT(date, d.idoc_Date),
                d.idoc_Name,
                d.idoc_ExternalName,
                d.idoc_part_ID,
                p.part_Name,
                d.idoc_stor_ID,
                d.idoc_idst_ID
            ORDER BY d.idoc_Date, d.idoc_Name
            """,
            [date_from, date_to],
        )


    def delivery_summary(
        self,
        parameters: dict[str, Any],
    ) -> tuple[str, list[Any]]:
        date_from = self._require_date(parameters.get("date_from"), "date_from")
        date_to = self._require_date(parameters.get("date_to"), "date_to")

        return (
            """
            SELECT
                COUNT(*) AS deliveries_count,
                AVG(CASE
                    WHEN gd.gsdlv_DateDelivered IS NOT NULL
                    THEN DATEDIFF(
                        second,
                        gd.gsdlv_Date,
                        gd.gsdlv_DateDelivered
                    ) / 60.0
                    ELSE NULL
                END) AS avg_delivery_minutes
            FROM dbo.tp_GuestDeliveries AS gd
            WHERE gd.gsdlv_Date >= ?
              AND gd.gsdlv_Date < DATEADD(day, 1, ?)
            """,
            [date_from, date_to],
        )

    def basket_pairs(
        self,
        parameters: dict[str, Any],
    ) -> tuple[str, list[Any]]:
        date_from = self._require_date(parameters.get("date_from"), "date_from")
        date_to = self._require_date(parameters.get("date_to"), "date_to")

        return (
            """
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
                  AND c.chck_Date < DATEADD(day, 1, ?)
                  AND ci.chit_Count > 0
                  AND LOWER(LTRIM(RTRIM(COALESCE(mi.mitm_Name, N''))))
                      NOT IN (
                          N'доставка',
                          N'доставка курьером',
                          N'стоимость доставки',
                          N'самовывоз'
                      )
            )
            SELECT TOP (100)
                a.item_id AS base_item_id,
                b.item_id AS pair_item_id,
                COUNT(DISTINCT a.check_id) AS pair_checks
            FROM PositiveItems AS a
            INNER JOIN PositiveItems AS b
                ON b.check_id = a.check_id
               AND b.item_id <> a.item_id
            GROUP BY a.item_id, b.item_id
            ORDER BY pair_checks DESC
            """,
            [date_from, date_to],
        )
