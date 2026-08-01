from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.db.sql_server import SqlServer, SqlServerError
from app.services.dashboard_service import DashboardService
from app.services.explorer_service import ExplorerService
from app.services.schema_map_service import SchemaMapService
from app.services.sales_service import SalesService

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={},
    )


@router.get("/sql", response_class=HTMLResponse)
def sql_dashboard(request: Request):
    data = None
    error = None

    try:
        data = DashboardService().load()
    except SqlServerError as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="sql_dashboard.html",
        context={
            "data": data,
            "error": error,
        },
    )


@router.get("/sql-test")
def sql_test():
    try:
        info = SqlServer().info()
        return {
            "status": "ok",
            "server": info.server_name,
            "database": info.database_name,
            "version": info.version,
        }
    except SqlServerError as exc:
        return {
            "status": "error",
            "message": str(exc),
        }


@router.get("/sql-explorer", response_class=HTMLResponse)
def sql_explorer(
    request: Request,
    table_search: str = "",
    column_search: str = "",
):
    result = {
        "tables": [],
        "columns": [],
    }
    error = None

    try:
        result = ExplorerService().search(
            table_search,
            column_search,
        )
    except SqlServerError as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="sql_explorer.html",
        context={
            "tables": result["tables"],
            "columns": result["columns"],
            "table_search": table_search,
            "column_search": column_search,
            "error": error,
        },
    )


@router.get("/sql-explorer/table", response_class=HTMLResponse)
def sql_explorer_table(
    request: Request,
    schema: str,
    table: str,
    limit: int = 20,
):
    result = {
        "structure": [],
        "preview": None,
    }
    error = None

    try:
        result = ExplorerService().table(
            schema,
            table,
            limit,
        )
    except SqlServerError as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="sql_table.html",
        context={
            "schema": schema,
            "table": table,
            "limit": max(1, min(limit, 100)),
            "structure": result["structure"],
            "preview": result["preview"],
            "error": error,
        },
    )


@router.get("/schema-map", response_class=HTMLResponse)
def schema_map(request: Request, search: str = ""):
    result = None
    error = None
    try:
        result = SchemaMapService().load(search)
    except SqlServerError as exc:
        error = str(exc)
    return templates.TemplateResponse(
        request=request,
        name="schema_map.html",
        context={"result": result, "search": search, "error": error},
    )


@router.get("/sales", response_class=HTMLResponse)
def sales_dashboard(
    request: Request,
    date_from: date | None = None,
    date_to: date | None = None,
):
    result = None
    error = None

    try:
        result = SalesService().dashboard(date_from, date_to)
    except SqlServerError as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="sales_dashboard.html",
        context={
            "result": result,
            "error": error,
        },
    )


@router.get("/health")
def health():
    return {
        "status": "ok",
        "version": "1.3.1",
    }
