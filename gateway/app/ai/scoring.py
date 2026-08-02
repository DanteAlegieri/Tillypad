from __future__ import annotations

from typing import Any

from .models import ScoreFactor


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def _metric_delta(current: float, previous: float) -> float | None:
    if previous == 0:
        return 0.0 if current == 0 else None
    return (current - previous) / previous * 100


def calculate_health(
    *,
    revenue: float,
    previous_revenue: float,
    average_check: float,
    previous_average_check: float,
    agent_online: bool,
    sync_age_minutes: int | None,
    menu_items: list[dict[str, Any]],
    hourly: list[dict[str, Any]],
) -> dict[str, Any]:
    factors: list[ScoreFactor] = []

    revenue_delta = _metric_delta(revenue, previous_revenue)
    revenue_score = 65 if revenue_delta is None else clamp(70 + revenue_delta * 1.5)
    factors.append(ScoreFactor(
        key="revenue",
        title="Динамика выручки",
        weight=25,
        score=revenue_score,
        explanation=(
            "Недостаточно истории для сравнения"
            if revenue_delta is None
            else f"Изменение к прошлому периоду: {revenue_delta:+.1f}%"
        ),
    ))

    avg_delta = _metric_delta(average_check, previous_average_check)
    avg_score = 65 if avg_delta is None else clamp(70 + avg_delta * 2)
    factors.append(ScoreFactor(
        key="average_check",
        title="Средний чек",
        weight=20,
        score=avg_score,
        explanation=(
            "Недостаточно истории для сравнения"
            if avg_delta is None
            else f"Изменение к прошлому периоду: {avg_delta:+.1f}%"
        ),
    ))

    factors.append(ScoreFactor(
        key="agent",
        title="Связь с рестораном",
        weight=15,
        score=100 if agent_online else 0,
        explanation="Агент подключён" if agent_online else "Агент не в сети",
    ))

    if sync_age_minutes is None:
        sync_score = 20
        sync_explanation = "Нет данных о последней синхронизации"
    elif sync_age_minutes <= 5:
        sync_score = 100
        sync_explanation = f"Обновлено {sync_age_minutes} мин. назад"
    elif sync_age_minutes <= 15:
        sync_score = 75
        sync_explanation = f"Обновлено {sync_age_minutes} мин. назад"
    elif sync_age_minutes <= 60:
        sync_score = 45
        sync_explanation = f"Данные устаревают: {sync_age_minutes} мин."
    else:
        sync_score = 10
        sync_explanation = f"Данные устарели: {sync_age_minutes} мин."
    factors.append(ScoreFactor(
        key="sync",
        title="Свежесть данных",
        weight=15,
        score=sync_score,
        explanation=sync_explanation,
    ))

    class_c = sum(1 for item in menu_items if item.get("abc_class") == "C")
    menu_score = clamp(100 - class_c * 4)
    factors.append(ScoreFactor(
        key="menu",
        title="Структура меню",
        weight=15,
        score=menu_score,
        explanation=(
            f"Позиций класса C: {class_c}"
            if menu_items
            else "Данные по меню ещё не получены"
        ),
    ))

    if hourly:
        values = [float(row.get("revenue") or 0) for row in hourly]
        nonzero = [value for value in values if value > 0]
        if len(nonzero) >= 2:
            peak = max(nonzero)
            average = sum(nonzero) / len(nonzero)
            load_score = clamp(100 - max(0, (peak / average - 2)) * 25)
            load_explanation = f"Пиковая нагрузка выше средней в {peak / average:.1f} раза"
        else:
            load_score = 60
            load_explanation = "Недостаточно почасовых данных"
    else:
        load_score = 50
        load_explanation = "Нет почасовых данных"
    factors.append(ScoreFactor(
        key="load",
        title="Равномерность нагрузки",
        weight=10,
        score=load_score,
        explanation=load_explanation,
    ))

    total_weight = sum(f.weight for f in factors)
    total = round(
        sum(f.score * f.weight for f in factors) / total_weight
    )

    return {
        "score": int(clamp(total)),
        "status": (
            "excellent" if total >= 85
            else "good" if total >= 70
            else "attention" if total >= 50
            else "critical"
        ),
        "factors": [f.to_dict() for f in factors],
        "revenue_delta": revenue_delta,
        "average_check_delta": avg_delta,
    }
