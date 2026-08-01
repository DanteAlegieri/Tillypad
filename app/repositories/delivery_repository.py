from datetime import date
from typing import Any

from app.db.sql_server import SqlServer


class DeliveryRepository:
    def __init__(self, database: SqlServer | None = None) -> None:
        self.database = database or SqlServer()

    @staticmethod
    def _rows(cursor) -> list[dict[str, Any]]:
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def load(self, date_from: date, date_to: date) -> dict[str, Any]:
        with self.database.connect() as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total_orders,
                    SUM(CASE WHEN gd.gsdlv_dlvrmt_ID = 1 THEN 1 ELSE 0 END)
                        AS courier_orders,
                    SUM(CASE WHEN gd.gsdlv_dlvrmt_ID = 2 THEN 1 ELSE 0 END)
                        AS pickup_orders,
                    SUM(CASE WHEN gd.gsdlv_dlvrst_ID = 1 THEN 1 ELSE 0 END)
                        AS completed_orders,
                    SUM(CASE WHEN gd.gsdlv_dlvrst_ID IN (4, 8) THEN 1 ELSE 0 END)
                        AS cancelled_orders,
                    AVG(
                        CASE
                            WHEN gd.gsdlv_DateDelivered IS NOT NULL
                            THEN DATEDIFF(second, gd.gsdlv_Date, gd.gsdlv_DateDelivered) / 60.0
                        END
                    ) AS avg_total_minutes,
                    SUM(
                        CASE
                            WHEN gd.gsdlv_DateDelivered IS NOT NULL
                             AND DATEDIFF(
                                    second,
                                    gd.gsdlv_Date,
                                    gd.gsdlv_DateDelivered
                                 ) <= (
                                    COALESCE(gd.gsdlv_CookingTime, 0)
                                    + COALESCE(gd.gsdlv_DeliveryTime, 0)
                                 )
                            THEN 1 ELSE 0
                        END
                    ) AS on_time_orders,
                    SUM(
                        CASE
                            WHEN gd.gsdlv_DateDelivered IS NOT NULL
                            THEN 1 ELSE 0
                        END
                    ) AS measured_orders
                FROM dbo.tp_GuestDeliveries AS gd
                WHERE gd.gsdlv_Date >= ?
                  AND gd.gsdlv_Date < DATEADD(day, 1, ?)
                """,
                date_from,
                date_to,
            )
            summary = self._rows(cursor)[0]

            cursor.execute(
                """
                WITH StageTimes AS (
                    SELECT
                        l.gsdlvsl_gsdlv_gest_ID AS delivery_id,
                        l.gsdlvsl_dlvrst_ID AS state_id,
                        l.gsdlvsl_Date AS state_date,
                        LEAD(l.gsdlvsl_Date) OVER (
                            PARTITION BY l.gsdlvsl_gsdlv_gest_ID
                            ORDER BY l.gsdlvsl_Date
                        ) AS next_date
                    FROM dbo.tp_GuestDeliveryStateLog AS l
                )
                SELECT
                    AVG(
                        CASE WHEN state_id = 3
                        THEN DATEDIFF(second, state_date, next_date) / 60.0 END
                    ) AS avg_wait_kitchen_minutes,
                    AVG(
                        CASE WHEN state_id = 5
                        THEN DATEDIFF(second, state_date, next_date) / 60.0 END
                    ) AS avg_cooking_minutes,
                    AVG(
                        CASE WHEN state_id = 6
                        THEN DATEDIFF(second, state_date, next_date) / 60.0 END
                    ) AS avg_wait_courier_minutes,
                    AVG(
                        CASE WHEN state_id = 7
                        THEN DATEDIFF(second, state_date, next_date) / 60.0 END
                    ) AS avg_road_minutes
                FROM StageTimes AS st
                INNER JOIN dbo.tp_GuestDeliveries AS gd
                    ON gd.gsdlv_gest_ID = st.delivery_id
                WHERE gd.gsdlv_Date >= ?
                  AND gd.gsdlv_Date < DATEADD(day, 1, ?)
                """,
                date_from,
                date_to,
            )
            stages = self._rows(cursor)[0]

            cursor.execute(
                """
                SELECT
                    CAST(gd.gsdlv_Date AS date) AS sale_date,
                    COUNT(*) AS orders_count,
                    SUM(CASE WHEN gd.gsdlv_dlvrmt_ID = 1 THEN 1 ELSE 0 END)
                        AS courier_count,
                    SUM(CASE WHEN gd.gsdlv_dlvrmt_ID = 2 THEN 1 ELSE 0 END)
                        AS pickup_count,
                    AVG(
                        CASE
                            WHEN gd.gsdlv_DateDelivered IS NOT NULL
                            THEN DATEDIFF(second, gd.gsdlv_Date, gd.gsdlv_DateDelivered) / 60.0
                        END
                    ) AS avg_minutes,
                    SUM(
                        CASE
                            WHEN gd.gsdlv_DateDelivered IS NOT NULL
                            THEN 1 ELSE 0
                        END
                    ) AS measured_orders,
                    SUM(
                        CASE
                            WHEN gd.gsdlv_DateDelivered IS NOT NULL
                             AND DATEDIFF(
                                    second,
                                    gd.gsdlv_Date,
                                    gd.gsdlv_DateDelivered
                                 ) <= (
                                    COALESCE(gd.gsdlv_CookingTime, 0)
                                    + COALESCE(gd.gsdlv_DeliveryTime, 0)
                                 )
                            THEN 1 ELSE 0
                        END
                    ) AS on_time_orders,
                    SUM(
                        CASE
                            WHEN gd.gsdlv_DateDelivered IS NOT NULL
                             AND DATEDIFF(
                                    second,
                                    gd.gsdlv_Date,
                                    gd.gsdlv_DateDelivered
                                 ) > (
                                    COALESCE(gd.gsdlv_CookingTime, 0)
                                    + COALESCE(gd.gsdlv_DeliveryTime, 0)
                                 )
                            THEN 1 ELSE 0
                        END
                    ) AS overdue_orders
                FROM dbo.tp_GuestDeliveries AS gd
                WHERE gd.gsdlv_Date >= ?
                  AND gd.gsdlv_Date < DATEADD(day, 1, ?)
                GROUP BY CAST(gd.gsdlv_Date AS date)
                ORDER BY sale_date
                """,
                date_from,
                date_to,
            )
            daily = self._rows(cursor)

            cursor.execute(
                """
                WITH RoadTimes AS (
                    SELECT
                        l.gsdlvsl_gsdlv_gest_ID AS delivery_id,
                        DATEDIFF(
                            second,
                            l.gsdlvsl_Date,
                            LEAD(l.gsdlvsl_Date) OVER (
                                PARTITION BY l.gsdlvsl_gsdlv_gest_ID
                                ORDER BY l.gsdlvsl_Date
                            )
                        ) / 60.0 AS road_minutes,
                        l.gsdlvsl_dlvrst_ID AS state_id
                    FROM dbo.tp_GuestDeliveryStateLog AS l
                )
                SELECT
                    COALESCE(NULLIF(LTRIM(RTRIM(u.usr_Name)), N''), N'Не назначен')
                        AS courier_name,
                    COUNT(*) AS orders_count,
                    AVG(
                        CASE
                            WHEN gd.gsdlv_DateDelivered IS NOT NULL
                            THEN DATEDIFF(second, gd.gsdlv_Date, gd.gsdlv_DateDelivered) / 60.0
                        END
                    ) AS avg_total_minutes,
                    AVG(CASE WHEN rt.state_id = 7 THEN rt.road_minutes END)
                        AS avg_road_minutes,
                    SUM(
                        CASE
                            WHEN gd.gsdlv_DateDelivered IS NOT NULL
                             AND DATEDIFF(
                                    second,
                                    gd.gsdlv_Date,
                                    gd.gsdlv_DateDelivered
                                 ) <= (
                                    COALESCE(gd.gsdlv_CookingTime, 0)
                                    + COALESCE(gd.gsdlv_DeliveryTime, 0)
                                 )
                            THEN 1 ELSE 0
                        END
                    ) AS on_time_orders
                FROM dbo.tp_GuestDeliveries AS gd
                LEFT JOIN dbo.tp_Users AS u
                    ON u.usr_ID = gd.gsdlv_usr_ID_Courier
                LEFT JOIN RoadTimes AS rt
                    ON rt.delivery_id = gd.gsdlv_gest_ID
                   AND rt.state_id = 7
                WHERE gd.gsdlv_Date >= ?
                  AND gd.gsdlv_Date < DATEADD(day, 1, ?)
                  AND gd.gsdlv_dlvrmt_ID = 1
                GROUP BY COALESCE(NULLIF(LTRIM(RTRIM(u.usr_Name)), N''), N'Не назначен')
                ORDER BY orders_count DESC
                """,
                date_from,
                date_to,
            )
            couriers = self._rows(cursor)

            cursor.execute(
                """
                WITH LatestState AS (
                    SELECT
                        l.gsdlvsl_gsdlv_gest_ID AS delivery_id,
                        l.gsdlvsl_dlvrst_ID AS state_id,
                        l.gsdlvsl_Date AS state_date,
                        ROW_NUMBER() OVER (
                            PARTITION BY l.gsdlvsl_gsdlv_gest_ID
                            ORDER BY l.gsdlvsl_Date DESC
                        ) AS row_number
                    FROM dbo.tp_GuestDeliveryStateLog AS l
                )
                SELECT TOP (30)
                    gd.gsdlv_gest_ID AS delivery_id,
                    gd.gsdlv_Date AS started_at,
                    DATEDIFF(minute, gd.gsdlv_Date, GETDATE()) AS age_minutes,
                    gd.gsdlv_dlvrmt_ID AS method_id,
                    dm.dlvrmt_Name AS method_name,
                    ls.state_id,
                    ds.dlvrst_Name AS state_name,
                    COALESCE(NULLIF(LTRIM(RTRIM(u.usr_Name)), N''), N'Не назначен')
                        AS courier_name
                FROM dbo.tp_GuestDeliveries AS gd
                LEFT JOIN LatestState AS ls
                    ON ls.delivery_id = gd.gsdlv_gest_ID
                   AND ls.row_number = 1
                LEFT JOIN dbo.tp_DeliveryStates AS ds
                    ON ds.dlvrst_ID = COALESCE(ls.state_id, gd.gsdlv_dlvrst_ID)
                LEFT JOIN dbo.tp_DeliveryMethods AS dm
                    ON dm.dlvrmt_ID = gd.gsdlv_dlvrmt_ID
                LEFT JOIN dbo.tp_Users AS u
                    ON u.usr_ID = gd.gsdlv_usr_ID_Courier
                WHERE gd.gsdlv_DateDelivered IS NULL
                  AND COALESCE(ls.state_id, gd.gsdlv_dlvrst_ID) NOT IN (1, 4, 8)
                ORDER BY gd.gsdlv_Date
                """
            )
            active = self._rows(cursor)

            cursor.execute(
                """
                SELECT TOP (1)
                    gd.gsdlv_gest_ID AS delivery_id,
                    gd.gsdlv_Date AS started_at,
                    gd.gsdlv_DateDelivered AS completed_at,
                    DATEDIFF(
                        minute,
                        gd.gsdlv_Date,
                        gd.gsdlv_DateDelivered
                    ) AS total_minutes,
                    gd.gsdlv_dlvrmt_ID AS method_id,
                    dm.dlvrmt_Name AS method_name,
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(u.usr_Name)), N''),
                        N'Не назначен'
                    ) AS courier_name
                FROM dbo.tp_GuestDeliveries AS gd
                LEFT JOIN dbo.tp_DeliveryMethods AS dm
                    ON dm.dlvrmt_ID = gd.gsdlv_dlvrmt_ID
                LEFT JOIN dbo.tp_Users AS u
                    ON u.usr_ID = gd.gsdlv_usr_ID_Courier
                WHERE gd.gsdlv_DateDelivered IS NOT NULL
                ORDER BY gd.gsdlv_DateDelivered DESC
                """
            )
            latest_completed_rows = self._rows(cursor)
            latest_completed = (
                latest_completed_rows[0]
                if latest_completed_rows
                else None
            )

            cursor.execute(
                """
                SELECT
                    ds.dlvrst_ID AS state_id,
                    ds.dlvrst_Name AS state_name,
                    COUNT(*) AS orders_count
                FROM dbo.tp_GuestDeliveries AS gd
                INNER JOIN dbo.tp_DeliveryStates AS ds
                    ON ds.dlvrst_ID = gd.gsdlv_dlvrst_ID
                WHERE gd.gsdlv_Date >= ?
                  AND gd.gsdlv_Date < DATEADD(day, 1, ?)
                GROUP BY ds.dlvrst_ID, ds.dlvrst_Name
                ORDER BY orders_count DESC
                """,
                date_from,
                date_to,
            )
            states = self._rows(cursor)

        return {
            "summary": summary,
            "stages": stages,
            "daily": daily,
            "couriers": couriers,
            "active": active,
            "latest_completed": latest_completed,
            "states": states,
        }

    def load_summary(
        self,
        date_from: date,
        date_to: date,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total_orders,
                    SUM(CASE WHEN gd.gsdlv_dlvrmt_ID = 1 THEN 1 ELSE 0 END)
                        AS courier_orders,
                    SUM(CASE WHEN gd.gsdlv_dlvrmt_ID = 2 THEN 1 ELSE 0 END)
                        AS pickup_orders,
                    SUM(CASE WHEN gd.gsdlv_dlvrst_ID = 1 THEN 1 ELSE 0 END)
                        AS completed_orders,
                    SUM(CASE WHEN gd.gsdlv_dlvrst_ID IN (4, 8) THEN 1 ELSE 0 END)
                        AS cancelled_orders,
                    AVG(
                        CASE
                            WHEN gd.gsdlv_DateDelivered IS NOT NULL
                            THEN DATEDIFF(
                                second,
                                gd.gsdlv_Date,
                                gd.gsdlv_DateDelivered
                            ) / 60.0
                        END
                    ) AS avg_total_minutes,
                    MAX(
                        CASE
                            WHEN gd.gsdlv_DateDelivered IS NOT NULL
                            THEN DATEDIFF(
                                second,
                                gd.gsdlv_Date,
                                gd.gsdlv_DateDelivered
                            ) / 60.0
                        END
                    ) AS max_total_minutes,
                    SUM(
                        CASE
                            WHEN gd.gsdlv_DateDelivered IS NOT NULL
                             AND DATEDIFF(
                                    second,
                                    gd.gsdlv_Date,
                                    gd.gsdlv_DateDelivered
                                 ) <= (
                                    COALESCE(gd.gsdlv_CookingTime, 0)
                                    + COALESCE(gd.gsdlv_DeliveryTime, 0)
                                 )
                            THEN 1 ELSE 0
                        END
                    ) AS on_time_orders,
                    SUM(
                        CASE
                            WHEN gd.gsdlv_DateDelivered IS NOT NULL
                            THEN 1 ELSE 0
                        END
                    ) AS measured_orders
                FROM dbo.tp_GuestDeliveries AS gd
                WHERE gd.gsdlv_Date >= ?
                  AND gd.gsdlv_Date < DATEADD(day, 1, ?)
                """,
                date_from,
                date_to,
            )
            return self._rows(cursor)[0]

