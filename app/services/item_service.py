from datetime import date, timedelta
from typing import Any

from app.db.sql_server import SqlServer
from app.repositories.item_repository import ItemRepository


class ItemService:
    def __init__(self) -> None:
        self.repository = ItemRepository(SqlServer())

    def load(
        self,
        item_id: str,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any] | None:
        info = self.repository.item_info(item_id)
        if not info:
            return None

        summary = self.repository.summary(
            item_id,
            date_from,
            date_to,
        )
        daily = self.repository.daily_sales(
            item_id,
            date_from,
            date_to,
        )
        hourly = self.repository.hourly_sales(
            item_id,
            date_from,
            date_to,
        )
        heatmap = self.repository.heatmap(
            item_id,
            date_from,
            date_to,
        )
        links = self.repository.basket_links(
            item_id,
            date_from,
            date_to,
        )
        classification = self.repository.classification(
            item_id,
            date_from,
            date_to,
        )

        health = self._health_score(
            summary,
            classification,
            links,
        )
        forecast = self._forecast(
            daily,
            summary,
        )
        insights = self._insights(
            info,
            summary,
            hourly,
            classification,
            links,
            forecast,
        )

        return {
            "info": info,
            "summary": summary,
            "daily": daily,
            "hourly": hourly,
            "heatmap": heatmap,
            "links": links,
            "classification": classification,
            "health": health,
            "forecast": forecast,
            "insights": insights,
        }

    @staticmethod
    def _health_score(
        summary: dict[str, Any],
        classification: dict[str, Any],
        links: list[dict[str, Any]],
    ) -> dict[str, Any]:
        score = 0

        score += {
            "A": 35,
            "B": 22,
            "C": 10,
        }.get(classification["abc"], 0)

        score += {
            "X": 25,
            "Y": 16,
            "Z": 7,
        }.get(classification["xyz"], 0)

        share = float(classification["share"] or 0)
        score += min(round(share * 1.5), 20)

        if summary["quantity_change"] is not None:
            if summary["quantity_change"] > 10:
                score += 10
            elif summary["quantity_change"] >= 0:
                score += 6
            elif summary["quantity_change"] > -15:
                score += 3

        if links:
            score += min(10, round(links[0]["confidence"] / 10))

        score = min(max(score, 0), 100)

        if score >= 80:
            label = "Отличное блюдо"
            status = "good"
        elif score >= 55:
            label = "Требует наблюдения"
            status = "attention"
        else:
            label = "Требует решения"
            status = "risk"

        return {
            "score": score,
            "label": label,
            "status": status,
        }

    @staticmethod
    def _forecast(
        daily: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        recent = daily[-14:]
        if not recent:
            return {
                "next_7_quantity": 0,
                "next_7_revenue": 0,
                "confidence": 0,
            }

        weights = list(range(1, len(recent) + 1))
        weight_sum = sum(weights)
        weighted_quantity = sum(
            row["quantity"] * weight
            for row, weight in zip(recent, weights)
        ) / weight_sum
        weighted_revenue = sum(
            row["revenue"] * weight
            for row, weight in zip(recent, weights)
        ) / weight_sum

        active_days = sum(
            1
            for row in recent
            if row["quantity"] > 0
        )
        confidence = round(
            min(95, 45 + (active_days / max(len(recent), 1)) * 50)
        )

        return {
            "next_7_quantity": round(weighted_quantity * 7),
            "next_7_revenue": round(weighted_revenue * 7),
            "confidence": confidence,
        }

    @staticmethod
    def _insights(
        info: dict[str, Any],
        summary: dict[str, Any],
        hourly: list[dict[str, Any]],
        classification: dict[str, Any],
        links: list[dict[str, Any]],
        forecast: dict[str, Any],
    ) -> list[dict[str, str]]:
        insights: list[dict[str, str]] = []

        if classification["matrix"] == "AX":
            insights.append({
                "level": "positive",
                "title": "Основа меню",
                "text": (
                    f'{info["item_name"]} сочетает высокую долю '
                    "выручки и стабильный спрос."
                ),
            })
        elif classification["abc"] == "A" and classification["xyz"] == "Z":
            insights.append({
                "level": "warning",
                "title": "Нестабильный лидер",
                "text": (
                    "Позиция приносит значимую выручку, "
                    "но спрос сильно колеблется."
                ),
            })

        if summary["quantity_change"] is not None:
            change = summary["quantity_change"]
            if change >= 10:
                insights.append({
                    "level": "positive",
                    "title": "Продажи растут",
                    "text": (
                        f"Количество продаж выросло на {change}% "
                        "к предыдущему периоду."
                    ),
                })
            elif change <= -10:
                insights.append({
                    "level": "warning",
                    "title": "Продажи снижаются",
                    "text": (
                        f"Количество продаж снизилось на {abs(change)}% "
                        "к предыдущему периоду."
                    ),
                })

        if hourly:
            peak = max(hourly, key=lambda row: row["quantity"])
            insights.append({
                "level": "info",
                "title": "Лучшее время",
                "text": (
                    f'Пик спроса приходится на '
                    f'{peak["sale_hour"]:02d}:00–'
                    f'{peak["sale_hour"] + 1:02d}:00.'
                ),
            })

        if links:
            leader = links[0]
            insights.append({
                "level": "info",
                "title": "Лучшая допродажа",
                "text": (
                    f'{leader["related_name"]} встречается в '
                    f'{leader["confidence"]}% чеков с этой позицией.'
                ),
            })

        insights.append({
            "level": "info",
            "title": "Прогноз на 7 дней",
            "text": (
                f'Ожидается около {forecast["next_7_quantity"]} продаж '
                f'на {forecast["next_7_revenue"]:,.0f} ₽.'
            ).replace(",", " "),
        })

        return insights
