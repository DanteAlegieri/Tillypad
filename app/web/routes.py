import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.dashboard import get_dashboard_data
from app.services.sync_service import SyncService
from app.services.tillypad_client import TillypadClient, TillypadError

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


def redirect_message(message: str, error: bool = False):
    key = "error" if error else "message"
    return RedirectResponse(
        url=f"/?{key}={quote(message)}",
        status_code=303,
    )


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    date: str | None = None,
    db: Session = Depends(get_db),
):
    stats = get_dashboard_data(db, date)

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


@router.get("/diagnostics", response_class=HTMLResponse)
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


@router.post("/diagnostics", response_class=HTMLResponse)
def diagnostics_run(
    request: Request,
    target: str = Form(...),
    body: str = Form(""),
):
    result = None
    error = None

    try:
        parsed_body = json.loads(body) if body.strip() else None
        result = TillypadClient().get(target.strip(), parsed_body)
    except (json.JSONDecodeError, TillypadError) as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="diagnostics.html",
        context={
            "result": (
                json.dumps(result, ensure_ascii=False, indent=2)
                if result is not None
                else None
            ),
            "error": error,
            "target": target,
            "body": body,
        },
    )


@router.post("/sync/segment-info")
def sync_segment_info(db: Session = Depends(get_db)):
    service = SyncService(db)
    try:
        count = service.test_connection()
        return redirect_message(
            f"Подключение успешно. Сегментов: {count}"
        )
    except TillypadError as exc:
        service.log("SegmentInfo", "error", str(exc), 0)
        return redirect_message(str(exc), error=True)


@router.post("/sync/divisions")
def sync_divisions(db: Session = Depends(get_db)):
    service = SyncService(db)
    try:
        count = service.sync_divisions()
        return redirect_message(
            f"Загружено подразделений: {count}"
        )
    except TillypadError as exc:
        service.log("Divisions", "error", str(exc), 0)
        return redirect_message(str(exc), error=True)


@router.post("/sync/guests")
def sync_guests(
    guest_filter: str = Form(""),
    db: Session = Depends(get_db),
):
    service = SyncService(db)

    try:
        parsed_filter = (
            json.loads(guest_filter)
            if guest_filter.strip()
            else None
        )
        count = service.sync_guests(parsed_filter)
        return redirect_message(
            f"Загружено гостевых счетов: {count}"
        )
    except json.JSONDecodeError as exc:
        message = f"Некорректный JSON-фильтр: {exc}"
        service.log("Guests", "error", message, 0)
        return redirect_message(message, error=True)
    except TillypadError as exc:
        service.log("Guests", "error", str(exc), 0)
        return redirect_message(str(exc), error=True)


@router.get("/health")
def health():
    return {
        "status": "ok",
        "version": "0.2.0",
    }
