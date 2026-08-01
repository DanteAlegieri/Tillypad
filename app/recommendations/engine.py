from typing import Any

from app.recommendations.models import Recommendation


class RecommendationEngine:
    PRIORITY_ORDER = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
    }

    def menu_recommendations(
        self,
        items: list[dict[str, Any]],
        date_from: Any,
        date_to: Any,
    ) -> list[Recommendation]:
        result: list[Recommendation] = []

        for item in items:
            matrix = item.get("matrix", "CZ")
            name = item.get("item_name") or "Позиция"
            score = int(item.get("index_score") or 0)
            share = float(item.get("revenue_share") or 0)
            quantity = float(item.get("quantity") or 0)
            route = (
                f'/menu/item/{item["item_id"]}'
                f'?date_from={date_from}&date_to={date_to}'
            )

            if matrix == "AX":
                result.append(Recommendation(
                    code=f'menu-stock-{item["item_id"]}',
                    source="Цифровой технолог",
                    title=f"Не допускать стоп-листа: {name}",
                    action="Обеспечить постоянное наличие ключевых ингредиентов.",
                    reason=(
                        f"Позиция относится к AX, индекс {score}/100 "
                        f"и даёт {share:.1f}% выручки меню."
                    ),
                    priority="high",
                    confidence=0.92,
                    expected_effect="Сохранение текущей выручки и доступности лидера.",
                    route=route,
                    entity_name=name,
                    metrics={"matrix": matrix, "score": score, "share": share},
                ))

            elif matrix in {"AY", "AZ"}:
                result.append(Recommendation(
                    code=f'menu-stabilize-{item["item_id"]}',
                    source="Цифровой технолог",
                    title=f"Стабилизировать спрос: {name}",
                    action="Проверить сезонность, стоп-листы и часы провалов.",
                    reason=(
                        f"Позиция даёт высокий вклад в выручку, "
                        f"но имеет класс {matrix}."
                    ),
                    priority="high",
                    confidence=0.84,
                    expected_effect="Снижение колебаний продаж.",
                    route=route,
                    entity_name=name,
                    metrics={"matrix": matrix, "score": score},
                ))

            elif matrix == "CX" and quantity >= 2:
                result.append(Recommendation(
                    code=f'menu-combo-{item["item_id"]}',
                    source="Цифровой технолог",
                    title=f"Добавить в комбо: {name}",
                    action="Проверить связки с лидерами и протестировать допродажу.",
                    reason=(
                        "Спрос устойчивый, но вклад в общую выручку низкий."
                    ),
                    priority="medium",
                    confidence=0.76,
                    expected_effect="Рост количества продаж позиции.",
                    route=route,
                    entity_name=name,
                    metrics={"matrix": matrix, "quantity": quantity},
                ))

            elif matrix in {"CY", "CZ"} and quantity <= 3:
                result.append(Recommendation(
                    code=f'menu-review-{item["item_id"]}',
                    source="Цифровой технолог",
                    title=f"Пересмотреть позицию: {name}",
                    action="Проверить цену, описание, подачу или исключение из меню.",
                    reason=(
                        f"За период продано {quantity:.0f} шт., "
                        f"класс {matrix}, индекс {score}/100."
                    ),
                    priority="medium",
                    confidence=0.86,
                    expected_effect="Сокращение слабых позиций меню.",
                    route=route,
                    entity_name=name,
                    metrics={"matrix": matrix, "score": score, "quantity": quantity},
                ))

        return result

    def sales_recommendations(
        self,
        sales: dict[str, Any],
    ) -> list[Recommendation]:
        comparison = sales.get("comparison", {})
        summary = sales.get("summary", {})
        result: list[Recommendation] = []

        revenue_change = comparison.get("revenue_change")
        checks_change = comparison.get("checks_change")
        avg_change = comparison.get("avg_check_change")

        if revenue_change is not None and revenue_change <= -10:
            cause = "снижение количества чеков"
            if (
                checks_change is not None
                and avg_change is not None
                and avg_change < checks_change
            ):
                cause = "снижение среднего чека"

            result.append(Recommendation(
                code="sales-decline",
                source="Цифровой управляющий",
                title="Разобрать снижение продаж",
                action="Проверить слабые часы, категории и позиции-антилидеры.",
                reason=(
                    f"Выручка снизилась на {abs(revenue_change):.1f}%. "
                    f"Вероятная основная причина — {cause}."
                ),
                priority="critical",
                confidence=0.91,
                expected_effect="Поиск причины потери выручки.",
                route="/sales",
                metrics={
                    "revenue_change": revenue_change,
                    "checks_change": checks_change,
                    "avg_check_change": avg_change,
                },
            ))

        if avg_change is not None and avg_change <= -5:
            result.append(Recommendation(
                code="sales-average-check",
                source="Цифровой маркетолог",
                title="Увеличить средний чек",
                action="Усилить допродажу напитков, картофеля, соусов и комбо.",
                reason=f"Средний чек снизился на {abs(avg_change):.1f}%.",
                priority="high",
                confidence=0.85,
                expected_effect="Рост среднего чека.",
                route="/marketing",
                metrics={"avg_check_change": avg_change},
            ))

        if int(summary.get("refunds_count") or 0) > 0:
            result.append(Recommendation(
                code="sales-refunds",
                source="Цифровой управляющий",
                title="Проверить возвраты",
                action="Открыть чеки возвратов и установить причины.",
                reason=(
                    f'Возвратов: {summary["refunds_count"]}, '
                    f'сумма: {summary["refunds_sum"]:.0f} ₽.'
                ),
                priority="high",
                confidence=0.99,
                expected_effect="Снижение повторных ошибок и потерь.",
                route="/sales",
            ))

        return result

    def marketing_recommendations(
        self,
        opportunities: list[dict[str, Any]],
    ) -> list[Recommendation]:
        result: list[Recommendation] = []

        for row in opportunities:
            base_name = row.get("base_item_name") or "Основная позиция"
            pair_name = row.get("pair_item_name") or "Дополнение"
            attach_rate = float(row.get("attach_rate") or 0)
            missing_checks = int(row.get("missing_checks") or 0)
            potential = float(row.get("estimated_potential") or 0)

            if missing_checks < 3 or potential <= 0:
                continue

            priority = "high" if potential >= 3000 else "medium"
            confidence = 0.78 if row.get("base_checks", 0) >= 20 else 0.64

            result.append(Recommendation(
                code=f'marketing-pair-{row["base_item_id"]}-{row["pair_item_id"]}',
                source="Цифровой маркетолог",
                title=f"Предлагать «{pair_name}» к «{base_name}»",
                action=(
                    "Добавить подсказку кассиру или протестировать комбо."
                ),
                reason=(
                    f"Связка встречается в {attach_rate:.1f}% чеков. "
                    f"Без дополнения осталось {missing_checks} чеков."
                ),
                priority=priority,
                confidence=confidence,
                expected_effect=(
                    f"Оценочный потенциал: до {potential:,.0f} ₽ "
                    f"за выбранный период."
                ).replace(",", " "),
                route="/marketing",
                entity_name=base_name,
                metrics={
                    "attach_rate": attach_rate,
                    "missing_checks": missing_checks,
                    "estimated_potential": potential,
                },
            ))

        return result

    def combine(
        self,
        *groups: list[Recommendation],
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        unique: dict[str, Recommendation] = {}

        for group in groups:
            for recommendation in group:
                current = unique.get(recommendation.code)
                if (
                    current is None
                    or recommendation.confidence > current.confidence
                ):
                    unique[recommendation.code] = recommendation

        ordered = sorted(
            unique.values(),
            key=lambda item: (
                self.PRIORITY_ORDER.get(item.priority, 99),
                -item.confidence,
            ),
        )
        return [item.to_dict() for item in ordered[:limit]]
