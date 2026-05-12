"""FastAPI application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from annotator_backend.config import get_settings
from annotator_backend.logging_config import setup_logging
from annotator_backend.routers.tickets import router as tickets_router
from db.session import configure_engine


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    setup_logging(json_logs=settings.log_json, level=logging.INFO)
    configure_engine(database_url=settings.database_url)
    yield


app = FastAPI(
    title="BuildIt Support Ticket Triage API",
    lifespan=lifespan,
)
app.include_router(tickets_router)
