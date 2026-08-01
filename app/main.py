from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.logging import configure_logging
from app.web.routes import router

configure_logging()

app = FastAPI(
    title="TillyPad Restaurant OS",
    version="11.1.2",
)

app.mount(
    "/static",
    StaticFiles(directory="app/web/static"),
    name="static",
)

app.include_router(router)
