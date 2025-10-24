from __future__ import annotations
import logging, json, os, sys, datetime
from typing import Any, Dict
from .logctx import ctx_snapshot

LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base: Dict[str, Any] = {
            "ts": datetime.datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Attach standard fields if present
        for attr in ("pathname","lineno","funcName"):
            base[attr] = getattr(record, attr, None)
        # Contextvars snapshot (request_id, task_id, route, candidate)
        base.update(ctx_snapshot())
        # If record has 'extra' dict (via LoggerAdapter or logger.info({...})), merge safely
        if isinstance(record.args, tuple) and len(record.args) == 1 and isinstance(record.args[0], dict):
            base.update(record.args[0])
        return json.dumps(base, ensure_ascii=False)

def setup_json_logging() -> None:
    root = logging.getLogger()
    root.setLevel(LEVEL)
    # Remove any existing handlers (uvicorn may add its own)
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
