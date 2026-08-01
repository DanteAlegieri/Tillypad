from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.logging import configure_logging
from app.web.routes import router

configure_logging()

app = FastAPI(
    title="Гастродом №3 — Tillypad Dashboard",
    version="1.0.0",
)

app.mount(
    "/static",
    StaticFiles(directory="app/web/static"),
    name="static",
)

app.include_router(router)
