"""Configure root logging: JSON lines for aggregators or plain text for local dev."""

from __future__ import annotations

import logging
import sys
from typing import Final

from pythonjsonlogger import jsonlogger

SERVICE_NAME: Final = "buildit-triage-api"


def setup_logging(*, json_logs: bool, level: int = logging.INFO) -> None:
    """Attach formatters to existing StreamHandlers or add stdout StreamHandler.

    Uvicorn often configures handlers before FastAPI lifespan; we attach JsonFormatter
    to those handlers when ``json_logs`` so worker logs still serialize as JSON.
    """
    root = logging.root
    root.setLevel(level)

    if json_logs:
        formatter: logging.Formatter = jsonlogger.JsonFormatter(
            "%(levelname)s %(name)s %(message)s",
            rename_fields={"levelname": "level"},
            static_fields={"service": SERVICE_NAME},
            timestamp=True,
            json_default=str,
        )
    else:
        formatter = logging.Formatter("%(levelname)s %(name)s %(message)s")

    stream_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)]
    if stream_handlers:
        for handler in stream_handlers:
            handler.setFormatter(formatter)
    else:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        root.addHandler(handler)
