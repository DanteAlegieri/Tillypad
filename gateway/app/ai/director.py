from __future__ import annotations

from typing import Any

from .recommendation_engine import build_recommendations
from .scoring import calculate_health


def _sum(items: list[dict[str, Any]], key: str) -> float:
    return sum(float(item.get(key) or 0) for item in items)


def _briefing(
    *,
    name: str,
    health: dict[str, Any],
    revenue: float,
    checks: int,
    average_check: float,
    menu_items: list[dict[str, Any]],
    recommendation_count: int,
) -> str:
    status_text = {
        "excellent": "находится в отличном состоянии",
        "good": "работает стабильно",
        "attention": "требует внимания",
        "critical": "находится в критическом состоянии",
    }[health["status"]]

    leader_text = ""
    if menu_items:
        leader = menu_items[0]
        leader_text = (
            f" Лидер продаж — «{leader['item_name']}», "
            f"его доля в выручке составляет "
            f"{float(leader.get('revenue_share') or 0):.1f}%."
        )

    return (
        f"Добрый день, {name}. Ресторан {status_text}: "
        f"{health['score']}/100. За выбранный период выручка составила "
        f"{revenue:,.0f} ₽, количество чеков — {checks}, "
        f"средний чек — {average_check:,.0f} ₽."
        f"{leader_text} "
        f"Система подготовила {recommendation_count} рекомендаций."
    ).replace(",", " ")


def build_director_report(
    *,
    owner_name: str,
    history: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    latest: dict[str, Any] | None,
    menu_items: list[dict[str, Any]],
    agent_info: dict[str, Any],
    sync_age_minutes: int | None,
) -> dict[str, Any]:
    revenue = _sum(history, "revenue")
    checks = int(_sum(history, "checks_count"))
    average_check = revenue / checks if checks else 0

    previous_revenue = _sum(previous, "revenue")
    previous_checks = int(_sum(previous, "checks_count"))
    previous_average_check = (
        previous_revenue / previous_checks
        if previous_checks
        else 0
    )

    hourly = []
    if latest:
        block = latest.get("hourly") or {}
        columns = block.get("columns") or []
        for row in block.get("rows") or []:
            hourly.append(dict(zip(columns, row)))

    health = calculate_health(
        revenue=revenue,
        previous_revenue=previous_revenue,
        average_check=average_check,
        previous_average_check=previous_average_check,
        agent_online=bool(agent_info.get("online")),
        sync_age_minutes=sync_age_minutes,
        menu_items=menu_items,
        hourly=hourly,
    )

    recommendations, events = build_recommendations(
        revenue_delta=health["revenue_delta"],
        average_check_delta=health["average_check_delta"],
        menu_items=menu_items,
        hourly=hourly,
        agent_online=bool(agent_info.get("online")),
        sync_age_minutes=sync_age_minutes,
    )

    return {
        "health": health,
        "briefing": _briefing(
            name=owner_name,
            health=health,
            revenue=revenue,
            checks=checks,
            average_check=average_check,
            menu_items=menu_items,
            recommendation_count=len(recommendations),
        ),
        "metrics": {
            "revenue": revenue,
            "checks": checks,
            "average_check": average_check,
        },
        "recommendations": [
            item.to_dict()
            for item in recommendations
        ],
        "events": [
            item.to_dict()
            for item in events
        ],
    }
