from datetime import date, datetime, time, timedelta
from typing import Any

from app.db.sql_server import SqlServer
from app.repositories.marketing_repository import MarketingRepository


class LiveAnalystService:
    def __init__(self) -> None:
        self.repository = MarketingRepository(SqlServer())

    @staticmethod
    def _change(current: float, previous: float) -> float | None:
        if previous == 0:
            return None
        return (current - previous) * 100.0 / previous

    @staticmethod
    def _format_change(value: float | None) -> str:
        if value is None:
            return "нет базы для сравнения"
        sign = "+" if value > 0 else ""
        return f"{sign}{value:.1f}%"

    def build(
        self,
        date_from: date,
        date_to: date,
        opportunities: list[dict[str, Any]],
    ) -> dict[str, Any]:
        period_days = (date_to - date_from).days + 1
        previous_to = date_from - timedelta(days=1)
        previous_from = previous_to - timedelta(days=period_days - 1)

        current = self.repository.period_summary(date_from, date_to)
        previous = self.repository.period_summary(previous_from, previous_to)
        hourly = self.repository.hourly_sales(date_from, date_to)
        top_items = self.repository.top_items(date_from, date_to, 5)

        revenue_change = self._change(
            current["revenue"],
            previous["revenue"],
        )
        checks_change = self._change(
            current["checks_count"],
            previous["checks_count"],
        )
        avg_check_change = self._change(
            current["avg_check"],
            previous["avg_check"],
        )

        events: list[dict[str, Any]] = []

        # Event: revenue
        if revenue_change is not None:
            if revenue_change <= -10:
                level = "danger"
                title = "Продажи ниже предыдущего периода"
                body = (
                    f"Выручка снизилась на {abs(revenue_change):.1f}%. "
                    f"Чеки: {self._format_change(checks_change)}, "
                    f"средний чек: {self._format_change(avg_check_change)}."
                )
            elif revenue_change >= 10:
                level = "success"
                title = "Продажи растут"
                body = (
                    f"Выручка выросла на {revenue_change:.1f}%. "
                    f"Чеки: {self._format_change(checks_change)}, "
                    f"средний чек: {self._format_change(avg_check_change)}."
                )
            else:
                level = "info"
                title = "Продажи близки к прошлому периоду"
                body = (
                    f"Изменение выручки: {self._format_change(revenue_change)}."
                )

            events.append({
                "time": "08:10",
                "level": level,
                "title": title,
                "body": body,
                "action": "Проверить продажи",
                "route": "/sales",
            })

        # Event: average check
        if avg_check_change is not None and avg_check_change <= -5:
            events.append({
                "time": "11:30",
                "level": "warning",
                "title": "Средний чек снизился",
                "body": (
                    f"Средний чек уменьшился на "
                    f"{abs(avg_check_change):.1f}%. "
                    "Проверьте долю чеков без напитков и дополнительных позиций."
                ),
                "action": "Открыть возможности допродажи",
                "route": "/marketing",
            })

        # Event: peak hour
        if hourly:
            peak = max(hourly, key=lambda item: item["revenue"])
            events.append({
                "time": f'{peak["sale_hour"]:02d}:00',
                "level": "info",
                "title": "Пиковый час периода",
                "body": (
                    f'С {peak["sale_hour"]:02d}:00 до '
                    f'{(peak["sale_hour"] + 1) % 24:02d}:00 '
                    f'получено {peak["revenue"]:,.0f} ₽ '
                    f'и {peak["checks_count"]} чеков.'
                ).replace(",", " "),
                "action": "Усилить готовность смены к этому часу",
                "route": "/sales",
            })

        # Event: best basket opportunity
        if opportunities:
            best = max(
                opportunities,
                key=lambda item: float(
                    item.get("estimated_potential") or 0
                ),
            )
            potential = float(best.get("estimated_potential") or 0)
            events.append({
                "time": "15:40",
                "level": "opportunity",
                "title": (
                    f'Допродажа: {best["pair_item_name"]} '
                    f'к {best["base_item_name"]}'
                ),
                "body": (
                    f'Без дополнения прошло {best["missing_checks"]} чеков. '
                    f'Оценочный потенциал — до {potential:,.0f} ₽ '
                    f'за выбранный период.'
                ).replace(",", " "),
                "action": "Добавить в скрипт кассира или комбо",
                "route": "/marketing",
            })

        # Event: top item
        if top_items:
            top = top_items[0]
            events.append({
                "time": "18:20",
                "level": "success",
                "title": f'Лидер периода: {top["item_name"]}',
                "body": (
                    f'Продано {top["quantity"]:.0f} единиц '
                    f'на {top["revenue"]:,.0f} ₽. '
                    "Не допускайте отсутствия позиции в продаже."
                ).replace(",", " "),
                "action": "Открыть анализ меню",
                "route": "/menu",
            })

        # Daily summary points
        positives: list[str] = []
        negatives: list[str] = []

        if revenue_change is not None:
            target = positives if revenue_change >= 0 else negatives
            target.append(
                f'Выручка {self._format_change(revenue_change)}.'
            )
        if checks_change is not None:
            target = positives if checks_change >= 0 else negatives
            target.append(
                f'Количество чеков {self._format_change(checks_change)}.'
            )
        if avg_check_change is not None:
            target = positives if avg_check_change >= 0 else negatives
            target.append(
                f'Средний чек {self._format_change(avg_check_change)}.'
            )
        if opportunities:
            negatives.append(
                f'Найдено {len(opportunities)} возможностей допродажи.'
            )

        return {
            "events": events,
            "current": current,
            "previous": previous,
            "changes": {
                "revenue": revenue_change,
                "checks": checks_change,
                "avg_check": avg_check_change,
            },
            "positives": positives,
            "negatives": negatives,
            "peak_hour": (
                max(hourly, key=lambda item: item["revenue"])
                if hourly else None
            ),
            "top_items": top_items,
            "previous_from": previous_from,
            "previous_to": previous_to,
        }
