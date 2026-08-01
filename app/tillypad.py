import json
from typing import Any
import requests

from .config import settings


class TillypadError(RuntimeError):
    pass


def get_target(target: str, body: Any | None = None) -> Any:
    if not settings.token:
        raise TillypadError(
            "В .env не указан TILLYPAD_TOKEN."
        )

    headers = {
        "Content-Type": "application/json",
        "Authorization": settings.token,
        "Target": target,
    }

    params = {}
    if body is not None:
        params["body"] = json.dumps(body, ensure_ascii=False)

    try:
        response = requests.get(
            settings.api_url,
            headers=headers,
            params=params,
            timeout=settings.timeout,
        )
        response.raise_for_status()
    except requests.Timeout as exc:
        raise TillypadError(
            f"Tillypad не ответил за {settings.timeout} секунд. "
            "Попробуйте применить более узкий фильтр."
        ) from exc
    except requests.RequestException as exc:
        text = ""
        if getattr(exc, "response", None) is not None:
            text = exc.response.text[:1000]
        raise TillypadError(f"Ошибка запроса Tillypad: {exc}. {text}") from exc

    try:
        return response.json()
    except ValueError as exc:
        raise TillypadError(
            f"Tillypad вернул не JSON: {response.text[:1000]}"
        ) from exc
