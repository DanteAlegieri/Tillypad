import json
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .db import (
    add_sync_log,
    dashboard_stats,
    init_db,
    normalize_list,
    upsert_divisions,
    upsert_guests,
)
from .tillypad import TillypadError, get_target

app = FastAPI(title="Гастродом №3 — Tillypad Dashboard")
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, date: str | None = None):
    stats = dashboard_stats(date)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "stats": stats,
            "selected_date": date or "",
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        },
    )


@app.get("/diagnostics", response_class=HTMLResponse)
def diagnostics(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="diagnostics.html",
        context={
            "result": None,
            "error": None,
            "target": "SegmentInfo",
            "body": "",
        },
    )


@app.post("/diagnostics", response_class=HTMLResponse)
def diagnostics_run(
    request: Request,
    target: str = Form(...),
    body: str = Form(""),
):
    parsed_body = None
    error = None
    result = None

    try:
        if body.strip():
            parsed_body = json.loads(body)
        result = get_target(target.strip(), parsed_body)
    except (json.JSONDecodeError, TillypadError) as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="diagnostics.html",
        context={
            "result": json.dumps(result, ensure_ascii=False, indent=2)
            if result is not None
            else None,
            "error": error,
            "target": target,
            "body": body,
        },
    )


@app.post("/sync/segment-info")
def sync_segment_info():
    try:
        data = get_target("SegmentInfo")
        rows = normalize_list(data)
        add_sync_log("SegmentInfo", "ok", "Подключение успешно", len(rows))
        return RedirectResponse(
            "/?message=Подключение к Tillypad успешно проверено",
            status_code=303,
        )
    except TillypadError as exc:
        add_sync_log("SegmentInfo", "error", str(exc), 0)
        return RedirectResponse(f"/?error={str(exc)}", status_code=303)


@app.post("/sync/divisions")
def sync_divisions():
    try:
        data = get_target("Divisions")
        rows = normalize_list(data)
        count = upsert_divisions(rows)
        add_sync_log("Divisions", "ok", "Подразделения обновлены", count)
        return RedirectResponse(
            f"/?message=Загружено подразделений: {count}",
            status_code=303,
        )
    except TillypadError as exc:
        add_sync_log("Divisions", "error", str(exc), 0)
        return RedirectResponse(f"/?error={str(exc)}", status_code=303)


@app.post("/sync/guests")
def sync_guests(
    guest_filter: str = Form(""),
):
    try:
        parsed_filter = None
        if guest_filter.strip():
            parsed_filter = json.loads(guest_filter)

        data = get_target("Guests", parsed_filter)
        rows = normalize_list(data)
        count = upsert_guests(rows)
        add_sync_log("Guests", "ok", "Гостевые счета обновлены", count)
        return RedirectResponse(
            f"/?message=Загружено гостевых счетов: {count}",
            status_code=303,
        )
    except json.JSONDecodeError as exc:
        message = f"Некорректный JSON-фильтр: {exc}"
        add_sync_log("Guests", "error", message, 0)
        return RedirectResponse(f"/?error={message}", status_code=303)
    except TillypadError as exc:
        add_sync_log("Guests", "error", str(exc), 0)
        return RedirectResponse(f"/?error={str(exc)}", status_code=303)


@app.post("/import/guests-json")
def import_guests_json(
    json_text: str = Form(...),
):
    try:
        data = json.loads(json_text)
        rows = normalize_list(data)
        count = upsert_guests(rows)
        add_sync_log("GuestsImport", "ok", "JSON импортирован", count)
        return RedirectResponse(
            f"/?message=Импортировано гостевых счетов: {count}",
            status_code=303,
        )
    except json.JSONDecodeError as exc:
        message = f"Некорректный JSON: {exc}"
        add_sync_log("GuestsImport", "error", message, 0)
        return RedirectResponse(f"/?error={message}", status_code=303)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "time": datetime.now().isoformat(),
    }
