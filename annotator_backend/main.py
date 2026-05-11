"""FastAPI application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from annotator_backend.config import get_settings
from annotator_backend.routers.tickets import router as tickets_router
from db.session import configure_engine


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not logging.root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)s %(name)s %(message)s",
        )
    configure_engine(database_url=get_settings().database_url)
    yield


app = FastAPI(
    title="BuildIt Support Ticket Triage API",
    lifespan=lifespan,
)
app.include_router(tickets_router)
