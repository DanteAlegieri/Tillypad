from datetime import date, timedelta
import re
from typing import Any

from app.db.sql_server import SqlServer
from app.repositories.delivery_repository import DeliveryRepository


class DeliveryService:
    def __init__(self) -> None:
        self.repository = DeliveryRepository(SqlServer())

    @staticmethod
    def _clean_tilly_text(value: Any) -> str:
        """
        Убирает управляющие байты из мультиязычных строк TillyPad
        и оставляет русское название, если оно присутствует.
        """
        if value is None:
            return ""

        text = str(value)

        text = "".join(
            character
            for character in text
            if ord(character) >= 32 and ord(character) != 127
        ).strip()

        has_cyrillic = bool(re.search(r"[А-Яа-яЁё]", text))
        latin_match = re.search(r"[A-Za-z]", text)

        if has_cyrillic and latin_match:
            text = text[:latin_match.start()].strip()

        return text.strip(' "\'').strip()

    def load(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, Any]:
        today = date.today()
        date_to = date_to or today
        date_from = date_from or (date_to - timedelta(days=29))

        if date_from > date_to:
            date_from, date_to = date_to, date_from

        period_days = (date_to - date_from).days + 1
        previous_to = date_from - timedelta(days=1)
        previous_from = previous_to - timedelta(days=period_days - 1)

        result = self.repository.load(date_from, date_to)
        previous_summary = self.repository.load_summary(
            previous_from,
            previous_to,
        )

        for row in result["couriers"]:
            row["courier_name"] = self._clean_tilly_text(
                row.get("courier_name")
            )

        for row in result["active"]:
            row["courier_name"] = self._clean_tilly_text(
                row.get("courier_name")
            )
            row["method_name"] = self._clean_tilly_text(
                row.get("method_name")
            )
            row["state_name"] = self._clean_tilly_text(
                row.get("state_name")
            )

        for row in result["states"]:
            row["state_name"] = self._clean_tilly_text(
                row.get("state_name")
            )

        if result.get("latest_completed"):
            result["latest_completed"]["courier_name"] = (
                self._clean_tilly_text(
                    result["latest_completed"].get("courier_name")
                )
            )
            result["latest_completed"]["method_name"] = (
                self._clean_tilly_text(
                    result["latest_completed"].get("method_name")
                )
            )

        summary = result["summary"]

        measured = int(summary.get("measured_orders") or 0)
        on_time = int(summary.get("on_time_orders") or 0)
        summary["on_time_percent"] = round(
            100 * on_time / measured, 1
        ) if measured else 0

        total = int(summary.get("total_orders") or 0)
        courier = int(summary.get("courier_orders") or 0)
        pickup = int(summary.get("pickup_orders") or 0)
        summary["courier_percent"] = round(100 * courier / total, 1) if total else 0
        summary["pickup_percent"] = round(100 * pickup / total, 1) if total else 0

        for row in result["couriers"]:
            count = int(row.get("orders_count") or 0)
            timely = int(row.get("on_time_orders") or 0)
            row["on_time_percent"] = round(
                100 * timely / count, 1
            ) if count else 0

            if row.get("avg_total_minutes") is not None:
                row["avg_total_minutes"] = float(
                    row["avg_total_minutes"]
                )
            if row.get("avg_road_minutes") is not None:
                row["avg_road_minutes"] = float(
                    row["avg_road_minutes"]
                )

        # Значения AVG из SQL Server приходят как Decimal.
        # Перед передачей в JavaScript их нужно привести к float.
        for row in result["daily"]:
            # SQL Server возвращает CAST(... AS date) как datetime.date.
            # Перед передачей в Jinja/JavaScript преобразуем дату в ISO-строку.
            if row.get("sale_date") is not None:
                row["sale_date"] = row["sale_date"].isoformat()

            if row.get("avg_minutes") is not None:
                row["avg_minutes"] = float(row["avg_minutes"])

            measured = int(row.get("measured_orders") or 0)
            timely = int(row.get("on_time_orders") or 0)
            row["on_time_percent"] = round(
                100 * timely / measured,
                1,
            ) if measured else 0

        for key in (
            "avg_total_minutes",
        ):
            if summary.get(key) is not None:
                summary[key] = float(summary[key])

        for key in (
            "avg_wait_kitchen_minutes",
            "avg_cooking_minutes",
            "avg_wait_courier_minutes",
            "avg_road_minutes",
        ):
            if result["stages"].get(key) is not None:
                result["stages"][key] = float(
                    result["stages"][key]
                )

        for key in (
            "avg_total_minutes",
            "max_total_minutes",
        ):
            if previous_summary.get(key) is not None:
                previous_summary[key] = float(previous_summary[key])

        previous_measured = int(previous_summary.get("measured_orders") or 0)
        previous_on_time = int(previous_summary.get("on_time_orders") or 0)
        previous_summary["on_time_percent"] = round(
            100 * previous_on_time / previous_measured, 1
        ) if previous_measured else 0

        summary["avg_total_delta"] = self._delta(
            summary.get("avg_total_minutes"),
            previous_summary.get("avg_total_minutes"),
        )
        summary["on_time_delta"] = self._delta(
            summary.get("on_time_percent"),
            previous_summary.get("on_time_percent"),
        )
        summary["orders_delta"] = self._delta(
            summary.get("total_orders"),
            previous_summary.get("total_orders"),
        )

        for row in result["couriers"]:
            score = float(row.get("on_time_percent") or 0)
            if score >= 85:
                row["rating"] = "Отлично"
                row["rating_class"] = "rate-good"
            elif score >= 70:
                row["rating"] = "Хорошо"
                row["rating_class"] = "rate-warning"
            elif score >= 50:
                row["rating"] = "Ниже нормы"
                row["rating_class"] = "rate-risk"
            else:
                row["rating"] = "Плохо"
                row["rating_class"] = "rate-risk"

        result["previous_summary"] = previous_summary
        result["previous_from"] = previous_from
        result["previous_to"] = previous_to
        result["date_from"] = date_from
        result["date_to"] = date_to
        result["period_label"] = self._period_label(date_from, date_to)
        result["stage_cards"] = self._stage_cards(result["stages"])
        result["daily_extremes"] = self._daily_extremes(result["daily"])
        result["recommendation"] = self._recommendation(result)
        result["problems"] = self._problems(result)
        return result

    @staticmethod
    def _period_label(date_from: date, date_to: date) -> str:
        month_names = (
            "января", "февраля", "марта", "апреля",
            "мая", "июня", "июля", "августа",
            "сентября", "октября", "ноября", "декабря",
        )

        if date_from == date_to:
            return (
                f"{date_from.day} "
                f"{month_names[date_from.month - 1]} "
                f"{date_from.year}"
            )

        if (
            date_from.day == 1
            and date_from.year == date_to.year
            and date_from.month == date_to.month
        ):
            next_month = (
                date_to.replace(day=28) + timedelta(days=4)
            ).replace(day=1)
            month_end = next_month - timedelta(days=1)
            if date_to == month_end:
                return (
                    f"{month_names[date_from.month - 1].capitalize()} "
                    f"{date_from.year}"
                )

        return (
            f"{date_from.strftime('%d.%m.%Y')} — "
            f"{date_to.strftime('%d.%m.%Y')}"
        )

    @staticmethod
    def _stage_cards(stages: dict[str, Any]) -> list[dict[str, Any]]:
        definitions = [
            (
                "Ожидание кухни",
                "avg_wait_kitchen_minutes",
                5.0,
            ),
            (
                "Приготовление",
                "avg_cooking_minutes",
                20.0,
            ),
            (
                "Ожидание курьера",
                "avg_wait_courier_minutes",
                5.0,
            ),
            (
                "Время в пути",
                "avg_road_minutes",
                15.0,
            ),
        ]

        result = []
        for title, key, norm in definitions:
            value = float(stages.get(key) or 0)
            ratio = value / norm if norm else 0

            if ratio <= 1:
                level = "good"
                label = "В норме"
            elif ratio <= 1.35:
                level = "warning"
                label = "Выше нормы"
            else:
                level = "risk"
                label = "Критично"

            result.append(
                {
                    "title": title,
                    "value": value,
                    "norm": norm,
                    "level": level,
                    "label": label,
                    "bar_percent": min(ratio * 100, 100),
                    "delta_to_norm": round(value - norm, 1),
                }
            )

        return result

    @staticmethod
    def _daily_extremes(
        daily: list[dict[str, Any]],
    ) -> dict[str, Any]:
        measured = [
            row for row in daily
            if row.get("avg_minutes") is not None
        ]
        if not measured:
            return {
                "best": None,
                "worst": None,
                "fastest": None,
            }

        return {
            "best": min(
                measured,
                key=lambda row: float(row["avg_minutes"]),
            ),
            "worst": max(
                measured,
                key=lambda row: float(row["avg_minutes"]),
            ),
            "fastest": min(
                measured,
                key=lambda row: float(row["avg_minutes"]),
            ),
        }

    @staticmethod
    def _delta(current: Any, previous: Any) -> float | None:
        if current is None or previous is None:
            return None
        return round(float(current) - float(previous), 1)

    @staticmethod
    def _problems(result: dict[str, Any]) -> list[dict[str, Any]]:
        summary = result["summary"]
        extremes = result["daily_extremes"]
        latest = result.get("latest_completed")

        return [
            {
                "title": "Просроченных заказов",
                "value": max(
                    int(summary.get("measured_orders") or 0)
                    - int(summary.get("on_time_orders") or 0),
                    0,
                ),
                "note": "за выбранный период",
            },
            {
                "title": "Самый долгий день",
                "value": (
                    extremes["worst"]["sale_date"]
                    if extremes["worst"]
                    else "Нет данных"
                ),
                "note": (
                    f'{float(extremes["worst"]["avg_minutes"]):.1f} мин'
                    if extremes["worst"]
                    else ""
                ),
            },
            {
                "title": "Лучший день",
                "value": (
                    extremes["best"]["sale_date"]
                    if extremes["best"]
                    else "Нет данных"
                ),
                "note": (
                    f'{float(extremes["best"]["avg_minutes"]):.1f} мин'
                    if extremes["best"]
                    else ""
                ),
            },
            {
                "title": "Последний закрытый заказ",
                "value": (
                    f'{int(latest["total_minutes"])} мин'
                    if latest
                    else "Нет данных"
                ),
                "note": (
                    latest["method_name"]
                    if latest
                    else ""
                ),
            },
        ]

    @staticmethod
    def _recommendation(result: dict[str, Any]) -> dict[str, str]:
        summary = result["summary"]
        stages = result["stages"]

        on_time = float(summary.get("on_time_percent") or 0)
        stage_values = {
            "ожидание кухни": float(stages.get("avg_wait_kitchen_minutes") or 0),
            "приготовление": float(stages.get("avg_cooking_minutes") or 0),
            "ожидание курьера": float(stages.get("avg_wait_courier_minutes") or 0),
            "время в пути": float(stages.get("avg_road_minutes") or 0),
        }
        worst_stage, worst_value = max(
            stage_values.items(),
            key=lambda item: item[1],
        )

        if on_time >= 85:
            return {
                "level": "good",
                "title": "Доставка работает стабильно",
                "text": (
                    f"В норматив укладывается {on_time:.1f}% заказов. "
                    f"Самый длительный этап — {worst_stage}: {worst_value:.1f} мин."
                ),
            }
        if on_time >= 65:
            return {
                "level": "warning",
                "title": f"Основная задержка — {worst_stage}",
                "text": (
                    f"Вовремя выполнено {on_time:.1f}% заказов. "
                    f"Сфокусируйтесь на этапе «{worst_stage}»."
                ),
            }
        return {
            "level": "risk",
            "title": "Слишком много заказов выходят за норматив",
            "text": (
                f"Вовремя выполнено только {on_time:.1f}%. "
                f"Главный узкий этап — {worst_stage}: {worst_value:.1f} мин."
            ),
        }
