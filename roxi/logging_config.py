"""
Structured JSON logging setup.

Call configure() once at process start. Every logger in the roxi package
then emits JSON lines to stderr, making them parseable by any log aggregator.

Usage:
    from roxi.logging_config import configure
    configure(level="INFO")

In development, set ROXI_LOG_FORMAT=text to get human-readable output.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import traceback


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        doc: dict = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            doc["exc"] = traceback.format_exception(*record.exc_info)[-1].strip()
        for key in ("run_id", "org_id", "agent", "lead_id", "vertical_id"):
            if hasattr(record, key):
                doc[key] = getattr(record, key)
        return json.dumps(doc, ensure_ascii=False)


class _TextFormatter(logging.Formatter):
    _FMT = "%(asctime)s %(levelname)-8s %(name)s %(message)s"
    _DATEFMT = "%H:%M:%S"

    def __init__(self) -> None:
        super().__init__(self._FMT, datefmt=self._DATEFMT)


def configure(level: str = "INFO") -> None:
    level_int = getattr(logging, level.upper(), logging.INFO)

    use_json = os.environ.get("ROXI_LOG_FORMAT", "json").lower() != "text"
    fmt: logging.Formatter = _JsonFormatter() if use_json else _TextFormatter()

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(fmt)

    root = logging.getLogger("roxi")
    root.setLevel(level_int)
    root.handlers.clear()
    root.addHandler(handler)
    root.propagate = False
