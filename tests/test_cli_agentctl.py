from __future__ import annotations

import uuid

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cli import agentctl


def test_sanitize_repo_path_normalizes_variants():
    assert agentctl._sanitize_repo_path(None) == "./workspace"
    assert agentctl._sanitize_repo_path("") == "./workspace"
    assert agentctl._sanitize_repo_path("./workspace") == "./workspace"
    assert agentctl._sanitize_repo_path("workspace/foo") == "./workspace/foo"
    assert agentctl._sanitize_repo_path("./foo/bar") == "./workspace/foo/bar"


def test_ensure_language_accepts_supported_values():
    assert agentctl._ensure_language("Python") == "python"
    assert agentctl._ensure_language("java") == "java"


def test_build_chat_payload_shapes_request():
    session_id = str(uuid.uuid4())
    payload = agentctl._build_chat_payload(
        message="hello world",
        language="python",
        repo_path="./workspace/uploads/demo",
        memory_ids=["abc"],
        session_id=session_id,
        max_tokens=512,
        latency_ms=20000,
    )
    assert payload["type"] == "DOC"
    assert payload["input"]["language"] == "python"
    assert payload["metadata"]["session_id"] == session_id
    assert payload["metadata"]["memory_context_ids"] == ["abc"]


def test_extract_result_text_prefers_main_fields():
    result = {"result": "primary", "content": "secondary", "note": "fallback"}
    assert agentctl._extract_result_text(result) == "primary"
    result.pop("result")
    assert agentctl._extract_result_text(result) == "secondary"
    result.pop("content")
    assert agentctl._extract_result_text(result) == "fallback"
