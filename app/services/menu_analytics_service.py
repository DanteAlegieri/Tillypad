from datetime import date, timedelta
from math import sqrt
from typing import Any

from app.db.sql_server import SqlServer
from app.repositories.menu_analytics_repository import (
    MenuAnalyticsRepository,
)


class MenuAnalyticsService:
    def __init__(self) -> None:
        self.repository = MenuAnalyticsRepository(SqlServer())

    @staticmethod
    def _clean(value: Any) -> str:
        if value is None:
            return ""
        return "".join(
            char for char in str(value)
            if ord(char) >= 32 and ord(char) != 127
        ).strip()

    @staticmethod
    def _abc(items: list[dict[str, Any]]) -> None:
        total = sum(float(item.get("revenue") or 0) for item in items)
        cumulative = 0.0

        for item in items:
            share = (
                float(item.get("revenue") or 0) / total * 100
                if total else 0
            )
            cumulative += share
            if cumulative <= 80:
                item["abc"] = "A"
            elif cumulative <= 95:
                item["abc"] = "B"
            else:
                item["abc"] = "C"
            item["revenue_share"] = round(share, 1)

    @staticmethod
    def _xyz(items: list[dict[str, Any]]) -> None:
        for item in items:
            avg = float(item.get("avg_daily_quantity") or 0)
            std = float(item.get("std_daily_quantity") or 0)
            coefficient = std / avg if avg else 999

            if coefficient <= 0.35:
                xyz = "X"
            elif coefficient <= 0.75:
                xyz = "Y"
            else:
                xyz = "Z"

            item["xyz"] = xyz
            item["variation"] = round(coefficient * 100, 1)

    @staticmethod
    def _score(items: list[dict[str, Any]]) -> None:
        max_quantity = max(
            (float(item.get("quantity") or 0) for item in items),
            default=1,
        )
        max_revenue = max(
            (float(item.get("revenue") or 0) for item in items),
            default=1,
        )

        for item in items:
            popularity = (
                float(item.get("quantity") or 0) / max_quantity * 100
                if max_quantity else 0
            )
            revenue_score = (
                float(item.get("revenue") or 0) / max_revenue * 100
                if max_revenue else 0
            )
            stability = {
                "X": 100,
                "Y": 65,
                "Z": 30,
            }.get(item.get("xyz"), 30)

            score = (
                popularity * 0.45
                + revenue_score * 0.35
                + stability * 0.20
            )
            item["popularity_score"] = round(popularity, 1)
            item["revenue_score"] = round(revenue_score, 1)
            item["stability_score"] = stability
            item["index_score"] = round(score)
            item["index_formula"] = {
                "popularity_weight": 45,
                "revenue_weight": 35,
                "stability_weight": 20,
            }

    @staticmethod
    def _matrix_label(item: dict[str, Any]) -> dict[str, str]:
        matrix = item.get("matrix", "CZ")
        labels = {
            "AX": ("Лидер меню", "Сильный и стабильный спрос"),
            "AY": ("Сильная позиция", "Высокий вклад, спрос колеблется"),
            "AZ": ("Риск лидера", "Высокий вклад, но спрос нестабилен"),
            "BX": ("Хорошая позиция", "Средний вклад и стабильный спрос"),
            "BY": ("Позиция под наблюдением", "Средний вклад и колебания"),
            "BZ": ("Нестабильная позиция", "Средний вклад, спрос непредсказуем"),
            "CX": ("Нишевая стабильная", "Низкий вклад, но спрос устойчив"),
            "CY": ("Слабая позиция", "Низкий вклад и колебания спроса"),
            "CZ": ("Кандидат на пересмотр", "Низкий и нестабильный спрос"),
        }
        title, subtitle = labels.get(
            matrix,
            ("Позиция меню", "Требуется дополнительный анализ"),
        )
        return {
            "title": title,
            "subtitle": subtitle,
        }

    @staticmethod
    def _action(item: dict[str, Any]) -> dict[str, str]:
        abc = item.get("abc", "C")
        xyz = item.get("xyz", "Z")
        score = int(item.get("index_score") or 0)

        if abc == "A" and xyz == "X":
            return {
                "code": "develop",
                "title": "Развивать",
                "text": "Поддерживать наличие и усиливать допродажи.",
            }
        if abc == "A":
            return {
                "code": "stabilize",
                "title": "Стабилизировать",
                "text": "Проверить причины колебаний и обеспечить наличие.",
            }
        if abc == "B" and score >= 45:
            return {
                "code": "watch",
                "title": "Наблюдать",
                "text": "Следить за динамикой и тестировать продвижение.",
            }
        if abc == "C" and xyz == "X":
            return {
                "code": "combo",
                "title": "Включить в комбо",
                "text": "Спрос устойчив, но вклад в выручку низкий.",
            }
        if abc == "C" and xyz in {"Y", "Z"}:
            return {
                "code": "review",
                "title": "Пересмотреть",
                "text": "Проверить цену, подачу, описание и необходимость.",
            }
        return {
            "code": "watch",
            "title": "Наблюдать",
            "text": "Недостаточно данных для жёсткого решения.",
        }

    @staticmethod
    def _reason(item: dict[str, Any], period_days: int) -> list[str]:
        reasons: list[str] = []
        quantity = float(item.get("quantity") or 0)
        share = float(item.get("revenue_share") or 0)
        active_days = int(item.get("active_days") or 0)
        variation = float(item.get("variation") or 0)

        if share >= 15:
            reasons.append(
                f"Даёт {share:.1f}% выручки меню."
            )
        elif share < 1:
            reasons.append(
                f"Даёт только {share:.1f}% выручки меню."
            )

        if quantity <= 1:
            reasons.append("Продана только 1 единица за период.")
        elif quantity <= 3:
            reasons.append(f"Продано всего {quantity:.0f} единицы за период.")

        if period_days >= 7:
            if active_days <= max(1, period_days // 7):
                reasons.append(
                    f"Продажи были только в {active_days} днях из {period_days}."
                )
            elif active_days >= int(period_days * 0.7):
                reasons.append(
                    f"Продаётся регулярно: {active_days} дней из {period_days}."
                )

        if variation <= 35:
            reasons.append("Спрос стабильный.")
        elif variation >= 75:
            reasons.append("Спрос сильно колеблется.")

        return reasons[:4]

    @staticmethod
    def _recommendation(item: dict[str, Any]) -> dict[str, str]:
        abc = item.get("abc", "C")
        xyz = item.get("xyz", "Z")
        score = int(item.get("index_score") or 0)

        if abc == "A" and xyz == "X":
            return {
                "level": "good",
                "title": "Ключевая стабильная позиция",
                "text": (
                    "Поддерживайте постоянный запас и контролируйте "
                    "доступность в часы пик."
                ),
            }
        if abc == "A" and xyz in {"Y", "Z"}:
            return {
                "level": "warning",
                "title": "Сильная, но нестабильная позиция",
                "text": (
                    "Проверьте сезонность и причины резких колебаний спроса."
                ),
            }
        if abc == "C" and xyz == "Z":
            return {
                "level": "risk",
                "title": "Слабая нестабильная позиция",
                "text": (
                    "Рассмотрите акцию, изменение подачи или исключение "
                    "из постоянного меню."
                ),
            }
        if score >= 70:
            return {
                "level": "good",
                "title": "Перспективная позиция",
                "text": "Поддерживайте наличие и используйте в продвижении.",
            }
        if score >= 45:
            return {
                "level": "warning",
                "title": "Позиция требует наблюдения",
                "text": "Следите за динамикой и стабильностью спроса.",
            }
        return {
            "level": "risk",
            "title": "Позиция требует пересмотра",
            "text": "Проверьте цену, описание, подачу и место в меню.",
        }

    @staticmethod
    def _advice(items: list[dict[str, Any]]) -> list[dict[str, str]]:
        advice: list[dict[str, str]] = []

        ax = [i for i in items if i["abc"] == "A" and i["xyz"] == "X"]
        cz = [i for i in items if i["abc"] == "C" and i["xyz"] == "Z"]
        leaders = sorted(
            items,
            key=lambda row: row["index_score"],
            reverse=True,
        )

        if ax:
            advice.append({
                "level": "good",
                "title": "Основа меню",
                "text": (
                    f'{ax[0]["item_name"]} — стабильный лидер. '
                    "Не допускайте стоп-листа."
                ),
            })

        if cz:
            advice.append({
                "level": "risk",
                "title": "Кандидат на пересмотр",
                "text": (
                    f'{cz[0]["item_name"]} имеет низкий и нестабильный спрос.'
                ),
            })

        if leaders:
            advice.append({
                "level": "normal",
                "title": "Самый высокий индекс",
                "text": (
                    f'{leaders[0]["item_name"]}: '
                    f'{leaders[0]["index_score"]}/100.'
                ),
            })

        return advice[:4]

    def dashboard(
        self,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        start, end = self.repository.normalize_period(date_from, date_to)
        items = self.repository.item_metrics(start, end)

        for item in items:
            item["item_name"] = self._clean(item.get("item_name"))
            item["group_name"] = self._clean(item.get("group_name"))
            for key in (
                "quantity",
                "revenue",
                "avg_price",
                "avg_daily_quantity",
                "std_daily_quantity",
            ):
                item[key] = float(item.get(key) or 0)
            item["checks_count"] = int(item.get("checks_count") or 0)
            item["active_days"] = int(item.get("active_days") or 0)

        self._abc(items)
        self._xyz(items)
        self._score(items)

        period_days = (end - start).days + 1

        for item in items:
            item["matrix"] = item["abc"] + item["xyz"]
            item["matrix_label"] = self._matrix_label(item)
            item["recommendation"] = self._recommendation(item)
            item["action"] = self._action(item)
            item["reasons"] = self._reason(item, period_days)

        matrix_counts: dict[str, int] = {}
        for item in items:
            matrix_counts[item["matrix"]] = (
                matrix_counts.get(item["matrix"], 0) + 1
            )

        return {
            "date_from": start,
            "date_to": end,
            "items": items,
            "matrix_counts": matrix_counts,
            "total_items": len(items),
            "total_quantity": sum(i["quantity"] for i in items),
            "total_revenue": sum(i["revenue"] for i in items),
            "avg_price": (
                sum(i["revenue"] for i in items)
                / sum(i["quantity"] for i in items)
                if sum(i["quantity"] for i in items)
                else 0
            ),
            "leaders": sorted(
                items,
                key=lambda row: row["index_score"],
                reverse=True,
            )[:10],
            "weak_items": sorted(
                items,
                key=lambda row: row["index_score"],
            )[:10],
            "advice": self._advice(items),
        }

    def item_detail(
        self,
        item_id: str,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any] | None:
        dashboard = self.dashboard(date_from, date_to)
        item = next(
            (
                row for row in dashboard["items"]
                if str(row["item_id"]).lower() == item_id.lower()
            ),
            None,
        )
        if item is None:
            return None

        daily = self.repository.item_daily(
            item_id,
            dashboard["date_from"],
            dashboard["date_to"],
        )
        hourly = self.repository.item_hourly(
            item_id,
            dashboard["date_from"],
            dashboard["date_to"],
        )
        pairs = self.repository.basket_pairs(
            item_id,
            dashboard["date_from"],
            dashboard["date_to"],
        )

        for row in daily:
            row["sale_date"] = str(row["sale_date"])
            row["quantity"] = float(row.get("quantity") or 0)
            row["revenue"] = float(row.get("revenue") or 0)
            row["checks_count"] = int(row.get("checks_count") or 0)

        for row in hourly:
            row["sale_hour"] = int(row.get("sale_hour") or 0)
            row["quantity"] = float(row.get("quantity") or 0)
            row["revenue"] = float(row.get("revenue") or 0)

        for row in pairs:
            row["item_name"] = self._clean(row.get("item_name"))
            row["pair_checks"] = int(row.get("pair_checks") or 0)
            row["base_checks"] = int(row.get("base_checks") or 0)
            row["attach_rate"] = float(row.get("attach_rate") or 0)

        peak_hour = (
            max(hourly, key=lambda row: row["quantity"])
            if hourly else None
        )
        best_day = (
            max(daily, key=lambda row: row["quantity"])
            if daily else None
        )

        return {
            "item": item,
            "date_from": dashboard["date_from"],
            "date_to": dashboard["date_to"],
            "daily": daily,
            "hourly": hourly,
            "pairs": pairs,
            "peak_hour": peak_hour,
            "best_day": best_day,
        }
