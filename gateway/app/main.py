from __future__ import annotations

import logging

from fastapi.staticfiles import StaticFiles
from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field

from .config import settings
from .connections import ConnectionManager
from .protocol import GatewayMessage
from .storage import GatewayStorage
from .events import EventEngine, Snapshot, SQLiteEventRepository
from .events.models import utc_now
from .events.serializers import serialize_event, serialize_events
from .events.types import EventSeverity, EventSource, EventStatus
from .owner_dashboard import setup_dashboard_routes


logger = logging.getLogger(__name__)

app = FastAPI(
    title="Restaurant Gateway",
    version="10.4.9",
)
storage = GatewayStorage(settings.database_path)
event_repository = SQLiteEventRepository(settings.database_path)
event_engine = EventEngine(event_repository)
connections = ConnectionManager()
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(setup_dashboard_routes(storage, connections, event_repository))


class CreateAgentRequest(BaseModel):
    agent_id: str = Field(min_length=2, max_length=100)
    name: str = Field(min_length=2, max_length=200)


class QueryRequest(BaseModel):
    query_name: str
    parameters: dict = Field(default_factory=dict)
    bypass_cache: bool = False
    cache_ttl_seconds: int | None = Field(
        default=None,
        ge=0,
        le=3600,
    )


def require_admin(
    x_admin_token: str = Header(default=""),
) -> None:
    if x_admin_token != settings.admin_token:
        raise HTTPException(
            status_code=401,
            detail="Неверный административный токен",
        )


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "service": "restaurant-gateway",
        "version": "10.4.9",
        "online_agents": len(connections.connections),
    }


@app.post(
    "/api/admin/agents",
    dependencies=[Depends(require_admin)],
)
def create_agent(payload: CreateAgentRequest) -> dict:
    return storage.create_agent(
        payload.agent_id,
        payload.name,
    )


@app.get(
    "/api/admin/agents",
    dependencies=[Depends(require_admin)],
)
def list_agents() -> list[dict]:
    result = storage.list_agents()
    for item in result:
        item["online"] = connections.is_online(
            item["agent_id"]
        )
    return result


