from datetime import datetime
from typing import Any
from app.brain.models import BrainReason, BrainReport, DecisionCard, TimelineEvent

class BrainEngine:
    def build(self, data: dict[str, Any]) -> BrainReport:
        current = data["current"]
        forecast = data["forecast"]
        menu = data["menu"]

        target = float(forecast["target"] or 0)
        revenue = float(current["revenue"] or 0)
        avg_check = float(current["avg_check"] or 0)
        remaining = max(target - revenue, 0)
        probability = int(forecast["probability"] or 0)
        revenue_change = data.get("revenue_change")
        avg_check_change = data.get("avg_check_change")

        plan_percent = revenue / target * 100 if target else 0
        reasons = [
            BrainReason(
                "Дневной план",
                f"{plan_percent:.1f}% выполнено",
                "positive" if plan_percent >= 95 else "warning",
                25 if plan_percent >= 95 else 15 if plan_percent >= 75 else 5,
            ),
            BrainReason(
                "Здоровье меню",
                f'{menu["score"]}/100',
                "positive" if menu["score"] >= 75 else "warning",
                20 if menu["score"] >= 75 else 12,
            ),
            BrainReason(
                "Вероятность плана",
                f"{probability}%",
                "positive" if probability >= 70 else "warning",
                15 if probability >= 70 else 8,
            ),
        ]

        if avg_check_change is not None:
            reasons.append(
                BrainReason(
                    "Средний чек",
                    f'{"+" if avg_check_change >= 0 else ""}{avg_check_change}% ко вчера',
                    "positive" if avg_check_change >= 0 else "warning",
                    20 if avg_check_change >= 0 else 8,
                )
            )

        if revenue_change is not None:
            reasons.append(
                BrainReason(
                    "Темп выручки",
                    f'{"+" if revenue_change >= 0 else ""}{revenue_change}% ко вчера',
                    "positive" if revenue_change >= 0 else "warning",
                    20 if revenue_change >= 0 else 10,
                )
            )

        pulse_score = min(100, sum(r.score for r in reasons))
        pulse_label = (
            "Отличное состояние" if pulse_score >= 85
            else "Хорошее состояние" if pulse_score >= 70
            else "Требует внимания" if pulse_score >= 50
            else "Критическое состояние"
        )

        trend = 0
        if revenue_change is not None:
            trend += 1 if revenue_change >= 0 else -1
        if avg_check_change is not None:
            trend += 1 if avg_check_change >= 0 else -1
        pulse_trend = "растёт" if trend > 0 else "снижается" if trend < 0 else "стабилен"

        if remaining <= 0:
            title = "План выполнен"
            action = "Сохраняйте текущий темп и работайте на рост среднего чека."
            effect = f'+{revenue-target:,.0f} ₽ к плану'.replace(",", " ")
            priority = "low"
            confidence = 96
        elif remaining <= max(avg_check, 1):
            title = "Закройте план следующим чеком"
            action = "Предложите напиток, картофель или комбо следующему гостю."
            effect = f'Нужно ещё {remaining:,.0f} ₽'.replace(",", " ")
            priority = "high"
            confidence = min(98, max(70, probability + 20))
        elif avg_check_change is not None and avg_check_change < -5:
            title = "Поднимите средний чек"
            action = "Сделайте допродажу напитка или картофеля каждому следующему гостю."
            effect = f'До плана {remaining:,.0f} ₽'.replace(",", " ")
            priority = "high"
            confidence = min(95, max(65, probability + 10))
        else:
            title = "Сохраняйте темп"
            action = "Продолжайте текущий сценарий продаж и следите за средним чеком."
            effect = f'Прогноз {forecast["forecast_revenue"]:,.0f} ₽'.replace(",", " ")
            priority = "medium"
            confidence = max(55, probability)

        timeline = []
        hourly = forecast.get("hourly", [])
        if hourly:
            first = hourly[0]
            peak = max(hourly, key=lambda x: x["revenue"])
            timeline.append(TimelineEvent(f'{first["sale_hour"]:02d}:00', "info", "Начало продаж", "Зафиксированы первые чеки дня."))
            timeline.append(TimelineEvent(f'{peak["sale_hour"]:02d}:00', "positive", "Пик выручки", f'{peak["revenue"]:,.0f} ₽ за час.'.replace(",", " ")))
        timeline.append(TimelineEvent(datetime.now().strftime("%H:%M"), "warning" if priority == "high" else "info", "Актуальное решение Brain", action))

        changes = []
        if revenue_change is not None:
            changes.append({"name":"Выручка","value":revenue_change,"direction":"up" if revenue_change >= 0 else "down"})
        if avg_check_change is not None:
            changes.append({"name":"Средний чек","value":avg_check_change,"direction":"up" if avg_check_change >= 0 else "down"})
        changes.append({"name":"Меню","value":menu["score"],"direction":"up" if menu["score"] >= 70 else "down"})
        changes.append({"name":"Вероятность плана","value":probability,"direction":"up" if probability >= 70 else "down"})

        pulse_components = [
            {
                "name": "Продажи",
                "score": 90 if revenue_change is not None and revenue_change >= 0 else 55,
                "trend": "up" if revenue_change is not None and revenue_change >= 0 else "down",
            },
            {
                "name": "Средний чек",
                "score": 90 if avg_check_change is not None and avg_check_change >= 0 else 50,
                "trend": "up" if avg_check_change is not None and avg_check_change >= 0 else "down",
            },
            {
                "name": "Меню",
                "score": int(menu["score"]),
                "trend": "up" if menu["score"] >= 70 else "down",
            },
            {
                "name": "План",
                "score": min(100, int(plan_percent)),
                "trend": "up" if plan_percent >= 90 else "down",
            },
        ]

        if remaining <= 0:
            headline = "Сегодня ресторан завершает день уверенно."
        elif remaining <= max(avg_check, 1):
            headline = "До выполнения плана остался один хороший чек."
        elif revenue_change is not None and revenue_change < -20:
            headline = "Сегодня день сложнее обычного, но ситуацию ещё можно исправить."
        elif probability >= 80:
            headline = "Сегодня ресторан движется по плану."
        else:
            headline = "Сегодня ресторан требует внимания."

        thought = (
            "Если сохранить текущий темп, следующий средний чек почти наверняка закроет план."
            if remaining <= max(avg_check, 1) and remaining > 0
            else "Сейчас самое выгодное действие — увеличить средний чек через допродажу."
            if avg_check_change is not None and avg_check_change < -5
            else "Система не видит срочных отклонений."
        )

        return {
            "pulse_score": pulse_score,
            "pulse_label": pulse_label,
            "pulse_trend": pulse_trend,
            "decision": DecisionCard(
                "primary_action",
                priority,
                title,
                action,
                effect,
                confidence,
                reasons,
            ),
            "timeline": timeline,
            "changes": changes,
            "pulse_components": pulse_components,
            "headline": headline,
            "thought": thought,
        }
