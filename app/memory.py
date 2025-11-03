from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import text

from .db import get_engine
from .settings import settings

# Limits to keep persisted payloads lean
MAX_FILES = 8
MAX_FILE_BYTES = 4096
MAX_SUMMARY_BYTES = 4096


def _enabled() -> bool:
    return bool(getattr(settings, "workspace_memory_enabled", False))


def _truncate(text_value: Optional[str], limit: int) -> str:
    if not text_value:
        return ""
    if len(text_value) <= limit:
        return text_value
    return text_value[: limit - 3] + "..."


def _normalize_repo_path(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).strip().replace("\\", "/")
    if not cleaned:
        return None
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    cleaned = cleaned.rstrip("/")
    return cleaned or None


def _normalize_session_id(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        sid = str(UUID(str(value)))
        return sid
    except Exception:
        return None


def _resolve_repo_path(job: Dict[str, Any]) -> Optional[str]:
    repo = ((job.get("input") or {}).get("repo")) or {}
    path = repo.get("path")
    if not path:
        return None
    return _normalize_repo_path(str(path))


def _detect_language_from_artifact(artifact: Optional[str], files: Dict[str, Any]) -> Optional[str]:
    """
    Try to infer the language from artifact/file extensions.
    Returns normalized language string or None if indeterminate.
    """
    CANDIDATE_EXTS = {
        ".java": "java",
        ".py": "python",
        ".rb": "ruby",
        ".js": "javascript",
        ".ts": "typescript",
        ".cs": "csharp",
        ".go": "go",
        ".rs": "rust",
        ".php": "php",
        ".kt": "kotlin",
    }

    paths: List[str] = []
    if artifact:
        paths.append(str(artifact))
    file_map = files.get("files")
    if isinstance(file_map, dict):
        paths.extend(str(name) for name in file_map.keys())
    for path in paths:
        suffix = Path(path).suffix.lower()
        if suffix in CANDIDATE_EXTS:
            return CANDIDATE_EXTS[suffix]
    return None


def _infer_language(job: Dict[str, Any], result: Dict[str, Any]) -> Optional[str]:
    lang = ((job.get("input") or {}).get("language")) or None
    lang = str(lang).strip().lower() if lang else None
    artifact = result.get("artifact")
    detected = _detect_language_from_artifact(artifact, result.get("files") or {})
    if detected:
        if not lang or lang != detected:
            return detected
    return lang


def _collect_files(result: Dict[str, Any]) -> Dict[str, Any]:
    files: Dict[str, Any] = {}
    artifact_path = result.get("artifact")
    if artifact_path:
        files["artifact"] = str(artifact_path)
        try:
            path_obj = Path(artifact_path)
            if path_obj.is_file():
                contents = path_obj.read_text(encoding="utf-8", errors="ignore")
                files["artifact_preview"] = _truncate(contents, MAX_FILE_BYTES)
        except Exception:
            pass
    if result.get("zip_url"):
        files["zip_url"] = result["zip_url"]
    if result.get("zip_path"):
        files["zip_path"] = result["zip_path"]
    extras = result.get("files")
    if isinstance(extras, dict):
        subset: Dict[str, str] = {}
        for idx, (rel, content) in enumerate(extras.items()):
            if idx >= MAX_FILES:
                break
            subset[str(rel)] = _truncate(str(content), MAX_FILE_BYTES)
        if subset:
            files["files"] = subset
    return files


def _deserialize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(row)
    files_field = data.get("files")
    if isinstance(files_field, str):
        try:
            data["files"] = json.loads(files_field)
        except json.JSONDecodeError:
            data["files"] = {}
    elif files_field is None:
        data["files"] = {}
    for key in ("id", "task_id", "session_id"):
        if key in data and data[key] is not None:
            data[key] = str(data[key])
    return data


def _repo_path_variants(value: str) -> List[str]:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        return []
    variants = {raw}
    variants.add(raw.rstrip("/"))
    variants.add(raw.lstrip("./"))
    variants.add(raw.lstrip("./").rstrip("/"))
    normalized = _normalize_repo_path(raw)
    if normalized:
        variants.add(normalized)
        variants.add(f"./{normalized}")
        variants.add(f"{normalized}/")
        variants.add(f"./{normalized}/")
    return [v for v in variants if v]


async def _insert_memory_row(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        engine = await get_engine()
    except Exception:
        return None

    sql = text(
        """
        INSERT INTO public.workspace_memories
            (task_id, repo_path, language, mode, status, goal, model, summary, artifact_rel, zip_rel, files, session_id)
        VALUES
            (:task_id, :repo_path, :language, :mode, :status, :goal, :model, :summary, :artifact_rel, :zip_rel, CAST(:files AS JSONB), :session_id)
        RETURNING id, goal, summary, model, language, mode, session_id, created_at
        """
    )

    payload = {
        "task_id": data.get("task_id"),
        "repo_path": data.get("repo_path"),
        "language": data.get("language"),
        "mode": data.get("mode"),
        "status": data.get("status") or "done",
        "goal": data.get("goal"),
        "model": data.get("model"),
        "summary": data.get("summary"),
        "artifact_rel": data.get("artifact_rel"),
        "zip_rel": data.get("zip_rel"),
        "files": json.dumps(data.get("files_payload") or {}),
        "session_id": data.get("session_id"),
    }

    try:
        async with engine.begin() as conn:
            result = await conn.execute(sql, payload)
            row = result.mappings().first()
            return dict(row) if row else None
    except Exception:
        return None


async def record_completion(task_id: str, job: Dict[str, Any], result: Dict[str, Any]) -> None:
    """
    Persist a completed task output into workspace memory.
    Safe no-op when the feature flag is disabled.
    """
    if not _enabled():
        return

    language = _infer_language(job, result)
    mode = result.get("mode") or job.get("_mode")
    repo_path = _resolve_repo_path(job)
    goal = ((job.get("input") or {}).get("goal")) or None
    summary = _truncate(result.get("content"), MAX_SUMMARY_BYTES)
    files_payload = _collect_files(result)
    session_id = _normalize_session_id((job.get("metadata") or {}).get("session_id")) if isinstance(job, dict) else None

    await _insert_memory_row({
        "task_id": str(task_id),
        "repo_path": repo_path,
        "language": language,
        "mode": mode,
        "status": result.get("status") or "done",
        "goal": goal,
        "model": result.get("model"),
        "summary": summary,
        "artifact_rel": files_payload.get("artifact"),
        "zip_rel": files_payload.get("zip_url") or files_payload.get("zip_path"),
        "files_payload": files_payload,
        "session_id": session_id,
    })


async def upsert_bootstrap_memory(
    *,
    rel_path: str,
    content: str,
    language: Optional[str] = None,
    repo_path: Optional[str] = None,
    model: str = "bootstrap-ingest",
    mode: str = "bootstrap",
    session_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Insert or replace a workspace memory entry for an existing repository file."""
    if not _enabled():
        return None
    cleaned_path = rel_path.replace("\\", "/").lstrip("./")
    summary = _truncate(content, MAX_SUMMARY_BYTES)
    snippet = _truncate(content, MAX_FILE_BYTES)
    files_payload = {
        "artifact": cleaned_path,
        "files": {cleaned_path: snippet},
    }
    if language is None:
        language = _detect_language_from_artifact(cleaned_path, files_payload)

    try:
        engine = await get_engine()
    except Exception:
        return None

    delete_sql = text(
        """
        DELETE FROM public.workspace_memories
        WHERE mode = :mode AND artifact_rel = :artifact_rel
        """
    )

    async with engine.begin() as conn:
        await conn.execute(delete_sql, {"artifact_rel": cleaned_path, "mode": mode})

    return await _insert_memory_row({
        "task_id": None,
        "repo_path": _normalize_repo_path(repo_path) if repo_path else None,
        "language": language,
        "mode": mode,
        "status": "done",
        "goal": f"Bootstrap file: {cleaned_path}",
        "model": model,
        "summary": summary,
        "artifact_rel": cleaned_path,
        "zip_rel": None,
        "files_payload": files_payload,
        "session_id": _normalize_session_id(session_id),
    })


async def record_upload_bundle(
    *,
    session_id: str,
    repo_path: Optional[str],
    goal: str,
    summary: str,
    files_payload: Dict[str, Any],
    language: Optional[str] = None,
    model: str = "memory-upload",
) -> Optional[Dict[str, Any]]:
    if not _enabled():
        return None
    lang = language
    if not lang and isinstance(files_payload, dict):
        candidates = []
        file_map = files_payload.get("files") if isinstance(files_payload.get("files"), dict) else {}
        if isinstance(file_map, dict):
            candidates.extend(file_map.keys())
        artifact_hint = files_payload.get("artifact")
        if artifact_hint:
            candidates.insert(0, artifact_hint)
        for rel in candidates:
            detected = _detect_language_from_artifact(rel, files_payload)
            if detected:
                lang = detected
                break
    return await _insert_memory_row({
        "task_id": None,
        "repo_path": _normalize_repo_path(repo_path) if repo_path else None,
        "language": lang,
        "mode": "upload",
        "status": "done",
        "goal": goal,
        "model": model,
        "summary": summary,
        "artifact_rel": files_payload.get("artifact"),
        "zip_rel": None,
        "files_payload": files_payload,
        "session_id": _normalize_session_id(session_id),
    })


async def search_memories(
    *,
    repo_path: Optional[str] = None,
    language: Optional[str] = None,
    query: Optional[str] = None,
    session_id: Optional[str] = None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """
    Retrieve recent workspace memories using basic filters.
    When disabled, returns an empty list.
    """
    if not _enabled():
        return []
    limit = max(1, min(limit, 25))

    try:
        engine = await get_engine()
    except Exception:
        return []

    clauses: List[str] = []
    params: Dict[str, Any] = {"limit": limit}

    if repo_path:
        variants = _repo_path_variants(repo_path)
        if variants:
            placeholders: List[str] = []
            for idx, value in enumerate(variants):
                key = f"repo_path_{idx}"
                params[key] = value.lower()
                placeholders.append(f"lower(coalesce(repo_path,'')) = :{key}")
            normalized = _normalize_repo_path(repo_path)
            if normalized:
                params["repo_like"] = f"%{normalized.lower()}%"
                placeholders.append("lower(coalesce(repo_path,'')) LIKE :repo_like")
            clauses.append("(" + " OR ".join(placeholders) + ")")
    if language:
        language_clean = str(language).strip().lower()
        if language_clean:
            params["language"] = language_clean
            params["language_like"] = f"%{language_clean}%"
            clauses.append(
                "("
                "lower(coalesce(language,'')) = :language"
                " OR lower(coalesce(goal,'')) LIKE :language_like"
                " OR lower(coalesce(summary,'')) LIKE :language_like"
                ")"
            )
    if query:
        clauses.append(
            "to_tsvector('english', coalesce(goal,'') || ' ' || coalesce(summary,'')) @@ plainto_tsquery(:query)"
        )
        params["query"] = query
    if session_id:
        sid = _normalize_session_id(session_id)
        if sid:
            params["session_id"] = sid
            clauses.append("session_id = :session_id")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    sql = text(
        f"""
        SELECT id, task_id, repo_path, language, mode, status, goal, model, summary,
               artifact_rel, zip_rel, files, created_at, session_id
        FROM public.workspace_memories
        {where}
        ORDER BY created_at DESC
        LIMIT :limit
        """
    )

    try:
        async with engine.connect() as conn:
            result = await conn.execute(sql, params)
            rows = result.mappings().all()
    except Exception:
        return []

    return [_deserialize_row(row) for row in rows]


async def get_memory(memory_id: str) -> Optional[Dict[str, Any]]:
    if not _enabled():
        return None
    try:
        engine = await get_engine()
    except Exception:
        return None

    sql = text(
        """
        SELECT id, task_id, repo_path, language, mode, status, goal, model, summary,
               artifact_rel, zip_rel, files, created_at, session_id
        FROM public.workspace_memories
        WHERE id = :memory_id
        """
    )

    try:
        async with engine.connect() as conn:
            result = await conn.execute(sql, {"memory_id": memory_id})
            row = result.mappings().first()
    except Exception:
        return None
    if not row:
        return None
    return _deserialize_row(row)
