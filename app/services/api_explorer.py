import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.api_probe import ApiProbe
from app.services.sync_service import normalize_rows
from app.services.tillypad_client import TillypadClient, TillypadError


SAFE_TARGETS = [
    "SegmentInfo",
    "Divisions",
    "Menuitems",
    "MenuGroups",
    "MenuModifiers",
    "MenuItemStopList",
    "SalePrivileges",
    "Users",
    "Guests",
    "GuestDeliveries",
    "ClientPurseTypes",
    "PlaceGroups",
    "Places",
    "Clients910",
    "ClientAddresses",
    "ClientPurseOperations",
]


def make_preview(data: Any, limit: int = 6000) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... ответ обрезан ..."


class ApiExplorer:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.client = TillypadClient()

    def probe(
        self,
        target: str,
        body: Any | None = None,
        timeout: int = 15,
    ) -> ApiProbe:
        target = target.strip()

        try:
            response = self.client.get_response(
                target=target,
                body=body,
                timeout=timeout,
            )
            rows_count = len(normalize_rows(response.data))

            probe = ApiProbe(
                target=target,
                status="ok",
                http_status=response.http_status,
                duration_ms=response.duration_ms,
                rows_count=rows_count,
                response_type=response.response_type,
                response_preview=make_preview(response.data),
                error_text=None,
            )
        except TillypadError as exc:
            probe = ApiProbe(
                target=target,
                status="error",
                http_status=None,
                duration_ms=None,
                rows_count=0,
                response_type=None,
                response_preview=None,
                error_text=str(exc),
            )

        self.db.add(probe)
        self.db.commit()
        self.db.refresh(probe)
        return probe

    def probe_known_targets(self, timeout: int = 10) -> list[ApiProbe]:
        results: list[ApiProbe] = []

        for target in SAFE_TARGETS:
            # Guests без фильтра уже давал timeout, поэтому его не запускаем
            # без безопасного фильтра.
            if target == "Guests":
                probe = ApiProbe(
                    target=target,
                    status="skipped",
                    rows_count=0,
                    response_type=None,
                    response_preview=None,
                    error_text=(
                        "Пропущен автоматический запрос без фильтра: "
                        "на этой базе Guests уже завершался timeout."
                    ),
                )
                self.db.add(probe)
                self.db.commit()
                self.db.refresh(probe)
            else:
                probe = self.probe(target, timeout=timeout)

            results.append(probe)

        return results

    def list_recent(self, limit: int = 100) -> list[ApiProbe]:
        return self.db.execute(
            select(ApiProbe)
            .order_by(ApiProbe.id.desc())
            .limit(limit)
        ).scalars().all()

    def clear_history(self) -> None:
        self.db.execute(delete(ApiProbe))
        self.db.commit()
