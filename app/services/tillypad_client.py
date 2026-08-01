import json
import time
from dataclasses import dataclass
from typing import Any

import requests
from loguru import logger

from app.core.config import get_settings


class TillypadError(RuntimeError):
    pass


@dataclass
class TillypadResponse:
    data: Any
    http_status: int
    duration_ms: int
    response_type: str


class TillypadClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def get_response(
        self,
        target: str,
        body: Any | None = None,
        timeout: int | None = None,
    ) -> TillypadResponse:
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

        effective_timeout = timeout or self.settings.tillypad_timeout
        started = time.perf_counter()

        logger.info("Tillypad GET target={}", target)

        try:
            response = requests.get(
                self.settings.tillypad_api_url,
                headers=headers,
                params=params,
                timeout=effective_timeout,
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            response.raise_for_status()
        except requests.Timeout as exc:
            raise TillypadError(
                f"Tillypad не ответил за {effective_timeout} секунд."
            ) from exc
        except requests.RequestException as exc:
            details = ""
            if exc.response is not None:
                details = exc.response.text[:1000]
            raise TillypadError(
                f"Ошибка запроса Tillypad: {exc}. {details}"
            ) from exc

        try:
            data = response.json()
            response_type = type(data).__name__
        except ValueError as exc:
            raise TillypadError(
                f"Tillypad вернул не JSON: {response.text[:1000]}"
            ) from exc

        return TillypadResponse(
            data=data,
            http_status=response.status_code,
            duration_ms=duration_ms,
            response_type=response_type,
        )

    def get(
        self,
        target: str,
        body: Any | None = None,
        timeout: int | None = None,
    ) -> Any:
        return self.get_response(
            target=target,
            body=body,
            timeout=timeout,
        ).data
