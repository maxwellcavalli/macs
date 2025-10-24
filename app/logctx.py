from __future__ import annotations
import contextvars
from typing import Dict

_request_id = contextvars.ContextVar("request_id", default=None)
_route      = contextvars.ContextVar("route", default=None)
_task_id    = contextvars.ContextVar("task_id", default=None)
_candidate  = contextvars.ContextVar("candidate", default=None)

def set_request_id(v: str|None): _request_id.set(v)
def set_route(v: str|None):      _route.set(v)
def set_task_id(v: str|None):    _task_id.set(v)
def set_candidate(v: str|None):  _candidate.set(v)

def ctx_snapshot() -> Dict[str,str|None]:
    return {
        "request_id": _request_id.get(),
        "route": _route.get(),
        "task_id": _task_id.get(),
        "candidate": _candidate.get(),
    }
