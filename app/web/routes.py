from datetime import date, timedelta
import csv
import io

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app.db.sql_server import SqlServer, SqlServerError
from app.services.dashboard_service import DashboardService
from app.services.explorer_service import ExplorerService
from app.services.schema_map_service import SchemaMapService
from app.services.sales_service import SalesService
from app.services.menu_analytics_service import MenuAnalyticsService
from app.services.recommendation_service import RecommendationService
from app.services.menu_service import MenuService
from app.services.finance_service import FinanceService
from app.services.operations_service import OperationsService
from app.services.bi_service import BIService
from app.services.item_service import ItemService
from app.services.decision_service import DecisionService
from app.services.ceo_service import CEOService
from app.services.database_explorer_service import DatabaseExplorerService
from app.services.delivery_service import DeliveryService

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


@router.get("/", response_class=HTMLResponse)
def restaurant_brain_home(request: Request):
    result = None
    error = None

    try:
        result = CEOService().load()
    except SqlServerError as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="restaurant_brain.html",
        context={
            "result": result,
            "error": error,
        },
    )


@router.get("/operations", response_class=HTMLResponse)
def operations_dashboard(request: Request):
    result = None
    error = None

    try:
        result = OperationsService().load()
    except SqlServerError as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="operations_dashboard.html",
        context={
            "result": result,
            "error": error,
        },
    )


@router.get("/sql")
def sql_dashboard():
    return RedirectResponse(url="/", status_code=302)


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
            "today": date.today(),
            "yesterday": date.today() - timedelta(days=1),
            "this_month_from": date.today().replace(day=1),
            "this_month_to": date.today(),
            "previous_month_to": (
                date.today().replace(day=1) - timedelta(days=1)
            ),
            "previous_month_from": (
                date.today().replace(day=1) - timedelta(days=1)
            ).replace(day=1),
        },
    )


@router.get("/marketing", response_class=HTMLResponse)
def marketing_dashboard(
    request: Request,
    date_from: date | None = None,
    date_to: date | None = None,
):
    result = None
    error = None

    try:
        result = RecommendationService().dashboard(
            date_from,
            date_to,
        )
    except SqlServerError as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="marketing_dashboard.html",
        context={
            "result": result,
            "error": error,
        },
    )


@router.get("/menu", response_class=HTMLResponse)
def menu_dashboard(
    request: Request,
    date_from: date | None = None,
    date_to: date | None = None,
):
    result = None
    error = None
    try:
        result = MenuAnalyticsService().dashboard(date_from, date_to)
    except SqlServerError as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="menu_dashboard.html",
        context={
            "result": result,
            "error": error,
        },
    )


@router.get("/menu/item/{item_id}", response_class=HTMLResponse)
def menu_item_detail(
    request: Request,
    item_id: str,
    date_from: date | None = None,
    date_to: date | None = None,
):
    result = None
    error = None
    try:
        result = MenuAnalyticsService().item_detail(
            item_id,
            date_from,
            date_to,
        )
    except SqlServerError as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="menu_item_detail.html",
        context={
            "result": result,
            "error": error,
        },
        status_code=200 if result or error else 404,
    )


@router.get("/finance", response_class=HTMLResponse)
def finance_dashboard(
    request: Request,
    date_from: date | None = None,
    date_to: date | None = None,
):
    result = None
    error = None

    try:
        result = FinanceService().load(date_from, date_to)
    except SqlServerError as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="finance_dashboard.html",
        context={
            "result": result,
            "error": error,
        },
    )


@router.get("/bi", response_class=HTMLResponse)
def bi_dashboard(
    request: Request,
    date_from: date | None = None,
    date_to: date | None = None,
    xyz_mode: str = "adaptive",
):
    result = None
    error = None
    try:
        result = BIService().load(date_from, date_to, xyz_mode)
    except SqlServerError as exc:
        error = str(exc)
    return templates.TemplateResponse(
        request=request,
        name="bi_dashboard.html",
        context={"result": result, "error": error, "xyz_mode": xyz_mode},
    )


