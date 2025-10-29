from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable, List, Tuple

from .fs_sandbox import resolve_safe_path, WORKSPACE_ROOT
from .java_utils import fix_java_package, fix_java_filename


def _session_key(session_id: str) -> str:
    cleaned = "".join(ch for ch in str(session_id) if ch.isalnum())
    cleaned = cleaned[:12] if cleaned else str(session_id)[:12]
    return cleaned or "session"


def staging_rel(session_id: str, repo_label: str | None) -> str:
    parts = ["uploads", _session_key(session_id)]
    if repo_label:
        parts.extend(p for p in repo_label.split("/") if p)
    return "/".join(parts)


def prepare_directory(rel_path: str) -> Path:
    safe_path, ok = resolve_safe_path(rel_path if rel_path else ".")
    if not ok:
        raise RuntimeError(f"unsafe workspace path: {rel_path}")
    shutil.rmtree(safe_path, ignore_errors=True)
    safe_path.mkdir(parents=True, exist_ok=True)
    return safe_path


def stage_upload(session_id: str, repo_label: str | None, entries: Iterable[tuple[str, bytes]]) -> tuple[str, List[str], str]:
    rel_base = staging_rel(session_id, repo_label)
    dest_root = prepare_directory(rel_base)
    written: List[str] = []
    for rel_path, content_bytes in entries:
        target = dest_root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content_bytes)
        if target.suffix.lower() == ".java":
            fix_java_package(target)
            target = fix_java_filename(target)
        written.append(target.relative_to(dest_root).as_posix())
    workspace_path = f"./workspace/{rel_base}"
    return rel_base, written, workspace_path


def ensure_merge_tree(task_id: str, stage_rel: str) -> tuple[str, Path]:
    merge_rel = f"runs/{task_id}/merge"
    merge_root = prepare_directory(merge_rel)
    if stage_rel and stage_rel not in (".", ""):
        stage_root, ok = resolve_safe_path(stage_rel)
        if ok and stage_root.exists():
            for src in stage_root.rglob("*"):
                if not src.is_file():
                    continue
                rel = src.relative_to(stage_root)
                dst = merge_root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(src.read_bytes())
    return merge_rel, merge_root
