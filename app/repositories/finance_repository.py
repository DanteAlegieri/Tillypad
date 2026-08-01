import re


PAYTYPE_MAP = {
    "Банковские карты": "💳 Банковская карта",
    "Наличные": "💵 Наличные",
    "QR код": "📱 QR / СБП",
    "Перевод на карту": "📲 Перевод на карту",
    "Питание Персонала": "👨‍🍳 Питание персонала",
    "Собственники": "👑 Собственники",
}

def normalize_paytype(name: str) -> str:
    if not name:
        return "Без названия"
    name = "".join(ch for ch in str(name) if ord(ch) >= 32)
    name = re.sub(r"[■□]+", "", name)
    parts = re.split(r"(Bank cards|Bankkarten|Cash|Bargeld|Готівка)", name, maxsplit=1)
    clean = parts[0].strip()
    clean = re.sub(r"\s{2,}", " ", clean)
    return PAYTYPE_MAP.get(clean, clean)

from datetime import date, timedelta
from typing import Any

from app.db.sql_server import SqlServer


class FinanceRepository:
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
                    COALESCE(SUM(cp.chpy_Sum), 0) AS total_amount,
                    COALESCE(
                        SUM(
                            CASE
                                WHEN pt.pytp_IsCash = 1
                                THEN cp.chpy_Sum
                                ELSE 0
                            END
                        ),
                        0
                    ) AS cash_amount,
                    COALESCE(
                        SUM(
                            CASE
                                WHEN pt.pytp_IsCash = 0
                                THEN cp.chpy_Sum
                                ELSE 0
                            END
                        ),
                        0
                    ) AS cashless_amount,
                    COUNT(DISTINCT c.chck_ID) AS checks_count,
                    COUNT(*) AS payment_rows,
                    COALESCE(
                        SUM(
                            CASE
                                WHEN cp.chpy_Sum < 0
                                THEN ABS(cp.chpy_Sum)
                                ELSE 0
                            END
                        ),
                        0
                    ) AS negative_amount,
                    SUM(
                        CASE
                            WHEN cp.chpy_Sum < 0 THEN 1 ELSE 0
                        END
                    ) AS negative_count
                FROM dbo.tp_CheckPayments AS cp
                INNER JOIN dbo.tp_Checks AS c
                    ON c.chck_ID = cp.chpy_chck_ID
                INNER JOIN dbo.tp_PayTypes AS pt
                    ON pt.pytp_ID = cp.chpy_pytp_ID
                WHERE c.chck_Date >= ?
                  AND c.chck_Date < ?
                """,
                start,
                end_exclusive,
            )
            row = cursor.fetchone()

        total = float(row.total_amount or 0)
        checks_count = int(row.checks_count or 0)

        return {
            "date_from": start,
            "date_to": end,
            "total_amount": total,
            "cash_amount": float(row.cash_amount or 0),
            "cashless_amount": float(row.cashless_amount or 0),
            "checks_count": checks_count,
            "payment_rows": int(row.payment_rows or 0),
            "avg_check": total / checks_count if checks_count else 0,
            "negative_amount": float(row.negative_amount or 0),
            "negative_count": int(row.negative_count or 0),
        }

    def by_pay_type(
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
                    pt.pytp_ID AS pay_type_id,
                    pt.pytp_Name AS pay_type_name,
                    pt.pytp_IsCash AS is_cash,
                    COUNT(DISTINCT c.chck_ID) AS checks_count,
                    COUNT(*) AS payment_rows,
                    COALESCE(SUM(cp.chpy_Sum), 0) AS amount,
                    COALESCE(AVG(NULLIF(cp.chpy_Sum, 0)), 0) AS avg_payment
                FROM dbo.tp_CheckPayments AS cp
                INNER JOIN dbo.tp_Checks AS c
                    ON c.chck_ID = cp.chpy_chck_ID
                INNER JOIN dbo.tp_PayTypes AS pt
                    ON pt.pytp_ID = cp.chpy_pytp_ID
                WHERE c.chck_Date >= ?
                  AND c.chck_Date < ?
                GROUP BY
                    pt.pytp_ID,
                    pt.pytp_Name,
                    pt.pytp_IsCash
                ORDER BY amount DESC
                """,
                start,
                end_exclusive,
            )
            columns = [item[0] for item in cursor.description]
            rows = [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]

        total = sum(float(row["amount"] or 0) for row in rows)

        for row in rows:
            amount = float(row["amount"] or 0)
            row["amount"] = amount
            row["checks_count"] = int(row["checks_count"] or 0)
            row["payment_rows"] = int(row["payment_rows"] or 0)
            row["avg_payment"] = float(row["avg_payment"] or 0)
            row["is_cash"] = bool(row["is_cash"])
            row["pay_type_name"] = normalize_paytype(row["pay_type_name"])
            row["share"] = round((amount / total) * 100, 1) if total else 0

        return rows

    def daily(
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
                    CONVERT(date, c.chck_Date) AS payment_date,
                    COALESCE(SUM(cp.chpy_Sum), 0) AS amount,
                    COALESCE(
                        SUM(
                            CASE WHEN pt.pytp_IsCash = 1
                            THEN cp.chpy_Sum ELSE 0 END
                        ),
                        0
                    ) AS cash_amount,
                    COALESCE(
                        SUM(
                            CASE WHEN pt.pytp_IsCash = 0
                            THEN cp.chpy_Sum ELSE 0 END
                        ),
                        0
                    ) AS cashless_amount,
                    COUNT(DISTINCT c.chck_ID) AS checks_count
                FROM dbo.tp_CheckPayments AS cp
                INNER JOIN dbo.tp_Checks AS c
                    ON c.chck_ID = cp.chpy_chck_ID
                INNER JOIN dbo.tp_PayTypes AS pt
                    ON pt.pytp_ID = cp.chpy_pytp_ID
                WHERE c.chck_Date >= ?
                  AND c.chck_Date < ?
                GROUP BY CONVERT(date, c.chck_Date)
                ORDER BY payment_date
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
            row["payment_date"] = str(row["payment_date"])
            row["amount"] = float(row["amount"] or 0)
            row["cash_amount"] = float(row["cash_amount"] or 0)
            row["cashless_amount"] = float(row["cashless_amount"] or 0)
            row["checks_count"] = int(row["checks_count"] or 0)

        return rows

    def hourly(
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
                    DATEPART(hour, c.chck_Date) AS payment_hour,
                    COALESCE(SUM(cp.chpy_Sum), 0) AS amount,
                    COUNT(DISTINCT c.chck_ID) AS checks_count
                FROM dbo.tp_CheckPayments AS cp
                INNER JOIN dbo.tp_Checks AS c
                    ON c.chck_ID = cp.chpy_chck_ID
                WHERE c.chck_Date >= ?
                  AND c.chck_Date < ?
                GROUP BY DATEPART(hour, c.chck_Date)
                ORDER BY payment_hour
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
            row["amount"] = float(row["amount"] or 0)
            row["checks_count"] = int(row["checks_count"] or 0)

        return rows

    def recent_payments(
        self,
        date_from: date | None,
        date_to: date | None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        start, end = self.normalize_period(date_from, date_to)
        end_exclusive = end + timedelta(days=1)
        limit = max(1, min(limit, 200))

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT TOP ({limit})
                    c.chck_Date AS check_date,
                    c.chck_Name AS check_name,
                    pt.pytp_Name AS pay_type_name,
                    pt.pytp_IsCash AS is_cash,
                    cp.chpy_Sum AS amount,
                    cp.chpy_chpc_ID AS operation_code
                FROM dbo.tp_CheckPayments AS cp
                INNER JOIN dbo.tp_Checks AS c
                    ON c.chck_ID = cp.chpy_chck_ID
                INNER JOIN dbo.tp_PayTypes AS pt
                    ON pt.pytp_ID = cp.chpy_pytp_ID
                WHERE c.chck_Date >= ?
                  AND c.chck_Date < ?
                ORDER BY c.chck_Date DESC
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
            row["amount"] = float(row["amount"] or 0)
            row["is_cash"] = bool(row["is_cash"])
            row["operation_code"] = int(row["operation_code"])
            row["pay_type_name"] = normalize_paytype(row["pay_type_name"])

        return rows
