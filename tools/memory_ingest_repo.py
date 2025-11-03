#!/usr/bin/env python
"""Bootstrap existing repository files into workspace memory."""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from typing import Iterable, List, Optional, Set

from app.settings import settings
from app.memory import upsert_bootstrap_memory

DEFAULT_EXTS = {
    ".py",
    ".java",
    ".md",
    ".rst",
    ".graphql",
    ".gql",
    ".sql",
    ".json",
    ".yml",
    ".yaml",
    ".js",
    ".ts",
    ".tsx",
    ".css",
    ".html",
}

EXCLUDE_DIRS = {".git", ".hg", ".svn", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}
MAX_FILE_BYTES = 128_000


def _iter_files(root: Path, include_exts: Set[str]) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in include_exts:
            continue
        yield path


def _read_text(path: Path) -> str | None:
    try:
        data = path.read_text(encoding="utf-8")
        return data if len(data.encode("utf-8")) <= MAX_FILE_BYTES * 4 else data
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="latin-1")
        except Exception:
            return None
    except Exception:
        return None


async def ingest_files(paths: List[Path], repo_root: Path, repo_path_hint: str, *, dry_run: bool, feature_enabled: bool, session_id: Optional[str]) -> None:
    for path in paths:
        rel = path.relative_to(repo_root).as_posix()
        content = _read_text(path)
        if content is None:
            print(f"[skip] {rel} (binary or unreadable)")
            continue
        if len(content) > MAX_FILE_BYTES:
            content = content[:MAX_FILE_BYTES]
        if dry_run or not feature_enabled:
            tag = "dry-run" if dry_run else "disabled"
            print(f"[{tag}] would ingest {rel}")
            continue
        await upsert_bootstrap_memory(
            rel_path=rel,
            content=content,
            language=None,
            repo_path=repo_path_hint,
            session_id=session_id,
        )
        print(f"[ingested] {rel}")


async def async_main(args: argparse.Namespace) -> None:
    feature_enabled = settings.workspace_memory_enabled
    if not feature_enabled and not args.dry_run:
        print("[warn] WORKSPACE_MEMORY_ENABLED=0; run with --dry-run or enable the feature to persist results.")
    repo_root = Path(args.root or settings.workspace_root).resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        raise SystemExit(f"Workspace root not found: {repo_root}")

    include_exts = {ext if ext.startswith(".") else f".{ext}" for ext in args.exts}
    paths = sorted(_iter_files(repo_root, include_exts))
    if not paths:
        print("No files matched the given extensions.")
        return

    await ingest_files(
        paths,
        repo_root,
        args.repo_path or repo_root.name,
        dry_run=args.dry_run,
        feature_enabled=feature_enabled,
        session_id=args.session_id,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap repository files into workspace memory")
    parser.add_argument("--root", help="Path to workspace root (defaults to settings.workspace_root)")
    parser.add_argument("--repo-path", help="Repo identifier stored with the memory (default: workspace folder name)")
    parser.add_argument("--ext", dest="exts", action="append", default=sorted(DEFAULT_EXTS),
                        help="File extension to include (can be provided multiple times). Default covers common text/code files.")
    parser.add_argument("--dry-run", action="store_true", help="List files without inserting records")
    parser.add_argument("--session-id", help="Associate all memories with this session identifier (UUID)")
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
