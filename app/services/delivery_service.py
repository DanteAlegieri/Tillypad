from datetime import date, timedelta
import re
import xml.etree.ElementTree as ET
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

            for key in (
                "avg_total_minutes",
                "best_total_minutes",
                "worst_total_minutes",
                "avg_road_minutes",
            ):
                if row.get(key) is not None:
                    row[key] = float(row[key])

        for row in result["heatmap"]:
            if row.get("avg_minutes") is not None:
                row["avg_minutes"] = float(row["avg_minutes"])

        for row in result["longest_orders"]:
            row["courier_name"] = self._clean_tilly_text(
                row.get("courier_name")
            )
            row["method_name"] = self._clean_tilly_text(
                row.get("method_name")
            )

            stage_values = {
                "Ожидание кухни": float(
                    row.get("wait_kitchen_minutes") or 0
                ),
                "Приготовление": float(
                    row.get("cooking_minutes") or 0
                ),
                "Ожидание курьера": float(
                    row.get("wait_courier_minutes") or 0
                ),
                "В пути": float(
                    row.get("road_minutes") or 0
                ),
            }
            for key in (
                "wait_kitchen_minutes",
                "cooking_minutes",
                "wait_courier_minutes",
                "road_minutes",
            ):
                row[key] = float(row.get(key) or 0)

            row["bottleneck_name"], row["bottleneck_minutes"] = max(
                stage_values.items(),
                key=lambda item: item[1],
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
        previous_orders = int(previous_summary.get("total_orders") or 0)
        summary["orders_delta_percent"] = (
            round(
                float(summary["orders_delta"]) / previous_orders * 100,
                1,
            )
            if previous_orders and summary["orders_delta"] is not None
            else None
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
        result["process_flow"] = self._process_flow(result["stages"])
        result["daily_extremes"] = self._daily_extremes(result["daily"])
        result["heatmap_matrix"] = self._heatmap_matrix(result["heatmap"])
        result["insights"] = self._insights(
            result,
            previous_summary,
        )
        result["director_status"] = self._director_status(result)
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
    def _human_date(value: Any) -> str:
        if value is None:
            return "Нет данных"

        if isinstance(value, str):
            parsed = date.fromisoformat(value)
        else:
            parsed = value

        weekdays = (
            "понедельник", "вторник", "среда", "четверг",
            "пятница", "суббота", "воскресенье",
        )
        months = (
            "января", "февраля", "марта", "апреля",
            "мая", "июня", "июля", "августа",
            "сентября", "октября", "ноября", "декабря",
        )
        return (
            f"{parsed.day} {months[parsed.month - 1]} "
            f"({weekdays[parsed.weekday()]})"
        )

    @staticmethod
    def _process_flow(stages: dict[str, Any]) -> dict[str, Any]:
        items = [
            {
                "title": "Ожидание кухни",
                "value": float(
                    stages.get("avg_wait_kitchen_minutes") or 0
                ),
                "class": "wait",
            },
            {
                "title": "Приготовление",
                "value": float(
                    stages.get("avg_cooking_minutes") or 0
                ),
                "class": "cook",
            },
            {
                "title": "Ожидание курьера",
                "value": float(
                    stages.get("avg_wait_courier_minutes") or 0
                ),
                "class": "courier",
            },
            {
                "title": "В пути",
                "value": float(
                    stages.get("avg_road_minutes") or 0
                ),
                "class": "road",
            },
        ]
        total = sum(item["value"] for item in items)

        for item in items:
            item["share"] = (
                round(item["value"] / total * 100, 1)
                if total else 0
            )
            item["width"] = max(item["share"], 2) if item["value"] else 0

        return {
            "items": items,
            "total": round(total, 1),
        }

    @staticmethod
    def _director_status(result: dict[str, Any]) -> dict[str, Any]:
        summary = result["summary"]
        stages = result["stages"]

        on_time = float(summary.get("on_time_percent") or 0)
        avg_total = float(summary.get("avg_total_minutes") or 0)
        overdue = max(
            int(summary.get("measured_orders") or 0)
            - int(summary.get("on_time_orders") or 0),
            0,
        )

        stage_values = {
            "ожидание кухни": float(
                stages.get("avg_wait_kitchen_minutes") or 0
            ),
            "приготовление": float(
                stages.get("avg_cooking_minutes") or 0
            ),
            "ожидание курьера": float(
                stages.get("avg_wait_courier_minutes") or 0
            ),
            "время в пути": float(
                stages.get("avg_road_minutes") or 0
            ),
        }
        worst_stage, worst_value = max(
            stage_values.items(),
            key=lambda item: item[1],
        )

        if on_time >= 85 and avg_total <= 40:
            level = "good"
            title = "Период проходит стабильно"
        elif on_time >= 65 and avg_total <= 55:
            level = "warning"
            title = "Есть отклонения, но ситуация управляемая"
        else:
            level = "risk"
            title = "Требуется вмешательство управляющего"

        return {
            "level": level,
            "title": title,
            "score": round(on_time, 1),
            "bullets": [
                f"Вовремя выполнено {on_time:.1f}% заказов.",
                f"Среднее полное время — {avg_total:.1f} мин.",
                f"Просрочено {overdue} заказов.",
                (
                    f"Главный узкий этап — {worst_stage}: "
                    f"{worst_value:.1f} мин."
                ),
            ],
        }

    @staticmethod
    def _heatmap_matrix(
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        weekday_names = [
            "Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс",
        ]
        hours = list(range(10, 23))

        lookup = {
            (
                int(row.get("weekday_number") or 0),
                int(row.get("hour_number") or 0),
            ): row
            for row in rows
        }

        max_minutes = max(
            (
                float(row.get("avg_minutes") or 0)
                for row in rows
            ),
            default=1,
        )

        matrix = []
        for weekday_number, weekday_name in enumerate(weekday_names):
            cells = []
            for hour in hours:
                row = lookup.get((weekday_number, hour), {})
                avg_minutes = float(row.get("avg_minutes") or 0)
                intensity = (
                    round(avg_minutes / max_minutes * 100)
                    if max_minutes
                    else 0
                )
                cells.append(
                    {
                        "hour": hour,
                        "orders": int(row.get("orders_count") or 0),
                        "avg_minutes": avg_minutes,
                        "overdue": int(row.get("overdue_orders") or 0),
                        "intensity": intensity,
                    }
                )
            matrix.append(
                {
                    "weekday": weekday_name,
                    "cells": cells,
                }
            )

        return {
            "hours": hours,
            "rows": matrix,
        }

    @staticmethod
    def _insights(
        result: dict[str, Any],
        previous_summary: dict[str, Any],
    ) -> list[dict[str, str]]:
        summary = result["summary"]
        stages = result["stages"]
        insights: list[dict[str, str]] = []

        orders_delta = summary.get("orders_delta")
        if orders_delta is not None:
            previous_orders = int(previous_summary.get("total_orders") or 0)
            percent = (
                round(float(orders_delta) / previous_orders * 100, 1)
                if previous_orders
                else 0
            )
            insights.append(
                {
                    "level": "good" if orders_delta >= 0 else "risk",
                    "title": (
                        "Заказов стало больше"
                        if orders_delta >= 0
                        else "Заказов стало меньше"
                    ),
                    "text": (
                        f"{orders_delta:+.0f} заказов "
                        f"({percent:+.1f}%) к предыдущему периоду."
                    ),
                }
            )

        on_time_delta = summary.get("on_time_delta")
        if on_time_delta is not None:
            insights.append(
                {
                    "level": "good" if on_time_delta >= 0 else "risk",
                    "title": (
                        "Своевременность улучшилась"
                        if on_time_delta >= 0
                        else "Своевременность снизилась"
                    ),
                    "text": (
                        f"{on_time_delta:+.1f} п.п. "
                        "к предыдущему периоду."
                    ),
                }
            )

        total_delta = summary.get("avg_total_delta")
        if total_delta is not None:
            insights.append(
                {
                    "level": "good" if total_delta <= 0 else "risk",
                    "title": (
                        "Среднее время сократилось"
                        if total_delta <= 0
                        else "Среднее время выросло"
                    ),
                    "text": (
                        f"{total_delta:+.1f} мин "
                        "к предыдущему периоду."
                    ),
                }
            )

        stage_values = {
            "ожидание кухни": float(
                stages.get("avg_wait_kitchen_minutes") or 0
            ),
            "приготовление": float(
                stages.get("avg_cooking_minutes") or 0
            ),
            "ожидание курьера": float(
                stages.get("avg_wait_courier_minutes") or 0
            ),
            "время в пути": float(
                stages.get("avg_road_minutes") or 0
            ),
        }
        worst_stage, worst_value = max(
            stage_values.items(),
            key=lambda item: item[1],
        )
        insights.append(
            {
                "level": "warning",
                "title": "Главный узкий этап",
                "text": (
                    f"{worst_stage.capitalize()} — "
                    f"{worst_value:.1f} мин."
                ),
            }
        )

        return insights[:4]

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
                    DeliveryService._human_date(
                        extremes["worst"]["sale_date"]
                    )
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
                    DeliveryService._human_date(
                        extremes["best"]["sale_date"]
                    )
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

    @staticmethod
    def _clean_phone(value: Any) -> str:
        cleaned = DeliveryService._clean_tilly_text(value)
        if not cleaned:
            return ""

        cleaned = re.sub(r"[^\d+() -]", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        digits = re.sub(r"\D", "", cleaned)
        if len(digits) == 11 and digits[0] in {"7", "8"}:
            return (
                f"+7 ({digits[1:4]}) "
                f"{digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
            )
        if len(digits) == 10:
            return (
                f"+7 ({digits[0:3]}) "
                f"{digits[3:6]}-{digits[6:8]}-{digits[8:10]}"
            )
        return cleaned

    @staticmethod
    def _parse_delivery_address(value: Any) -> dict[str, str]:
        if value is None:
            raw = ""
        else:
            raw = str(value)
            raw = "".join(
                character
                for character in raw
                if ord(character) >= 32 and ord(character) != 127
            ).strip()

        result = {
            "full": "",
            "street": "",
            "house": "",
            "apartment": "",
            "entrance": "",
            "floor": "",
            "comment": "",
            "payment": "",
            "bonuses": "",
        }
        if not raw:
            return result

        xml_start = raw.find("<Address")
        xml_end = raw.rfind("</Address>")
        xml_text = (
            raw[xml_start:xml_end + len("</Address>")]
            if xml_start >= 0 and xml_end >= 0
            else raw
        )

        # Иногда TillyPad сохраняет XML с мусорным префиксом
        # или дополнительными байтами перед тегом Address.
        if "<Address" in xml_text:
            xml_text = xml_text[xml_text.find("<Address"):]

        try:
            root = ET.fromstring(xml_text)
            tag_map = {
                "Street": "street",
                "House": "house",
                "Apartment": "apartment",
                "Flat": "apartment",
                "Entrance": "entrance",
                "Floor": "floor",
                "Comment": "comment",
            }
            for element in root.iter():
                local_name = element.tag.split("}")[-1]
                key = tag_map.get(local_name)
                text = DeliveryService._clean_tilly_text(element.text)
                if key and text:
                    result[key] = text
        except ET.ParseError:
            for xml_tag, key in (
                ("Street", "street"),
                ("House", "house"),
                ("Apartment", "apartment"),
                ("Flat", "apartment"),
                ("Entrance", "entrance"),
                ("Floor", "floor"),
                ("Comment", "comment"),
            ):
                match = re.search(
                    rf"<{xml_tag}\b[^>]*>(.*?)</{xml_tag}>",
                    xml_text,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                if match:
                    result[key] = DeliveryService._clean_tilly_text(
                        match.group(1)
                    )

        comment = result["comment"]
        if comment:
            payment_match = re.search(
                r"(?:способ\s+оплаты|оплата)\s*:\s*([^|;\n]+)",
                comment,
                flags=re.IGNORECASE,
            )
            if payment_match:
                result["payment"] = payment_match.group(1).strip()

            bonus_match = re.search(
                r"бонус\w*\s*:\s*([+-]?\d+(?:[.,]\d+)?)",
                comment,
                flags=re.IGNORECASE,
            )
            if bonus_match:
                result["bonuses"] = bonus_match.group(1).replace(",", ".")

        address_parts = []
        if result["street"]:
            address_parts.append(result["street"])
        if result["house"]:
            address_parts.append(result["house"])
        if result["apartment"]:
            address_parts.append(f"кв. {result['apartment']}")

        result["full"] = ", ".join(address_parts)
        if not result["full"]:
            plain = re.sub(r"<[^>]+>", " ", raw)
            plain = re.sub(r"[^0-9A-Za-zА-Яа-яЁё.,/() -]", " ", plain)
            plain = re.sub(r"\s+", " ", plain).strip()

            meaningful_chars = re.sub(r"[^0-9A-Za-zА-Яа-яЁё]", "", plain)
            result["full"] = plain if len(meaningful_chars) >= 4 else ""

        return result

    @staticmethod
    def _order_analysis(order: dict[str, Any]) -> dict[str, Any]:
        total = float(order.get("total_minutes") or 0)
        is_takeaway = bool(order.get("is_takeaway"))
        bottleneck = order.get("bottleneck") or {
            "title": "Нет данных",
            "minutes": 0,
        }
        bottleneck_minutes = float(bottleneck.get("minutes") or 0)
        share = (
            round(bottleneck_minutes / total * 100, 1)
            if total > 0 else 0
        )

        title = bottleneck.get("title") or "Нет данных"
        checks: list[str] = []

        if title == "Ожидание кухни":
            conclusion = (
                "Основная задержка возникла до начала приготовления."
            )
            checks = [
                "Проверить, когда заказ был подтверждён сотрудником.",
                "Уточнить, почему кухня не начала готовить заказ вовремя.",
                "Проверить загрузку кухни и наличие сотрудников в этот период.",
            ]
        elif title == "Приготовление":
            conclusion = (
                "Основная задержка возникла непосредственно "
                "во время приготовления."
            )
            checks = [
                "Проверить состав и сложность заказа.",
                "Сравнить время приготовления этих позиций с нормативом.",
                "Проверить загрузку кухни и работу смены.",
            ]
        elif title == "Ожидание курьера":
            conclusion = (
                "Готовый заказ долго ожидал назначения или прибытия курьера."
            )
            checks = [
                "Проверить доступность курьеров в этот момент.",
                "Уточнить время назначения курьера.",
                "Сравнить количество заказов и курьеров в час задержки.",
            ]
        elif title == "В пути":
            if is_takeaway:
                conclusion = (
                    "Для самовывоза этап «В пути» не должен влиять "
                    "на длительность заказа."
                )
                checks = [
                    "Проверить корректность статусов самовывоза.",
                    "Убедиться, что заказ закрывается после выдачи клиенту.",
                ]
            else:
                conclusion = (
                    "Основная задержка возникла после передачи заказа курьеру."
                )
                checks = [
                    "Проверить корректность времени перевода в статус «В пути».",
                    "Уточнить маршрут, адрес и фактическое время доставки.",
                    "Проверить, не забыли ли своевременно закрыть заказ.",
                ]
        else:
            conclusion = "Недостаточно данных для точного вывода."
            checks = ["Проверить последовательность статусов заказа."]

        if share >= 80:
            confidence = "Высокая"
        elif share >= 55:
            confidence = "Средняя"
        else:
            confidence = "Низкая"

        norm_minutes = float(
            order.get("cooking_norm_minutes") or 0
        ) + float(order.get("delivery_norm_minutes") or 0)

        return {
            "title": title,
            "minutes": round(bottleneck_minutes, 1),
            "share": share,
            "confidence": confidence,
            "conclusion": conclusion,
            "checks": checks,
            "norm_minutes": round(norm_minutes, 1),
            "over_norm_minutes": round(max(total - norm_minutes, 0), 1),
            "norm_percent": (
                round(total / norm_minutes * 100, 1)
                if norm_minutes > 0 else None
            ),
        }

    def load_orders(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
        courier_name: str = "",
        stage: str = "",
        weekday_number: int | None = None,
        hour_number: int | None = None,
        only_overdue: bool = False,
    ) -> dict[str, Any]:
        today = date.today()
        date_to = date_to or today
        date_from = date_from or (date_to - timedelta(days=29))

        if date_from > date_to:
            date_from, date_to = date_to, date_from

        rows = self.repository.load_orders(
            date_from=date_from,
            date_to=date_to,
            courier_name=courier_name,
            stage=stage,
            weekday_number=weekday_number,
            hour_number=hour_number,
            only_overdue=only_overdue,
        )

        for row in rows:
            row["courier_name"] = self._clean_tilly_text(
                row.get("courier_name")
            )
            row["state_name"] = self._clean_tilly_text(
                row.get("state_name")
            )
            row["method_name"] = self._clean_tilly_text(
                row.get("method_name")
            )

            stage_values = {
                "Ожидание кухни": float(
                    row.get("wait_kitchen_minutes") or 0
                ),
                "Приготовление": float(
                    row.get("cooking_minutes") or 0
                ),
                "Ожидание курьера": float(
                    row.get("wait_courier_minutes") or 0
                ),
                "В пути": float(
                    row.get("road_minutes") or 0
                ),
            }
            for key in (
                "wait_kitchen_minutes",
                "cooking_minutes",
                "wait_courier_minutes",
                "road_minutes",
            ):
                row[key] = float(row.get(key) or 0)

            row["bottleneck_name"], row["bottleneck_minutes"] = max(
                stage_values.items(),
                key=lambda item: item[1],
            )

        return {
            "orders": rows,
            "date_from": date_from,
            "date_to": date_to,
            "courier_name": courier_name,
            "stage": stage,
            "weekday_number": weekday_number,
            "hour_number": hour_number,
            "only_overdue": only_overdue,
            "count": len(rows),
        }

    def load_order_detail(
        self,
        delivery_id: str,
    ) -> dict[str, Any] | None:
        order = self.repository.load_order_detail(delivery_id)
        if order is None:
            return None

        for key in (
            "courier_name",
            "state_name",
            "method_name",
            "client_name",
            "client_phone",
            "courier_comment",
            "extra_info",
        ):
            order[key] = self._clean_tilly_text(order.get(key))

        order["client_phone"] = self._clean_phone(
            order.get("client_phone")
        )
        order["address"] = self._parse_delivery_address(
            order.get("client_address")
        )
        method_name = (order.get("method_name") or "").lower()
        order["is_takeaway"] = (
            "самовывоз" in method_name
            or int(order.get("state_id") or -1) == 1
            and not order.get("client_address")
            and not order.get("courier_name")
        )
        if order["is_takeaway"]:
            order["courier_name"] = "Самовывоз"
            order["address"] = {
                "full": "",
                "street": "",
                "house": "",
                "apartment": "",
                "entrance": "",
                "floor": "",
                "comment": "",
                "payment": "",
                "bonuses": "",
            }

        for row in order["timeline"]:
            row["state_name"] = self._clean_tilly_text(
                row.get("state_name")
            )
            row["changed_by"] = self._clean_tilly_text(
                row.get("changed_by")
            )
            row["stage_minutes"] = float(
                row.get("stage_minutes") or 0
            )

        for item in order["items"]:
            item_name = self._clean_tilly_text(item.get("item_name"))
            item["item_name"] = (
                item_name.strip()
                if item_name and item_name.strip()
                else "Позиция без названия"
            )
            item["item_sum"] = float(item.get("item_sum") or 0)

        stage_labels = {
            3: "Ожидание кухни",
            5: "Приготовление",
            6: "Ожидание курьера",
            7: "В пути",
        }
        stage_totals = {
            "Ожидание кухни": 0.0,
            "Приготовление": 0.0,
            "Ожидание курьера": 0.0,
            "В пути": 0.0,
        }

        for row in order["timeline"]:
            label = stage_labels.get(int(row.get("state_id") or -1))
            if label:
                stage_totals[label] += row["stage_minutes"]

        order["stage_totals"] = [
            {
                "title": title,
                "minutes": round(minutes, 1),
            }
            for title, minutes in stage_totals.items()
        ]
        order["bottleneck"] = max(
            order["stage_totals"],
            key=lambda item: item["minutes"],
        )
        order["items_total"] = round(
            sum(float(item["item_sum"]) for item in order["items"]),
            2,
        )
        order["analysis"] = self._order_analysis(order)
        return order

