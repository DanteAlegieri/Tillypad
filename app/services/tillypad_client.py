import json
from typing import Any

import requests
from loguru import logger

from app.core.config import get_settings


class TillypadError(RuntimeError):
    pass


class TillypadClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def get(self, target: str, body: Any | None = None) -> Any:
        if not self.settings.tillypad_token.strip():
            raise TillypadError(
                "В файле .env не указан TILLYPAD_TOKEN."
            )

        headers = {
            "Content-Type": "application/json",
            "Authorization": self.settings.tillypad_token,
            "Target": target,
        }

        params: dict[str, str] = {}
        if body is not None:
            params["body"] = json.dumps(body, ensure_ascii=False)

        logger.info("Tillypad GET target={}", target)

        try:
            response = requests.get(
                self.settings.tillypad_api_url,
                headers=headers,
                params=params,
                timeout=self.settings.tillypad_timeout,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise TillypadError(
                f"Tillypad не ответил за "
                f"{self.settings.tillypad_timeout} секунд. "
                "Нужен более узкий фильтр."
            ) from exc
        except requests.RequestException as exc:
            details = ""
            if exc.response is not None:
                details = exc.response.text[:1000]
            raise TillypadError(
                f"Ошибка запроса Tillypad: {exc}. {details}"
            ) from exc

        try:
            return response.json()
        except ValueError as exc:
            raise TillypadError(
                f"Tillypad вернул не JSON: {response.text[:1000]}"
            ) from exc
