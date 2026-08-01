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
                SELECT
                    (DATEPART(weekday, gd.gsdlv_Date) + @@DATEFIRST - 2) % 7
                        AS weekday_number,
                    DATEPART(hour, gd.gsdlv_Date) AS hour_number,
                    COUNT(*) AS orders_count,
                    AVG(
                        CASE
                            WHEN gd.gsdlv_DateDelivered IS NOT NULL
                            THEN DATEDIFF(
                                second,
                                gd.gsdlv_Date,
                                gd.gsdlv_DateDelivered
                            ) / 60.0
                        END
                    ) AS avg_minutes,
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
                GROUP BY
                    (DATEPART(weekday, gd.gsdlv_Date) + @@DATEFIRST - 2) % 7,
                    DATEPART(hour, gd.gsdlv_Date)
                ORDER BY weekday_number, hour_number
                """,
                date_from,
                date_to,
            )
            heatmap = self._rows(cursor)

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
                    MIN(
                        CASE
                            WHEN gd.gsdlv_DateDelivered IS NOT NULL
                            THEN DATEDIFF(second, gd.gsdlv_Date, gd.gsdlv_DateDelivered) / 60.0
                        END
                    ) AS best_total_minutes,
                    MAX(
                        CASE
                            WHEN gd.gsdlv_DateDelivered IS NOT NULL
                            THEN DATEDIFF(second, gd.gsdlv_Date, gd.gsdlv_DateDelivered) / 60.0
                        END
                    ) AS worst_total_minutes,
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
                WITH StageRows AS (
                    SELECT
                        l.gsdlvsl_gsdlv_gest_ID AS delivery_id,
                        l.gsdlvsl_dlvrst_ID AS state_id,
                        DATEDIFF(
                            second,
                            l.gsdlvsl_Date,
                            LEAD(l.gsdlvsl_Date) OVER (
                                PARTITION BY l.gsdlvsl_gsdlv_gest_ID
                                ORDER BY l.gsdlvsl_Date
                            )
                        ) / 60.0 AS stage_minutes
                    FROM dbo.tp_GuestDeliveryStateLog AS l
                ),
                StageTotals AS (
                    SELECT
                        delivery_id,
                        SUM(
                            CASE WHEN state_id = 3
                            THEN stage_minutes ELSE 0 END
                        ) AS wait_kitchen_minutes,
                        SUM(
                            CASE WHEN state_id = 5
                            THEN stage_minutes ELSE 0 END
                        ) AS cooking_minutes,
                        SUM(
                            CASE WHEN state_id = 6
                            THEN stage_minutes ELSE 0 END
                        ) AS wait_courier_minutes,
                        SUM(
                            CASE WHEN state_id = 7
                            THEN stage_minutes ELSE 0 END
                        ) AS road_minutes
                    FROM StageRows
                    GROUP BY delivery_id
                )
                SELECT TOP (10)
                    gd.gsdlv_gest_ID AS delivery_id,
                    gd.gsdlv_Date AS started_at,
                    gd.gsdlv_DateDelivered AS completed_at,
                    DATEDIFF(
                        minute,
                        gd.gsdlv_Date,
                        gd.gsdlv_DateDelivered
                    ) AS total_minutes,
                    dm.dlvrmt_Name AS method_name,
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(u.usr_Name)), N''),
                        N'Не назначен'
                    ) AS courier_name,
                    COALESCE(st.wait_kitchen_minutes, 0)
                        AS wait_kitchen_minutes,
                    COALESCE(st.cooking_minutes, 0)
                        AS cooking_minutes,
                    COALESCE(st.wait_courier_minutes, 0)
                        AS wait_courier_minutes,
                    COALESCE(st.road_minutes, 0)
                        AS road_minutes
                FROM dbo.tp_GuestDeliveries AS gd
                LEFT JOIN StageTotals AS st
                    ON st.delivery_id = gd.gsdlv_gest_ID
                LEFT JOIN dbo.tp_DeliveryMethods AS dm
                    ON dm.dlvrmt_ID = gd.gsdlv_dlvrmt_ID
                LEFT JOIN dbo.tp_Users AS u
                    ON u.usr_ID = gd.gsdlv_usr_ID_Courier
                WHERE gd.gsdlv_Date >= ?
                  AND gd.gsdlv_Date < DATEADD(day, 1, ?)
                  AND gd.gsdlv_DateDelivered IS NOT NULL
                ORDER BY DATEDIFF(
                    second,
                    gd.gsdlv_Date,
                    gd.gsdlv_DateDelivered
                ) DESC
                """,
                date_from,
                date_to,
            )
            longest_orders = self._rows(cursor)

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
            "heatmap": heatmap,
            "couriers": couriers,
            "longest_orders": longest_orders,
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

    def load_orders(
        self,
        date_from: date,
        date_to: date,
        courier_name: str = "",
        stage: str = "",
        weekday_number: int | None = None,
        hour_number: int | None = None,
        only_overdue: bool = False,
        limit: int = 300,
    ) -> list[dict[str, Any]]:
        stage_state_map = {
            "wait_kitchen": 3,
            "cooking": 5,
            "wait_courier": 6,
            "road": 7,
        }
        stage_state = stage_state_map.get(stage)

        filters = [
            "gd.gsdlv_Date >= ?",
            "gd.gsdlv_Date < DATEADD(day, 1, ?)",
        ]
        parameters: list[Any] = [date_from, date_to]

        if courier_name:
            filters.append(
                "COALESCE(NULLIF(LTRIM(RTRIM(u.usr_Name)), N''), "
                "N'Не назначен') = ?"
            )
            parameters.append(courier_name)

        if weekday_number is not None:
            filters.append(
                "(DATEPART(weekday, gd.gsdlv_Date) + @@DATEFIRST - 2) % 7 = ?"
            )
            parameters.append(weekday_number)

        if hour_number is not None:
            filters.append("DATEPART(hour, gd.gsdlv_Date) = ?")
            parameters.append(hour_number)

        if only_overdue:
            filters.append(
                """
                gd.gsdlv_DateDelivered IS NOT NULL
                AND DATEDIFF(
                    second,
                    gd.gsdlv_Date,
                    gd.gsdlv_DateDelivered
                ) > (
                    COALESCE(gd.gsdlv_CookingTime, 0)
                    + COALESCE(gd.gsdlv_DeliveryTime, 0)
                )
                """
            )

        if stage_state is not None:
            filters.append(
                """
                EXISTS (
                    SELECT 1
                    FROM dbo.tp_GuestDeliveryStateLog AS stage_filter
                    WHERE stage_filter.gsdlvsl_gsdlv_gest_ID =
                        gd.gsdlv_gest_ID
                      AND stage_filter.gsdlvsl_dlvrst_ID = ?
                )
                """
            )
            parameters.append(stage_state)

        safe_limit = max(1, min(int(limit), 1000))
        where_sql = "\n                  AND ".join(filters)

        query = f"""
            WITH StageRows AS (
                SELECT
                    l.gsdlvsl_gsdlv_gest_ID AS delivery_id,
                    l.gsdlvsl_dlvrst_ID AS state_id,
                    DATEDIFF(
                        second,
                        l.gsdlvsl_Date,
                        LEAD(l.gsdlvsl_Date) OVER (
                            PARTITION BY l.gsdlvsl_gsdlv_gest_ID
                            ORDER BY l.gsdlvsl_Date
                        )
                    ) / 60.0 AS stage_minutes
                FROM dbo.tp_GuestDeliveryStateLog AS l
            ),
            StageTotals AS (
                SELECT
                    delivery_id,
                    SUM(CASE WHEN state_id = 3
                        THEN stage_minutes ELSE 0 END)
                        AS wait_kitchen_minutes,
                    SUM(CASE WHEN state_id = 5
                        THEN stage_minutes ELSE 0 END)
                        AS cooking_minutes,
                    SUM(CASE WHEN state_id = 6
                        THEN stage_minutes ELSE 0 END)
                        AS wait_courier_minutes,
                    SUM(CASE WHEN state_id = 7
                        THEN stage_minutes ELSE 0 END)
                        AS road_minutes
                FROM StageRows
                GROUP BY delivery_id
            )
            SELECT TOP ({safe_limit})
                gd.gsdlv_gest_ID AS delivery_id,
                g.gest_Name AS order_name,
                gd.gsdlv_Date AS started_at,
                gd.gsdlv_DateDelivered AS completed_at,
                DATEDIFF(
                    minute,
                    gd.gsdlv_Date,
                    COALESCE(gd.gsdlv_DateDelivered, GETDATE())
                ) AS total_minutes,
                gd.gsdlv_dlvrst_ID AS state_id,
                ds.dlvrst_Name AS state_name,
                dm.dlvrmt_Name AS method_name,
                COALESCE(
                    NULLIF(LTRIM(RTRIM(u.usr_Name)), N''),
                    N'Не назначен'
                ) AS courier_name,
                COALESCE(st.wait_kitchen_minutes, 0)
                    AS wait_kitchen_minutes,
                COALESCE(st.cooking_minutes, 0)
                    AS cooking_minutes,
                COALESCE(st.wait_courier_minutes, 0)
                    AS wait_courier_minutes,
                COALESCE(st.road_minutes, 0)
                    AS road_minutes,
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
                END AS is_overdue
            FROM dbo.tp_GuestDeliveries AS gd
            INNER JOIN dbo.tp_Guests AS g
                ON g.gest_ID = gd.gsdlv_gest_ID
            LEFT JOIN StageTotals AS st
                ON st.delivery_id = gd.gsdlv_gest_ID
            LEFT JOIN dbo.tp_DeliveryStates AS ds
                ON ds.dlvrst_ID = gd.gsdlv_dlvrst_ID
            LEFT JOIN dbo.tp_DeliveryMethods AS dm
                ON dm.dlvrmt_ID = gd.gsdlv_dlvrmt_ID
            LEFT JOIN dbo.tp_Users AS u
                ON u.usr_ID = gd.gsdlv_usr_ID_Courier
            WHERE {where_sql}
            ORDER BY gd.gsdlv_Date DESC
        """

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(query, *parameters)
            return self._rows(cursor)

    def load_order_detail(
        self,
        delivery_id: str,
    ) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT TOP (1)
                    gd.gsdlv_gest_ID AS delivery_id,
                    g.gest_Name AS order_name,
                    g.gest_ClientName AS client_name,
                    g.gest_ClientPhone AS client_phone,
                    g.gest_ClientAddress AS client_address,
                    gd.gsdlv_Date AS started_at,
                    gd.gsdlv_DateDelivered AS completed_at,
                    DATEDIFF(
                        minute,
                        gd.gsdlv_Date,
                        COALESCE(gd.gsdlv_DateDelivered, GETDATE())
                    ) AS total_minutes,
                    gd.gsdlv_dlvrst_ID AS state_id,
                    ds.dlvrst_Name AS state_name,
                    dm.dlvrmt_Name AS method_name,
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(u.usr_Name)), N''),
                        N'Не назначен'
                    ) AS courier_name,
                    gd.gsdlv_CookingTime / 60.0 AS cooking_norm_minutes,
                    gd.gsdlv_DeliveryTime / 60.0 AS delivery_norm_minutes,
                    gd.gsdlv_CourierComment AS courier_comment,
                    gd.gsdlv_ExtraInfo AS extra_info
                FROM dbo.tp_GuestDeliveries AS gd
                INNER JOIN dbo.tp_Guests AS g
                    ON g.gest_ID = gd.gsdlv_gest_ID
                LEFT JOIN dbo.tp_DeliveryStates AS ds
                    ON ds.dlvrst_ID = gd.gsdlv_dlvrst_ID
                LEFT JOIN dbo.tp_DeliveryMethods AS dm
                    ON dm.dlvrmt_ID = gd.gsdlv_dlvrmt_ID
                LEFT JOIN dbo.tp_Users AS u
                    ON u.usr_ID = gd.gsdlv_usr_ID_Courier
                WHERE gd.gsdlv_gest_ID = ?
                """,
                delivery_id,
            )
            rows = self._rows(cursor)
            if not rows:
                return None
            order = rows[0]

            cursor.execute(
                """
                SELECT
                    l.gsdlvsl_ID AS log_id,
                    l.gsdlvsl_dlvrst_ID AS state_id,
                    ds.dlvrst_Name AS state_name,
                    l.gsdlvsl_Date AS state_date,
                    LEAD(l.gsdlvsl_Date) OVER (
                        ORDER BY l.gsdlvsl_Date
                    ) AS next_date,
                    DATEDIFF(
                        second,
                        l.gsdlvsl_Date,
                        LEAD(l.gsdlvsl_Date) OVER (
                            ORDER BY l.gsdlvsl_Date
                        )
                    ) / 60.0 AS stage_minutes,
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(u.usr_Name)), N''),
                        N'Система'
                    ) AS changed_by
                FROM dbo.tp_GuestDeliveryStateLog AS l
                LEFT JOIN dbo.tp_DeliveryStates AS ds
                    ON ds.dlvrst_ID = l.gsdlvsl_dlvrst_ID
                LEFT JOIN dbo.tp_Users AS u
                    ON u.usr_ID = l.gsdlvsl_usr_ID
                WHERE l.gsdlvsl_gsdlv_gest_ID = ?
                ORDER BY l.gsdlvsl_Date
                """,
                delivery_id,
            )
            timeline = self._rows(cursor)

            cursor.execute(
                """
                SELECT
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(mi.mitm_Name)), N''),
                        NULLIF(LTRIM(RTRIM(oi.orit_Comment)), N''),
                        N'Позиция без названия'
                    ) AS item_name,
                    SUM(oi.orit_Count) AS item_count,
                    SUM(
                        (
                            oi.orit_Price
                            - oi.orit_PriceDiscount
                            + oi.orit_PriceMargin
                        ) * oi.orit_Count
                    ) AS item_sum
                FROM dbo.tp_Orders AS o
                INNER JOIN dbo.tp_OrderItems AS oi
                    ON oi.orit_ordr_ID = o.ordr_ID
                LEFT JOIN dbo.tp_MenuItems AS mi
                    ON mi.mitm_ID = oi.orit_mitm_ID
                WHERE o.ordr_gest_ID = ?
                  AND oi.orit_master_ID IS NULL
                GROUP BY
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(mi.mitm_Name)), N''),
                        NULLIF(LTRIM(RTRIM(oi.orit_Comment)), N''),
                        N'Позиция без названия'
                    )
                ORDER BY item_sum DESC
                """,
                delivery_id,
            )
            items = self._rows(cursor)

            order["timeline"] = timeline
            order["items"] = items
            return order

