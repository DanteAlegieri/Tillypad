from datetime import date, datetime
from typing import Any

from app.db.sql_server import SqlServer
from app.repositories.sales_repository import SalesRepository


class SalesService:
    def __init__(self) -> None:
        self.repository = SalesRepository(SqlServer())

    @staticmethod
    def _clean_tilly_text(value: Any) -> str:
        if value is None:
            return ""
        text = str(value)
        text = "".join(
            char for char in text
            if ord(char) >= 32 and ord(char) != 127
        ).strip()
        for marker in ("\x19", "\x08", "\x07", "\x0c", "\x1a"):
            text = text.replace(marker, "")
        return text.strip()

    @staticmethod
    def _status(
        summary: dict[str, Any],
        comparison: dict[str, Any],
    ) -> dict[str, Any]:
        checks = int(summary["checks_count"])
        revenue = float(summary["revenue"])
        revenue_change = comparison.get("revenue_change")
        avg_change = comparison.get("avg_check_change")

        if checks == 0:
            return {
                "level": "neutral",
                "title": "За выбранный период продаж ещё не было",
                "text": (
                    "Показатели появятся после закрытия первого "
                    "положительного чека."
                ),
            }

        if revenue_change is None:
            return {
                "level": "normal",
                "title": "Продажи идут, но базы сравнения пока нет",
                "text": (
                    f"Закрыто {checks} чеков на сумму "
                    f"{revenue:,.0f} ₽."
                ).replace(",", " "),
            }

        if revenue_change >= 10:
            return {
                "level": "good",
                "title": "Продажи заметно выросли",
                "text": (
                    f"Выручка выше прошлого периода на "
                    f"{revenue_change:+.1f}%."
                ),
            }

        if revenue_change <= -10:
            return {
                "level": "risk",
                "title": "Продажи снизились",
                "text": (
                    f"Выручка ниже прошлого периода на "
                    f"{abs(revenue_change):.1f}%."
                ),
            }

        if avg_change is not None and avg_change < -8:
            return {
                "level": "warning",
                "title": "Выручка стабильна, но снижается средний чек",
                "text": (
                    f"Средний чек изменился на {avg_change:+.1f}%."
                ),
            }

        return {
            "level": "normal",
            "title": "Продажи находятся в стабильном диапазоне",
            "text": (
                f"Изменение выручки к прошлому периоду: "
                f"{revenue_change:+.1f}%."
            ),
        }

    @staticmethod
    def _extremes(
        daily: list[dict[str, Any]],
        hourly: list[dict[str, Any]],
    ) -> dict[str, Any]:
        nonzero_days = [
            row for row in daily if float(row.get("revenue") or 0) > 0
        ]
        nonzero_hours = [
            row for row in hourly if float(row.get("revenue") or 0) > 0
        ]
        return {
            "best_day": (
                max(nonzero_days, key=lambda row: row["revenue"])
                if nonzero_days else None
            ),
            "weak_day": (
                min(nonzero_days, key=lambda row: row["revenue"])
                if nonzero_days else None
            ),
            "peak_hour": (
                max(nonzero_hours, key=lambda row: row["revenue"])
                if nonzero_hours else None
            ),
        }

    @staticmethod
    def _insights(
        summary: dict[str, Any],
        comparison: dict[str, Any],
        top_items: list[dict[str, Any]],
        top_groups: list[dict[str, Any]],
        extremes: dict[str, Any],
    ) -> list[dict[str, str]]:
        if int(summary["checks_count"]) == 0:
            return [
                {
                    "tone": "neutral",
                    "title": "Нет закрытых продаж",
                    "text": "Выбранный период пока пуст.",
                }
            ]

        insights: list[dict[str, str]] = []
        revenue_change = comparison.get("revenue_change")
        checks_change = comparison.get("checks_change")
        avg_change = comparison.get("avg_check_change")

        if revenue_change is not None:
            insights.append({
                "tone": "good" if revenue_change >= 0 else "risk",
                "title": (
                    "Выручка выросла"
                    if revenue_change >= 0
                    else "Выручка снизилась"
                ),
                "text": f"{revenue_change:+.1f}% к прошлому периоду.",
            })

        if checks_change is not None:
            insights.append({
                "tone": "good" if checks_change >= 0 else "risk",
                "title": (
                    "Чеков стало больше"
                    if checks_change >= 0
                    else "Чеков стало меньше"
                ),
                "text": f"{checks_change:+.1f}% к прошлому периоду.",
            })

        if avg_change is not None:
            insights.append({
                "tone": "good" if avg_change >= 0 else "warning",
                "title": (
                    "Средний чек вырос"
                    if avg_change >= 0
                    else "Средний чек снизился"
                ),
                "text": f"{avg_change:+.1f}% к прошлому периоду.",
            })

        if top_items:
            insights.append({
                "tone": "normal",
                "title": "Лидер продаж",
                "text": (
                    f'{top_items[0]["item_name"]} — '
                    f'{top_items[0]["revenue"]:,.0f} ₽.'
                ).replace(",", " "),
            })

        if top_groups:
            insights.append({
                "tone": "normal",
                "title": "Главная категория",
                "text": (
                    f'{top_groups[0]["group_name"]} — '
                    f'{top_groups[0]["revenue"]:,.0f} ₽.'
                ).replace(",", " "),
            })

        if extremes["peak_hour"]:
            hour = int(extremes["peak_hour"]["sale_hour"])
            insights.append({
                "tone": "warning",
                "title": "Пиковый час",
                "text": (
                    f"{hour:02d}:00–{hour + 1:02d}:00 — "
                    f'{extremes["peak_hour"]["revenue"]:,.0f} ₽.'
                ).replace(",", " "),
            })

        return insights[:5]

    @staticmethod
    def _normalize_payment_name(value: Any) -> str:
        raw = SalesService._clean_tilly_text(value)
        lowered = raw.lower()

        if not raw:
            return "Не определено"

        if (
            "bank card" in lowered
            or "bankkarten" in lowered
            or "банків" in lowered
            or "банковск" in lowered
            or "карта" in lowered
        ):
            return "Банковская карта"

        if (
            "cash" in lowered
            or "bargeld" in lowered
            or "готівка" in lowered
            or "налич" in lowered
        ):
            return "Наличные"

        if "qr" in lowered:
            return "QR-код"

        if "перевод" in lowered:
            return "Перевод на карту"

        if "питание персонала" in lowered:
            return "Питание персонала"

        if "собственник" in lowered:
            return "Собственники"

        if "бонус" in lowered:
            return "Бонусы"

        return raw

    @staticmethod
    def _assign_abc(items: list[dict[str, Any]]) -> None:
        total = sum(float(item.get("revenue") or 0) for item in items)
        cumulative = 0.0

        for item in items:
            revenue = float(item.get("revenue") or 0)
            share = revenue / total * 100 if total else 0
            cumulative += share

            if cumulative <= 80:
                abc = "A"
            elif cumulative <= 95:
                abc = "B"
            else:
                abc = "C"

            item["abc"] = abc
            item["cumulative_share"] = round(cumulative, 1)

    @staticmethod
    def _aggregate_daily(
        rows: list[dict[str, Any]],
        date_from: date,
        date_to: date,
    ) -> dict[str, Any]:
        period_days = (date_to - date_from).days + 1

        if period_days <= 1:
            return {
                "mode": "hour",
                "title": "Выручка и средний чек по часам",
                "labels": [],
                "revenue": [],
                "avg_check": [],
            }

        if period_days <= 45:
            return {
                "mode": "day",
                "title": "Выручка и средний чек по дням",
                "labels": [row["sale_date"] for row in rows],
                "revenue": [float(row["revenue"]) for row in rows],
                "avg_check": [float(row["avg_check"]) for row in rows],
            }

        grouped: dict[str, dict[str, float]] = {}
        for row in rows:
            sale_date = datetime.strptime(
                str(row["sale_date"]),
                "%Y-%m-%d",
            ).date()
            monday = sale_date.fromordinal(
                sale_date.toordinal() - sale_date.weekday()
            )
            key = monday.isoformat()

            bucket = grouped.setdefault(
                key,
                {"revenue": 0.0, "checks_count": 0.0},
            )
            bucket["revenue"] += float(row["revenue"])
            bucket["checks_count"] += float(row["checks_count"])

        labels = []
        revenue = []
        avg_check = []

        for key in sorted(grouped):
            bucket = grouped[key]
            labels.append(key)
            revenue.append(round(bucket["revenue"], 2))
            avg_check.append(
                round(
                    bucket["revenue"] / bucket["checks_count"],
                    2,
                )
                if bucket["checks_count"] else 0
            )

        return {
            "mode": "week",
            "title": "Выручка и средний чек по неделям",
            "labels": labels,
            "revenue": revenue,
            "avg_check": avg_check,
        }

    def dashboard(
        self,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        summary = self.repository.summary(date_from, date_to)
        start = summary["date_from"]
        end = summary["date_to"]

        daily = self.repository.daily_sales(start, end)
        hourly = self.repository.hourly_sales(start, end)
        comparison = self.repository.comparison(start, end)
        top_items = self.repository.top_items(start, end)
        top_groups = self.repository.top_groups(start, end)
        payments = self.repository.payment_mix(start, end)
        recent_checks = self.repository.recent_checks(start, end)

        for row in top_items:
            row["item_name"] = self._clean_tilly_text(
                row.get("item_name")
            ) or "Позиция без названия"

        for row in top_groups:
            row["group_name"] = self._clean_tilly_text(
                row.get("group_name")
            ) or "Без категории"

        for row in payments:
            row["payment_name"] = self._normalize_payment_name(
                row.get("payment_name")
            )

        for row in recent_checks:
            row["cashier_name"] = self._clean_tilly_text(
                row.get("cashier_name")
            ) or "Не указан"
            row["check_name"] = self._clean_tilly_text(
                row.get("check_name")
            ) or str(row.get("check_id"))

        payment_total = sum(
            float(row["payment_sum"]) for row in payments
        )
        for row in payments:
            row["share"] = (
                round(float(row["payment_sum"]) / payment_total * 100, 1)
                if payment_total else 0
            )

        revenue = float(summary["revenue"])
        for row in top_items:
            row["share"] = (
                round(float(row["revenue"]) / revenue * 100, 1)
                if revenue else 0
            )

        self._assign_abc(top_items)

        extremes = self._extremes(daily, hourly)
        adaptive_chart = self._aggregate_daily(
            daily,
            start,
            end,
        )

        if adaptive_chart["mode"] == "hour":
            adaptive_chart = {
                "mode": "hour",
                "title": "Выручка и средний чек по часам",
                "labels": [
                    f'{int(row["sale_hour"]):02d}:00'
                    for row in hourly
                ],
                "revenue": [
                    float(row["revenue"])
                    for row in hourly
                ],
                "avg_check": [
                    float(row["avg_check"])
                    for row in hourly
                ],
            }

        return {
            "summary": summary,
            "daily": daily,
            "hourly": hourly,
            "comparison": comparison,
            "top_items": top_items,
            "top_groups": top_groups,
            "payments": payments,
            "recent_checks": recent_checks,
            "extremes": extremes,
            "adaptive_chart": adaptive_chart,
            "status": self._status(summary, comparison),
            "insights": self._insights(
                summary,
                comparison,
                top_items,
                top_groups,
                extremes,
            ),
            "has_sales": int(summary["checks_count"]) > 0,
        }
