from __future__ import annotations

from typing import Any

from .models import Event, Recommendation


def build_recommendations(
    *,
    revenue_delta: float | None,
    average_check_delta: float | None,
    menu_items: list[dict[str, Any]],
    hourly: list[dict[str, Any]],
    agent_online: bool,
    sync_age_minutes: int | None,
) -> tuple[list[Recommendation], list[Event]]:
    recommendations: list[Recommendation] = []
    events: list[Event] = []

    if not agent_online:
        recommendations.append(Recommendation(
            id="restore-agent",
            agent="operations",
            priority="critical",
            title="Восстановить связь с рестораном",
            reason="Агент Restaurant OS не подключён к Gateway.",
            action="Проверить службу агента и интернет-соединение.",
            expected_effect="Восстановление актуальной аналитики",
            confidence=100,
            evidence=["Статус агента: offline"],
        ))
        events.append(Event(
            level="critical",
            title="Агент не в сети",
            text="Система не получает свежие данные из TillyPad.",
            source="Операционный центр",
        ))

    if sync_age_minutes is not None and sync_age_minutes > 15:
        recommendations.append(Recommendation(
            id="refresh-data",
            agent="operations",
            priority="high",
            title="Проверить синхронизацию",
            reason=f"Последний облачный снимок получен {sync_age_minutes} минут назад.",
            action="Проверить журнал агента и подключение к SQL.",
            expected_effect="Актуальные показатели в реальном времени",
            confidence=95,
            evidence=[f"Возраст данных: {sync_age_minutes} мин."],
        ))

    if revenue_delta is not None:
        if revenue_delta < -10:
            recommendations.append(Recommendation(
                id="recover-sales",
                agent="manager",
                priority="critical",
                title="Разобрать падение выручки",
                reason=f"Выручка ниже прошлого периода на {abs(revenue_delta):.1f}%.",
                action="Проверить слабые часы, поток чеков и лидеров меню.",
                expected_effect="Снижение потерь и восстановление оборота",
                confidence=91,
                evidence=[f"Динамика выручки: {revenue_delta:+.1f}%"],
            ))
            events.append(Event(
                level="warning",
                title="Выручка снизилась",
                text=f"Падение к прошлому периоду: {abs(revenue_delta):.1f}%.",
                source="Финансовый директор",
            ))
        elif revenue_delta > 10:
            events.append(Event(
                level="positive",
                title="Выручка растёт",
                text=f"Рост к прошлому периоду: {revenue_delta:+.1f}%.",
                source="Финансовый директор",
            ))

    if average_check_delta is not None and average_check_delta < -5:
        recommendations.append(Recommendation(
            id="raise-average-check",
            agent="marketing",
            priority="high",
            title="Поднять средний чек",
            reason=f"Средний чек снизился на {abs(average_check_delta):.1f}%.",
            action="Подготовить комбо и усилить допродажи напитков и гарниров.",
            expected_effect="+5–10% к среднему чеку",
            confidence=87,
            evidence=[f"Динамика среднего чека: {average_check_delta:+.1f}%"],
        ))

    if menu_items:
        leader = menu_items[0]
        recommendations.append(Recommendation(
            id="protect-leader",
            agent="technology",
            priority="high",
            title=f"Не допускать стоп-листа: {leader['item_name']}",
            reason="Позиция является лидером по выручке.",
            action="Проверить остатки ключевых ингредиентов и заготовок.",
            expected_effect="Сохранение текущего оборота",
            confidence=93,
            evidence=[
                f"Доля в выручке: {float(leader.get('revenue_share') or 0):.1f}%",
                f"Продано: {float(leader.get('quantity') or 0):.0f} шт.",
            ],
        ))
        events.append(Event(
            level="info",
            title=f"Лидер меню: {leader['item_name']}",
            text=f"Выручка по позиции: {float(leader.get('revenue') or 0):.0f} ₽.",
            source="Цифровой технолог",
        ))

        weak = [item for item in menu_items if item.get("abc_class") == "C"]
        if weak:
            recommendations.append(Recommendation(
                id="review-class-c",
                agent="technology",
                priority="medium",
                title="Проверить позиции класса C",
                reason=f"Найдено {len(weak)} слабых позиций.",
                action="Рассмотреть акцию, изменение цены или вывод из меню.",
                expected_effect="Упрощение меню и снижение операционной нагрузки",
                confidence=82,
                evidence=[f"Позиций класса C: {len(weak)}"],
            ))

    if hourly:
        weakest = min(hourly, key=lambda row: float(row.get("revenue") or 0))
        weakest_revenue = float(weakest.get("revenue") or 0)
        if weakest_revenue >= 0:
            recommendations.append(Recommendation(
                id="fill-weak-hour",
                agent="marketing",
                priority="medium",
                title=f"Усилить продажи в {int(weakest.get('sale_hour') or 0):02d}:00",
                reason="Это один из самых слабых часов по выручке.",
                action="Запустить ограниченное по времени предложение.",
                expected_effect="Дополнительный поток в слабый период",
                confidence=76,
                evidence=[f"Выручка в слабый час: {weakest_revenue:.0f} ₽"],
            ))

    recommendations.sort(
        key=lambda item: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(item.priority, 9),
            -item.confidence,
        )
    )
    return recommendations, events