@app.post(
    "/api/agents/{agent_id}/query",
    dependencies=[Depends(require_admin)],
)
async def query_agent(
    agent_id: str,
    payload: QueryRequest,
) -> dict:
    try:
        return await connections.request(
            agent_id,
            payload.query_name,
            payload.parameters,
            settings.request_timeout_seconds,
            bypass_cache=payload.bypass_cache,
            cache_ttl_seconds=payload.cache_ttl_seconds,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@app.get(
    "/api/agents/{agent_id}/capabilities",
    dependencies=[Depends(require_admin)],
)
async def agent_capabilities(agent_id: str) -> dict:
    try:
        return await connections.control(
            agent_id,
            "capabilities_request",
            {},
            settings.request_timeout_seconds,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@app.post(
    "/api/agents/{agent_id}/cache/clear",
    dependencies=[Depends(require_admin)],
)
async def clear_agent_cache(agent_id: str) -> dict:
    try:
        return await connections.control(
            agent_id,
            "cache_clear",
            {},
            settings.request_timeout_seconds,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@app.get(
    "/api/cloud/{agent_id}/sales/latest",
    dependencies=[Depends(require_admin)],
)
def latest_cloud_sales(agent_id: str) -> dict:
    result = storage.latest_sales_snapshot(agent_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Облачные данные ещё не получены",
        )
    return result


@app.get(
    "/api/cloud/{agent_id}/sales/history",
    dependencies=[Depends(require_admin)],
)
def cloud_sales_history(
    agent_id: str,
    date_from: str = Query(...),
    date_to: str = Query(...),
) -> list[dict]:
    return storage.sales_history(
        agent_id,
        date_from,
        date_to,
    )


@app.get(
    "/api/cloud/{agent_id}/menu/history",
    dependencies=[Depends(require_admin)],
)
def cloud_menu_history(
    agent_id: str,
    date_from: str = Query(...),
    date_to: str = Query(...),
) -> list[dict]:
    return storage.menu_sales_history(
        agent_id,
        date_from,
        date_to,
    )



@app.get("/api/events", dependencies=[Depends(require_admin)])
def list_events(
    agent_id: str = Query(...),
    status: EventStatus | None = Query(None),
    source: EventSource | None = Query(None),
    severity: EventSeverity | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    return serialize_events(event_repository.list(
        agent_id=agent_id,status=status,source=source,
        severity=severity,limit=limit))

@app.get("/api/events/{event_id}", dependencies=[Depends(require_admin)])
def get_event(event_id: str) -> dict:
    event=event_repository.get(event_id)
    if event is None:
        raise HTTPException(status_code=404,detail="Событие не найдено")
    return serialize_event(event)

@app.post("/api/events/{event_id}/status", dependencies=[Depends(require_admin)])
def update_event_status(event_id: str,status: EventStatus) -> dict:
    event=event_repository.set_status(event_id,status)
    if event is None:
        raise HTTPException(status_code=404,detail="Событие не найдено")
    return serialize_event(event)

@app.websocket("/ws/agent")
async def websocket_agent(websocket: WebSocket) -> None:
    agent_id = websocket.headers.get("x-agent-id", "").strip()
    api_key = websocket.headers.get("x-relay-key", "").strip()

    if not agent_id or not api_key:
        await websocket.close(code=4401)
        return

    if not storage.authenticate(agent_id, api_key):
        await websocket.close(code=4403)
        return

    await connections.connect(agent_id, websocket)
    storage.update_seen(agent_id, status="online")

    try:
        while True:
            raw = await websocket.receive_text()
            message = GatewayMessage.model_validate_json(raw)

            if message.agent_id and message.agent_id != agent_id:
                await websocket.close(code=4403)
                return

            if message.type == "agent_hello":
                storage.update_seen(
                    agent_id,
                    status="online",
                    hostname=message.payload.get("hostname"),
                    database_name=message.payload.get(
                        "database_name"
                    ),
                    agent_version=message.payload.get(
                        "agent_version"
                    ),
                    capabilities=list(
                        message.payload.get("capabilities") or []
                    ),
                    allowed_queries=list(
                        message.payload.get("allowed_queries") or []
                    ),
                )
                await websocket.send_text(
                    GatewayMessage(
                        type="hello_ack",
                        agent_id=agent_id,
                        request_id=message.request_id,
                        payload={
                            "ok": True,
                            "heartbeat_seconds": 20,
                        },
                    ).model_dump_json()
                )

            elif message.type == "heartbeat":
                storage.update_seen(
                    agent_id,
                    status=str(
                        message.payload.get("status") or "online"
                    ),
                    last_query_at=message.payload.get(
                        "last_query_at"
                    ),
                    cache_entries=message.payload.get(
                        "cache_entries"
                    ),
                )
                await websocket.send_text(
                    GatewayMessage(
                        type="pong",
                        agent_id=agent_id,
                        request_id=message.request_id,
                        payload={
                            "ok": True,
                            "server_time": utc_now(),
                        },
                    ).model_dump_json()
                )

            elif message.type == "cloud_snapshot":
                try:
                    from .payload_codec import decode_payload

                    snapshot = decode_payload(message.payload)
                    storage.save_sales_snapshot(
                        agent_id,
                        snapshot,
                    )

                    current_event_snapshot = Snapshot.from_payload(
                        agent_id,
                        snapshot,
                    )
                    previous_payload = storage.previous_sales_snapshot(
                        agent_id,
                        current_event_snapshot.created_at,
                    )
                    previous_event_snapshot = (
                        Snapshot.from_payload(
                            agent_id,
                            previous_payload,
                        )
                        if previous_payload
                        else None
                    )

                    try:
                        event_engine.process_snapshot(
                            current_event_snapshot,
                            previous_event_snapshot,
                        )
                    except Exception:
                        logger.exception(
                            "Event Engine не обработал снимок агента %s",
                            agent_id,
                        )

                    storage.update_seen(
                        agent_id,
                        status="online",
                    )

                    await websocket.send_text(
                        GatewayMessage(
                            type="snapshot_ack",
                            agent_id=agent_id,
                            request_id=message.request_id,
                            payload={
                                "ok": True,
                                "business_date": snapshot.get(
                                    "business_date"
                                ),
                            },
                        ).model_dump_json()
                    )
                except Exception as exc:
                    logger.exception(
                        "Ошибка обработки облачного снимка агента %s",
                        agent_id,
                    )
                    await websocket.send_text(
                        GatewayMessage(
                            type="snapshot_error",
                            agent_id=agent_id,
                            request_id=message.request_id,
                            payload={
                                "ok": False,
                                "error": str(exc),
                            },
                        ).model_dump_json()
                    )

            elif message.type in {
                "query_result",
                "control_result",
                "capabilities_result",
            }:
                connections.resolve(agent_id, message)

    except WebSocketDisconnect:
        pass
    finally:
        storage.update_seen(agent_id, status="offline")
        await connections.disconnect(agent_id)
