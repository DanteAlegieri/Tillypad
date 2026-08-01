from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from app.core.config import get_settings
from app.db.sql_server import SqlServer
from app.repositories.bi_repository import BIRepository


class DecisionRepository:
    def __init__(self, database: SqlServer | None = None) -> None:
        self.database = database or SqlServer()
        self.settings = get_settings()
        self.bi = BIRepository(self.database)

    @staticmethod
    def _change(current: float, previous: float) -> float | None:
        if previous == 0:
            return None
        return round(((current - previous) / previous) * 100, 1)

    def _day_payments(self, day: date) -> dict[str, Any]:
        next_day = day + timedelta(days=1)

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    COALESCE(SUM(cp.chpy_Sum), 0) AS revenue,
                    COUNT(DISTINCT c.chck_ID) AS checks_count
                FROM dbo.tp_CheckPayments AS cp
                INNER JOIN dbo.tp_Checks AS c
                    ON c.chck_ID = cp.chpy_chck_ID
                WHERE c.chck_Date >= ?
                  AND c.chck_Date < ?
                """,
                day,
                next_day,
            )
            row = cursor.fetchone()

        revenue = float(row.revenue or 0)
        checks_count = int(row.checks_count or 0)

        return {
            "revenue": revenue,
            "checks_count": checks_count,
            "avg_check": revenue / checks_count if checks_count else 0,
        }

    def _historical_same_weekday(
        self,
        day: date,
        weeks: int = 8,
    ) -> list[dict[str, Any]]:
        start = day - timedelta(days=weeks * 7)
        result: list[dict[str, Any]] = []

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    CONVERT(date, c.chck_Date) AS sale_date,
                    DATEPART(hour, c.chck_Date) AS sale_hour,
                    COALESCE(SUM(cp.chpy_Sum), 0) AS revenue,
                    COUNT(DISTINCT c.chck_ID) AS checks_count
                FROM dbo.tp_CheckPayments AS cp
                INNER JOIN dbo.tp_Checks AS c
                    ON c.chck_ID = cp.chpy_chck_ID
                WHERE c.chck_Date >= ?
                  AND c.chck_Date < ?
                  AND DATEPART(weekday, c.chck_Date) = DATEPART(weekday, ?)
                GROUP BY
                    CONVERT(date, c.chck_Date),
                    DATEPART(hour, c.chck_Date)
                ORDER BY sale_date, sale_hour
                """,
                start,
                day,
                day,
            )
            columns = [item[0] for item in cursor.description]
            rows = [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]

        for row in rows:
            result.append(
                {
                    "sale_date": str(row["sale_date"]),
                    "sale_hour": int(row["sale_hour"]),
                    "revenue": float(row["revenue"] or 0),
                    "checks_count": int(row["checks_count"] or 0),
                }
            )

        return result

    def _today_hourly(self, day: date) -> list[dict[str, Any]]:
        next_day = day + timedelta(days=1)

        with self.database.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT
                    DATEPART(hour, c.chck_Date) AS sale_hour,
                    COALESCE(SUM(cp.chpy_Sum), 0) AS revenue,
                    COUNT(DISTINCT c.chck_ID) AS checks_count
                FROM dbo.tp_CheckPayments AS cp
                INNER JOIN dbo.tp_Checks AS c
                    ON c.chck_ID = cp.chpy_chck_ID
                WHERE c.chck_Date >= ?
                  AND c.chck_Date < ?
                GROUP BY DATEPART(hour, c.chck_Date)
                ORDER BY sale_hour
                """,
                day,
                next_day,
            )
            columns = [item[0] for item in cursor.description]
            rows = [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]

        return [
            {
                "sale_hour": int(row["sale_hour"]),
                "revenue": float(row["revenue"] or 0),
                "checks_count": int(row["checks_count"] or 0),
            }
            for row in rows
        ]

    def forecast_today(self) -> dict[str, Any]:
        today = date.today()
        now_hour = datetime.now().hour
        today_data = self._day_payments(today)
        today_hourly = self._today_hourly(today)
        history = self._historical_same_weekday(today)

        by_day: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "total": 0.0,
                "to_current_hour": 0.0,
                "hours": defaultdict(float),
            }
        )

        for row in history:
            day_data = by_day[row["sale_date"]]
            day_data["total"] += row["revenue"]
            day_data["hours"][row["sale_hour"]] += row["revenue"]

            if row["sale_hour"] <= now_hour:
                day_data["to_current_hour"] += row["revenue"]

        valid_days = [
            values
            for values in by_day.values()
            if values["total"] > 0
        ]

        average_total = (
            sum(values["total"] for values in valid_days)
            / len(valid_days)
            if valid_days
            else 0
        )
        average_to_now = (
            sum(values["to_current_hour"] for values in valid_days)
            / len(valid_days)
            if valid_days
            else 0
        )

        historical_share = (
            average_to_now / average_total
            if average_total
            else 0
        )

        current_revenue = float(today_data["revenue"])

        if historical_share >= 0.15:
            forecast_revenue = current_revenue / historical_share
            method = "по темпу аналогичных дней"
        elif average_total:
            forecast_revenue = average_total
            method = "по среднему аналогичных дней"
        else:
            forecast_revenue = current_revenue
            method = "по фактической выручке"

        target = float(self.settings.daily_revenue_target or 0)
        probability = 0

        if target:
            ratio = forecast_revenue / target
            if ratio >= 1.2:
                probability = 95
            elif ratio >= 1.05:
                probability = 85
            elif ratio >= 0.95:
                probability = 65
            elif ratio >= 0.8:
                probability = 35
            else:
                probability = 15

        historical_hours: dict[int, float] = defaultdict(float)
        for values in valid_days:
            for hour, revenue in values["hours"].items():
                if hour > now_hour:
                    historical_hours[hour] += revenue

        next_peak_hour = None
        next_peak_revenue = 0.0

        if historical_hours:
            next_peak_hour, peak_total = max(
                historical_hours.items(),
                key=lambda item: item[1],
            )
            next_peak_revenue = (
                peak_total / len(valid_days)
                if valid_days
                else 0
            )

        current_checks = int(today_data["checks_count"])
        expected_checks = (
            round(
                current_checks
                * (forecast_revenue / current_revenue)
            )
            if current_revenue
            else 0
        )

        return {
            "current_revenue": current_revenue,
            "forecast_revenue": round(forecast_revenue),
            "forecast_checks": expected_checks,
            "target": target,
            "probability": probability,
            "method": method,
            "historical_days": len(valid_days),
            "historical_average": round(average_total),
            "historical_share_to_now": round(
                historical_share * 100,
                1,
            ),
            "next_peak_hour": next_peak_hour,
            "next_peak_revenue": round(next_peak_revenue),
            "hourly": today_hourly,
        }

    def menu_health(self) -> dict[str, Any]:
        today = date.today()
        start = today - timedelta(days=29)
        analysis = self.bi.abc_xyz(
            start,
            today,
            xyz_mode="adaptive",
        )
        items = analysis["items"]

        total_items = len(items)
        ax_count = sum(
            1
            for item in items
            if item["matrix"] == "AX"
        )
        az_count = sum(
            1
            for item in items
            if item["matrix"] == "AZ"
        )
        weak_items = [
            item
            for item in items
            if item["abc"] == "C"
            and item["quantity"] <= 2
        ]

        leader_share = (
            float(items[0]["share"])
            if items
            else 0
        )

        concentration_score = max(
            0,
            100 - max(0, leader_share - 25) * 2,
        )
        stability_score = (
            (analysis["x_count"] / total_items) * 100
            if total_items
            else 0
        )
        portfolio_score = (
            ((total_items - len(weak_items)) / total_items) * 100
            if total_items
            else 0
        )
        core_score = min(
            100,
            (ax_count / max(total_items, 1)) * 300,
        )

        score = round(
            concentration_score * 0.25
            + stability_score * 0.25
            + portfolio_score * 0.25
            + core_score * 0.25
        )

        if score >= 80:
            label = "Меню в хорошем состоянии"
            status = "good"
        elif score >= 60:
            label = "Есть точки роста"
            status = "attention"
        else:
            label = "Меню требует пересмотра"
            status = "risk"

        return {
            "score": score,
            "label": label,
            "status": status,
            "total_items": total_items,
            "ax_count": ax_count,
            "az_count": az_count,
            "weak_count": len(weak_items),
            "leader_name": items[0]["item_name"] if items else None,
            "leader_share": leader_share,
            "weak_items": weak_items[:5],
        }

    def executive(self) -> dict[str, Any]:
        today = date.today()
        yesterday = today - timedelta(days=1)

        current = self._day_payments(today)
        previous = self._day_payments(yesterday)
        forecast = self.forecast_today()
        menu = self.menu_health()

        target = float(self.settings.daily_revenue_target or 0)
        target_progress = (
            current["revenue"] / target * 100
            if target
            else 0
        )

        alerts = []

        revenue_change = self._change(
            current["revenue"],
            previous["revenue"],
        )
        avg_check_change = self._change(
            current["avg_check"],
            previous["avg_check"],
        )

        if target and current["revenue"] >= target:
            alerts.append({
                "level": "positive",
                "title": "План выполнен",
                "text": (
                    f'Факт превышает план на '
                    f'{current["revenue"] - target:,.0f} ₽.'
                ).replace(",", " "),
            })
        elif forecast["forecast_revenue"] >= target and target:
            alerts.append({
                "level": "positive",
                "title": "План достижим",
                "text": (
                    f'Прогноз к закрытию — '
                    f'{forecast["forecast_revenue"]:,.0f} ₽.'
                ).replace(",", " "),
            })
        elif target:
            alerts.append({
                "level": "warning",
                "title": "Есть риск не выполнить план",
                "text": (
                    f'По текущему темпу не хватает около '
                    f'{max(target - forecast["forecast_revenue"], 0):,.0f} ₽.'
                ).replace(",", " "),
            })

        if revenue_change is not None:
            level = "positive" if revenue_change >= 0 else "warning"
            alerts.append({
                "level": level,
                "title": "Выручка ко вчера",
                "text": (
                    f'Изменение составляет '
                    f'{"+" if revenue_change >= 0 else ""}'
                    f'{revenue_change}%.'
                ),
            })

        if avg_check_change is not None and avg_check_change <= -5:
            alerts.append({
                "level": "warning",
                "title": "Средний чек снижается",
                "text": (
                    f'Средний чек ниже вчерашнего '
                    f'на {abs(avg_check_change)}%.'
                ),
            })

        if forecast["next_peak_hour"] is not None:
            alerts.append({
                "level": "info",
                "title": "Следующий вероятный пик",
                "text": (
                    f'{forecast["next_peak_hour"]:02d}:00–'
                    f'{forecast["next_peak_hour"] + 1:02d}:00, '
                    f'обычно около '
                    f'{forecast["next_peak_revenue"]:,.0f} ₽.'
                ).replace(",", " "),
            })

        if menu["weak_count"] > 0:
            alerts.append({
                "level": "warning",
                "title": "Слабые позиции меню",
                "text": (
                    f'{menu["weak_count"]} позиций продались '
                    "не более двух раз за 30 дней."
                ),
            })

        restaurant_score = round(
            min(target_progress, 100) * 0.35
            + forecast["probability"] * 0.25
            + menu["score"] * 0.30
            + (
                100
                if revenue_change is not None and revenue_change >= 0
                else 60
            ) * 0.10
        )

        if restaurant_score >= 80:
            status = "good"
            status_label = "Система работает уверенно"
        elif restaurant_score >= 60:
            status = "attention"
            status_label = "Есть задачи для внимания"
        else:
            status = "risk"
            status_label = "Требуются действия"

        return {
            "date": today,
            "current": current,
            "previous": previous,
            "forecast": forecast,
            "menu": menu,
            "target_progress": round(target_progress, 1),
            "revenue_change": revenue_change,
            "avg_check_change": avg_check_change,
            "restaurant_score": restaurant_score,
            "status": status,
            "status_label": status_label,
            "alerts": alerts[:8],
        }
