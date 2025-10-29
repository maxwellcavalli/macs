from __future__ import annotations
from datetime import datetime

from pydantic import BaseModel, Field, constr, field_validator, model_validator
from typing import List, Optional, Literal, Dict, Any
import uuid

class BaseTaskModel(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _normalize_status(cls, data):
        try:
            if isinstance(data, dict) and "status" in data:
                raw = data["status"]
                s = str(getattr(raw, "value", raw)).strip().lower()
                mapping = {
                    "succeeded": "done",
                    "success":   "done",
                    "completed": "done",
                    "complete":  "done",
                    "failed":    "error",
                    "failure":   "error",
                    "fail":      "error",
                    "cancelled": "canceled",
                }
                data["status"] = mapping.get(s, s)
        except Exception:
            # best-effort only; never block model construction
            pass
        return data

class _OldBaseTaskModel(BaseModel):
    @field_validator("status", mode="before", check_fields=False)
    @classmethod
    def _normalize_status(cls, v):
        if v is None:
            return v
        s = str(getattr(v, "value", v)).strip().lower()
        mapping = {
            "done": "done",
            "success": "done",
            "completed": "done",
            "complete": "done",
            "error": "error",
            "failure": "error",
            "fail": "error",
            "canceled": "canceled",
        }
        return mapping.get(s, s)

TaskType = Literal["CODE","PLAN","REFACTOR","TEST","DOC"]

class RepoSpec(BaseModel):
    path: str
    include: List[str] = []
    exclude: List[str] = []

class Constraints(BaseModel):
    max_tokens: int = 2048
    latency_ms: int = 60000
    style: Optional[str] = None

class TaskInput(BaseTaskModel):
    language: Literal["java","python","graphql"]
    frameworks: List[str] = []
    repo: RepoSpec
    constraints: Constraints
    goal: str

class OutputContract(BaseModel):
    expected_files: List[str] = []
    package_name: Optional[str] = None
    test_targets: List[str] = []

class NonNegotiables(BaseModel):
    build_tool: Optional[str] = None
    jdk: Optional[int] = None

class Oracle(BaseModel):
    smoke: bool = True
    full: bool = False

class TaskV1(BaseTaskModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    type: TaskType
    input: TaskInput
    context: Optional[Dict[str, Any]] = None
    routing_hints: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    prompt_template_version: Optional[str] = None

class TaskV11(TaskV1):
    output_contract: Optional[OutputContract] = None
    non_negotiables: Optional[NonNegotiables] = None
    oracle: Optional[Oracle] = None

class FeedbackV1(BaseModel):
    task_id: uuid.UUID
    model: str
    success: bool
    latency_ms: Optional[int] = None
    human_score: Optional[int] = Field(default=None, ge=0, le=5)
    notes: Optional[str] = None
    artifacts: Optional[Dict[str, Any]] = None

class TaskStatus(BaseTaskModel):
    id: uuid.UUID
    status: Literal["queued","running","done","error","canceled"]
    model_used: Optional[str] = None
    latency_ms: Optional[int] = None
    template_ver: Optional[str] = None


class WorkspaceMemory(BaseModel):
    id: uuid.UUID
    task_id: Optional[uuid.UUID] = None
    repo_path: Optional[str] = None
    language: Optional[str] = None
    mode: Optional[str] = None
    status: Optional[str] = None
    goal: Optional[str] = None
    model: Optional[str] = None
    summary: Optional[str] = None
    artifact_rel: Optional[str] = None
    zip_rel: Optional[str] = None
    files: Dict[str, Any] = Field(default_factory=dict)
    session_id: Optional[uuid.UUID] = None
    created_at: datetime


class WorkspaceMemorySearchResponse(BaseModel):
    memories: List[WorkspaceMemory] = Field(default_factory=list)