@router.get("/bi/export.csv")
def bi_export_csv(
    date_from: date | None = None,
    date_to: date | None = None,
    xyz_mode: str = "adaptive",
):
    result = BIService().load(date_from, date_to, xyz_mode)
    analysis = result["analysis"]
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "Позиция", "ABC", "XYZ", "Матрица",
        "Продано", "Выручка", "Доля, %", "Вариация, %",
    ])
    for item in analysis["items"]:
        writer.writerow([
            item["item_name"], item["abc"], item["xyz"], item["matrix"],
            item["quantity"], item["revenue"], item["share"],
            item["variation"] if item["variation"] is not None else "",
        ])
    payload = ("\ufeff" + output.getvalue()).encode("utf-8")
    filename = f'bi_{analysis["date_from"]}_{analysis["date_to"]}.csv'
    return StreamingResponse(
        iter([payload]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/menu/item/{item_id}", response_class=HTMLResponse)
def item_dashboard(
    request: Request,
    item_id: str,
    date_from: date | None = None,
    date_to: date | None = None,
):
    result = None
    error = None

    try:
        result = ItemService().load(
            item_id,
            date_from,
            date_to,
        )
        if result is None:
            error = "Позиция меню не найдена."
    except SqlServerError as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="item_dashboard.html",
        context={
            "result": result,
            "error": error,
            "item_id": item_id,
        },
    )


@router.get("/decisions", response_class=HTMLResponse)
def decision_center(request: Request):
    result = None
    error = None

    try:
        result = DecisionService().load()
    except SqlServerError as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="decision_center.html",
        context={
            "result": result,
            "error": error,
        },
    )


@router.get("/ceo")
def ceo_mode():
    return RedirectResponse(url="/", status_code=302)





@router.get("/delivery", response_class=HTMLResponse)
def delivery_dashboard(
    request: Request,
    date_from: date | None = None,
    date_to: date | None = None,
):
    result = None
    error = None

    try:
        result = DeliveryService().load(date_from, date_to)
    except SqlServerError as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="delivery_dashboard.html",
        context={
            "result": result,
            "error": error,
            "today": date.today(),
            "yesterday": date.today() - timedelta(days=1),
            "this_month_from": date.today().replace(day=1),
            "this_month_to": date.today(),
            "previous_month_to": date.today().replace(day=1) - timedelta(days=1),
            "previous_month_from": (
                date.today().replace(day=1) - timedelta(days=1)
            ).replace(day=1),
        },
    )


@router.get("/delivery/orders", response_class=HTMLResponse)
def delivery_orders(
    request: Request,
    date_from: date | None = None,
    date_to: date | None = None,
    courier: str = "",
    stage: str = "",
    weekday: int | None = None,
    hour: int | None = None,
    overdue: bool = False,
):
    result = None
    error = None

    try:
        result = DeliveryService().load_orders(
            date_from=date_from,
            date_to=date_to,
            courier_name=courier,
            stage=stage,
            weekday_number=weekday,
            hour_number=hour,
            only_overdue=overdue,
        )
    except SqlServerError as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="delivery_orders.html",
        context={
            "result": result,
            "error": error,
        },
    )


@router.get("/delivery/order/{delivery_id}", response_class=HTMLResponse)
def delivery_order_detail(
    request: Request,
    delivery_id: str,
):
    result = None
    error = None

    try:
        result = DeliveryService().load_order_detail(delivery_id)
    except SqlServerError as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request=request,
        name="delivery_order_detail.html",
        context={
            "result": result,
            "error": error,
            "delivery_id": delivery_id,
        },
        status_code=200 if result or error else 404,
    )


@router.get("/database-explorer", response_class=HTMLResponse)
def database_explorer(request: Request, search: str = ""):
    result = None
    error = None
    try:
        result = DatabaseExplorerService().index(search)
    except Exception as exc:
        error = str(exc)
    return templates.TemplateResponse(
        request=request,
        name="database_explorer.html",
        context={"result": result, "error": error},
    )


@router.get("/database-explorer/table", response_class=HTMLResponse)
def database_explorer_table(
    request: Request,
    schema_name: str,
    table_name: str,
    limit: int = 50,
):
    result = None
    error = None
    try:
        result = DatabaseExplorerService().table(
            schema_name, table_name, limit
        )
    except Exception as exc:
        error = str(exc)
    return templates.TemplateResponse(
        request=request,
        name="database_explorer_table.html",
        context={"result": result, "error": error},
    )


@router.get("/health")
def health():
    return {
        "status": "ok",
        "version": "14.2.0",
    }
