from datetime import datetime
from typing import Any

from app.db.sql_server import SqlServer
from app.repositories.decision_repository import DecisionRepository
from app.brain.engine import BrainEngine


class CEOService:
    def __init__(self) -> None:
        self.repository = DecisionRepository(SqlServer())
        self.brain = BrainEngine()

    @staticmethod
    def _greeting() -> str:
        hour = datetime.now().hour

        if hour < 6:
            return "Доброй ночи"
        if hour < 12:
            return "Доброе утро"
        if hour < 18:
            return "Добрый день"
        return "Добрый вечер"

    @staticmethod
    def _main_action(data: dict[str, Any]) -> dict[str, Any]:
        current = data["current"]
        forecast = data["forecast"]
        target = float(forecast["target"] or 0)

        if target and current["revenue"] >= target:
            return {
                "level": "positive",
                "title": "План уже выполнен",
                "text": (
                    "Сохраняйте текущий темп и не снижайте активность "
                    "до закрытия смены."
                ),
                "effect": (
                    f'+{current["revenue"] - target:,.0f} ₽ к плану'
                ).replace(",", " "),
            }

        missing = max(target - current["revenue"], 0)

        if missing <= 0:
            return {
                "level": "positive",
                "title": "День идёт уверенно",
                "text": "Система не видит срочных действий.",
                "effect": "Риск низкий",
            }

        if missing <= 600:
            return {
                "level": "warning",
                "title": "Закройте план одной допродажей",
                "text": (
                    "Предложите следующему гостю комбо, напиток "
                    "или дополнительную позицию."
                ),
                "effect": (
                    f'Нужно ещё около {missing:,.0f} ₽'
                ).replace(",", " "),
            }

        if missing <= 2000:
            return {
                "level": "warning",
                "title": "Поднимите средний чек",
                "text": (
                    "Сделайте акцент на напитках, картофеле и комбо "
                    "в каждом следующем заказе."
                ),
                "effect": (
                    f'До плана около {missing:,.0f} ₽'
                ).replace(",", " "),
            }

        return {
            "level": "risk",
            "title": "Нужен активный сценарий продаж",
            "text": (
                "План заметно отстаёт. Продвигайте самые сильные "
                "комбо и допродажи до конца смены."
            ),
            "effect": (
                f'Отставание около {missing:,.0f} ₽'
            ).replace(",", " "),
        }

    @staticmethod
    def _brain_notes(data: dict[str, Any]) -> list[dict[str, str]]:
        notes: list[dict[str, str]] = []

        revenue_change = data["revenue_change"]
        avg_check_change = data["avg_check_change"]
        forecast = data["forecast"]
        menu = data["menu"]

        if revenue_change is not None:
            notes.append({
                "level": "positive" if revenue_change >= 0 else "warning",
                "title": "Выручка",
                "text": (
                    f'Сегодня {"выше" if revenue_change >= 0 else "ниже"} '
                    f'вчера на {abs(revenue_change)}%.'
                ),
            })

        if avg_check_change is not None:
            notes.append({
                "level": "positive" if avg_check_change >= 0 else "warning",
                "title": "Средний чек",
                "text": (
                    f'Средний чек {"растёт" if avg_check_change >= 0 else "снижается"} '
                    f'на {abs(avg_check_change)}% ко вчера.'
                ),
            })

        if forecast["next_peak_hour"] is not None:
            notes.append({
                "level": "info",
                "title": "Следующий пик",
                "text": (
                    f'Вероятный пик — '
                    f'{forecast["next_peak_hour"]:02d}:00–'
                    f'{forecast["next_peak_hour"] + 1:02d}:00.'
                ),
            })

        if menu["leader_name"]:
            notes.append({
                "level": "positive",
                "title": "Лидер меню",
                "text": (
                    f'{menu["leader_name"]} даёт '
                    f'{menu["leader_share"]:.1f}% выручки меню.'
                ),
            })

        if menu["weak_count"] > 0:
            notes.append({
                "level": "warning",
                "title": "Слабые позиции",
                "text": (
                    f'{menu["weak_count"]} позиций почти не продаются.'
                ),
            })

        return notes[:5]

    def load(self) -> dict[str, Any]:
        executive = self.repository.executive()
        forecast = executive["forecast"]
        current = executive["current"]
        target = float(forecast["target"] or 0)

        progress = (
            min(round(current["revenue"] / target * 100, 1), 100)
            if target
            else 0
        )

        brain_report = self.brain.build(executive)

        return {
            "greeting": self._greeting(),
            "status": executive["status"],
            "status_label": executive["status_label"],
            "health": executive["restaurant_score"],
            "current": current,
            "forecast": forecast,
            "menu": executive["menu"],
            "main_action": self._main_action(executive),
            "brain_notes": self._brain_notes(executive),
            "progress": progress,
            "remaining": max(target - current["revenue"], 0),
            "alerts": executive["alerts"],
            "brain_report": brain_report,
        }
