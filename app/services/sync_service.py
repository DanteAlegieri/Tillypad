import json
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from app.models.division import Division
from app.models.guest import Guest
from app.models.sync_log import SyncLog
from app.services.tillypad_client import TillypadClient


def normalize_rows(data: Any) -> list[dict]:
    if data is None:
        return []
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


class SyncService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.client = TillypadClient()

    def log(
        self,
        target: str,
        status: str,
        message: str,
        rows_count: int = 0,
    ) -> None:
        self.db.add(
            SyncLog(
                target=target,
                status=status,
                message=message,
                rows_count=rows_count,
            )
        )
        self.db.commit()

    def test_connection(self) -> int:
        data = self.client.get("SegmentInfo")
        rows = normalize_rows(data)
        self.log(
            "SegmentInfo",
            "ok",
            "Подключение успешно",
            len(rows),
        )
        return len(rows)

    def sync_divisions(self) -> int:
        rows = normalize_rows(self.client.get("Divisions"))

        for row in rows:
            dvsn_id = row.get("dvsn_ID") or row.get("dvsn_id")
            if not dvsn_id:
                continue

            model = self.db.get(Division, str(dvsn_id))
            if model is None:
                model = Division(
                    dvsn_id=str(dvsn_id),
                    name="",
                    raw_json="{}",
                )
                self.db.add(model)

            model.name = str(
                row.get("dvsn_Name")
                or row.get("dvsn_name")
                or ""
            )
            model.purse_id = (
                row.get("dvsn_mitm_ID_Purse")
                or row.get("mitm_ID_Purse")
            )
            model.raw_json = json.dumps(
                row,
                ensure_ascii=False,
            )

        self.db.commit()
        self.log(
            "Divisions",
            "ok",
            "Подразделения обновлены",
            len(rows),
        )
        return len(rows)

    def sync_guests(self, body: Any | None = None) -> int:
        rows = normalize_rows(self.client.get("Guests", body))

        for row in rows:
            gest_id = row.get("gest_ID") or row.get("gest_id")
            if not gest_id:
                continue

            model = self.db.get(Guest, str(gest_id))
            if model is None:
                model = Guest(
                    gest_id=str(gest_id),
                    raw_json="{}",
                )
                self.db.add(model)

            model.division_id = (
                row.get("gest_dvsn_ID")
                or row.get("gest_dvsn_id")
            )
            model.name = row.get("gest_Name") or row.get("gest_name")
            model.state_id = row.get("gest_gsst_ID")
            model.state = row.get("gest_state")
            model.date_open = row.get("gest_DateOpen")
            model.date_close = row.get("gest_DateClose")
            model.client_name = row.get("gest_ClientName")
            model.client_phone = str(
                row.get("gest_ClientPhone") or ""
            )
            model.order_sum = as_float(row.get("gest_OrderSum"))
            model.pay_sum = as_float(row.get("gest_PaySum"))
            model.raw_json = json.dumps(
                row,
                ensure_ascii=False,
            )

        self.db.commit()
        self.log(
            "Guests",
            "ok",
            "Гостевые счета обновлены",
            len(rows),
        )
        logger.info("Guests synced: {}", len(rows))
        return len(rows)
