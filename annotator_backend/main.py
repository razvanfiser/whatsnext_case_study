"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from annotator_backend.config import get_settings
from annotator_backend.routers.tickets import router as tickets_router
from db.session import configure_engine


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_engine(database_url=get_settings().database_url)
    yield


app = FastAPI(
    title="BuildIt Support Ticket Triage API",
    lifespan=lifespan,
)
app.include_router(tickets_router)
