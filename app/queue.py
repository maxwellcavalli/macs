from __future__ import annotations
from .bandit_client import record as bandit_record
import asyncio, time, json, textwrap, os, re, traceback
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
from fnmatch import fnmatch
from .sse import StreamHub
from .registry import available_models
from .db import get_engine, update_task_status
from .metrics import (
    router_route_count, compile_pass_total, test_smoke_pass_total,
    duel_selection_decisions_total, duel_rule_decisions_total
)
from sqlalchemy import text
from .llm.ollama_client import generate_stream, OllamaError
from .bandit import extract_features, feature_hash, upsert_stat, rank_models
from .duel_config import get_duel_config
from .exec_sandbox import run_sandboxed
from .build_java import build_and_test_java
from .logging_setup import get_logger
from .logctx import set_task_id, set_candidate
from .fs_sandbox import resolve_safe_path, WORKSPACE_ROOT
from .java_utils import fix_java_package, fix_java_filename
from .workspace_io import ensure_merge_tree

# additions
from .bandit_store import record_event as bandit_record_event
from .artifacts import write_result
from .zips import write_zip
from .memory import record_completion

log = get_logger("queue")

FENCE_RX = re.compile(r"^\s*```.*$")
PACKAGE_LINE_RX = re.compile(r"^\s*package\s+([a-zA-Z0-9_.]+)\s*;\s*$")

CODE_KEYWORDS = {
    "implement","fix","bug","refactor","function","class","module","api","endpoint",
    "write code","generate code","compile","build","test","unit test","integration test",
    "sql","schema","service","controller","handler","repository",
    "project","projects","skeleton","scaffold","structure","template","setup","zip","archive"
}
DOC_KEYWORDS = {"document","docs","documentation","explain","tutorial","guide","readme","summary","describe","notes"}
PLANNER_KEYWORDS = {"plan","outline","steps","strategy","roadmap","analysis","approach","design"}
CHAT_KEYWORDS = {"hello","hi","hey","greetings","thanks","how are","say","tell me","question","what is","who is","help me understand","conversation","chat"}

MODE_PREFERENCES = {
    "chat": [
        "llama3.1:8b-instruct-q4_K_M",
        "mistral:7b-instruct-q4_K_M",
        "gemma2:9b-instruct-q4_K_M",
    ],
    "docs": [
        "gemma2:9b-instruct-q4_K_M",
        "llama3.1:8b-instruct-q4_K_M",
        "mistral:7b-instruct-q4_K_M",
    ],
    "planner": [
        "deepseek-coder:6.7b-instruct-q4_K_M",
        "llama3.1:8b-instruct-q4_K_M",
        "mistral:7b-instruct-q4_K_M",
    ],
    "code": [
        "qwen2.5-coder:7b-instruct-q4_K_M",
        "deepseek-coder:6.7b-instruct-q4_K_M",
        "llama3.1:8b-instruct-q4_K_M",
        "mistral:7b-instruct-q4_K_M",
    ],
}

COMPONENT_SYNONYMS = {
    "repository": ("repository", "repositories", "repo interface", "data access object", "dao"),
    "service": ("service", "services", "application service"),
    "controller": ("controller", "controllers", "rest controller", "rest controllers", "api controller"),
    "entity": ("entity", "entities", "domain entity"),
    "dto": ("dto", "dtos", "data transfer object", "data transfer objects"),
}

COMPONENT_PLACEMENT = {
    "repository": {"folder": "repository", "keywords": ("repository", "repositories", "repo", "dao")},
    "service": {"folder": "service", "keywords": ("service", "services")},
    "controller": {"folder": "controller", "keywords": ("controller", "controllers")},
    "entity": {"folder": "entity", "keywords": ("entity", "entities", "model")},
    "dto": {"folder": "dto", "keywords": ("dto", "dtos")},
}

COMPONENT_ANNOTATIONS = {
    "repository": ("@repository", "@jdbcrepository"),
    "service": ("@service",),
    "controller": ("@restcontroller", "@controller"),
    "entity": ("@entity", "@table"),
    "dto": ("@value", "@data"),
}

COMPONENT_CLASS_HINTS = {
    "repository": ("repository", "dao"),
    "service": ("service",),
    "controller": ("controller", "resource"),
    "entity": ("entity", "model"),
    "dto": ("dto",),
}

CANDIDATE_TIMEOUT_SEC = int(os.getenv("CANDIDATE_TIMEOUT_SEC", "180"))
DUEL_TIMEOUT_SEC = int(os.getenv("DUEL_TIMEOUT_SEC", "120"))
FORCE_DUEL = (os.getenv("FORCE_DUEL", "0") or "0").lower() in ("1", "true", "yes")

ZIP_INCLUDE_REPO = (os.getenv("ZIP_INCLUDE_REPO", "1") or "1").lower() not in ("0", "false", "no", "")
ZIP_MAX_FILES = int(os.getenv("ZIP_MAX_FILES", "400"))
ZIP_MAX_BYTES = int(os.getenv("ZIP_MAX_BYTES", str(10 * 1024 * 1024)))
ZIP_MAX_FILE_BYTES = int(os.getenv("ZIP_MAX_FILE_BYTES", str(512 * 1024)))
ZIP_REPO_PREFIX = (os.getenv("ZIP_REPO_PREFIX", "") or "").strip()
ZIP_SKIP_SEGMENTS = tuple(
    seg.strip() for seg in (os.getenv(
        "ZIP_SKIP_SEGMENTS",
        ".git,.hg,.svn,.idea,.vscode,.gradle,.mvn,node_modules,dist,build,target,.pytest_cache,.ruff_cache,.tox,coverage,zips,.duel"
    ).split(",")) if seg.strip()
)
ZIP_SKIP_SUFFIXES = tuple(
    suf.strip() for suf in (os.getenv(
        "ZIP_SKIP_SUFFIXES",
        ".class,.jar,.war,.ear,.zip,.tar,.gz,.tgz,.xz,.png,.jpg,.jpeg,.gif,.bmp,.ico,.exe,.dll,.so,.dylib,.bin,.lock,.log"
    ).split(",")) if suf.strip()
)

CODE_BLOCK_RE = re.compile(r"```([\w.+-]*)\n([\s\S]*?)```", re.MULTILINE)
PATH_HINT_RE = re.compile(r"(?:^|\b)(?:file|path)\s*[:=]\s*([\w./\\-]+)", re.IGNORECASE)

def _sanitize_rel_path(path: str) -> str:
    path = path.strip().replace("\\", "/").lstrip("./")
    parts = [p for p in path.split("/") if p and p not in (".", "..")]
    return "/".join(parts) if parts else "output.txt"

def _extract_files_from_content(text: str) -> Dict[str, str]:
    files: Dict[str, str] = {}
    if not text:
        return files
    for match in CODE_BLOCK_RE.finditer(text):
        body = match.group(2)
        lines = body.splitlines()
        path = None
        while lines and not lines[0].strip():
            lines.pop(0)
        if lines:
            first = lines[0].strip()
            first = first.lstrip("*_`> ")
            first = first.replace("**", "").replace("`", "")
            m = PATH_HINT_RE.match(first)
            if m:
                path = _sanitize_rel_path(m.group(1))
                lines = lines[1:]
        if not path:
            context = text[:match.start()].splitlines()
            for line in reversed(context[-4:]):
                line_clean = line.strip().lstrip("*_`> ")
                line_clean = line_clean.replace("**", "").replace("`", "")
                m = PATH_HINT_RE.search(line_clean)
                if m:
                    path = _sanitize_rel_path(m.group(1))
                    break
        if not path:
            continue
        content = "\n".join(lines).rstrip() + "\n"
        files[path] = content
    return files

def _format_model_name(m: Dict[str, Any]) -> str:
    tag = (m.get("tag") or "").strip()
    if tag:
        return tag
    size = str(m.get("size", "")).lower()
    if not size:
        size_tag = ""
    elif size.endswith("b") or "-" in size:
        size_tag = size
    else:
        size_tag = f"{size}b"
    quant = m.get("quant", "")
    return f"{m.get('name')}:{size_tag}-{quant}".strip("-")

def _order_models_for_mode(mode: str, models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    prefs = MODE_PREFERENCES.get(mode, [])
    index = {tag: idx for idx, tag in enumerate(prefs)}
    def sort_key(m: Dict[str, Any]) -> Tuple[int, int]:
        tag = _format_model_name(m)
        return (index.get(tag, len(prefs)), int(m.get("speed_rank", 999)))
    return sorted(models, key=sort_key)

def _normalize_repo_rel(path: str) -> str:
    cleaned = str(path or "").strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    if cleaned.startswith("/"):
        cleaned = cleaned.lstrip("/")
    workspace_name = WORKSPACE_ROOT.name
    if cleaned == workspace_name:
        cleaned = ""
    elif cleaned.startswith(f"{workspace_name}/"):
        cleaned = cleaned[len(workspace_name)+1:]
    if not cleaned or cleaned == ".":
        return "."
    return cleaned

def _should_skip_repo_file(rel_posix: str, includes: List[str], excludes: List[str]) -> bool:
    rel_norm = rel_posix.replace("\\", "/")
    parts = [p for p in rel_norm.split("/") if p]
    if any(part in ZIP_SKIP_SEGMENTS for part in parts):
        return True
    if any(rel_norm.endswith(suf) for suf in ZIP_SKIP_SUFFIXES):
        return True
    if includes:
        if not any(fnmatch(rel_norm, pat) for pat in includes):
            return True
    if excludes and any(fnmatch(rel_norm, pat) for pat in excludes):
        return True
    return False

def _read_text_file(path: Path) -> str | None:
    try:
        size = path.stat().st_size
        if ZIP_MAX_FILE_BYTES and size > ZIP_MAX_FILE_BYTES:
            return None
    except Exception:
        pass
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="latin-1")
        except Exception:
            return None
    except Exception:
        return None

def _collect_repo_snapshot(job: Dict[str, Any]) -> Tuple[Dict[str, str], List[str]]:
    notes: List[str] = []
    if not ZIP_INCLUDE_REPO:
        return {}, notes
    repo = (job.get("input") or {}).get("repo") or {}
    repo_path_raw = repo.get("path")
    defaulted_path = False
    if not repo_path_raw:
        repo_path_raw = "."
        defaulted_path = True
    rel = _normalize_repo_rel(repo_path_raw)
    repo_dir, ok = resolve_safe_path(rel if rel != "." else ".")
    if not ok or not repo_dir.exists():
        notes.append(f"Repo snapshot skipped (path '{rel}' not accessible).")
        return {}, notes
    includes = [str(p).strip() for p in (repo.get("include") or []) if str(p).strip()]
    excludes = [str(p).strip() for p in (repo.get("exclude") or []) if str(p).strip()]
    base_parts: List[str] = []
    if ZIP_REPO_PREFIX:
        base_parts.append(ZIP_REPO_PREFIX)
    if rel not in (".", ""):
        base_parts.append(rel)
    base_prefix = "/".join(p.strip("/") for p in base_parts if p)
    collected: Dict[str, str] = {}
    total_bytes = 0
    file_count = 0
    try:
        for fs_path in sorted(repo_dir.rglob("*")):
            if not fs_path.is_file():
                continue
            rel_path = fs_path.relative_to(repo_dir).as_posix()
            if _should_skip_repo_file(rel_path, includes, excludes):
                continue
            text = _read_text_file(fs_path)
            if text is None:
                continue
            encoded = text.encode("utf-8", errors="ignore")
            size = len(encoded)
            if file_count >= ZIP_MAX_FILES or (ZIP_MAX_BYTES and total_bytes + size > ZIP_MAX_BYTES):
                notes.append(
                    f"Repo snapshot truncated at {file_count} files / {total_bytes} bytes "
                    f"(limits: {ZIP_MAX_FILES} files, {ZIP_MAX_BYTES} bytes)."
                )
                break
            if base_prefix:
                rel_key = f"{base_prefix}/{rel_path}" if rel_path else base_prefix
            else:
                rel_key = rel_path
            if not rel_key:
                continue
            collected[rel_key] = text
            total_bytes += size
            file_count += 1
    except Exception as exc:
        notes.append(f"Repo snapshot error: {exc}")
    if collected:
        if not notes:
            notes.append(f"Repo snapshot captured {file_count} files ({total_bytes} bytes).")
        if defaulted_path:
            notes.append("Repo snapshot defaulted to workspace root (no repo.path provided).")
    return collected, notes

def _collect_memory_context_files(job: Dict[str, Any]) -> Tuple[Dict[str, str], List[str]]:
    files: Dict[str, str] = {}
    notes: List[str] = []
    meta = job.get("metadata") or {}
    entries = meta.get("memory_context") or []
    if not isinstance(entries, list) or not entries:
        return files, notes
    for idx, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            continue
        mem_id = str(entry.get("id") or idx)
        base = f"memory/{idx:02d}_{mem_id}"
        summary = str(entry.get("summary") or "").strip()
        if summary:
            files.setdefault(f"{base}/SUMMARY.txt", summary if summary.endswith("\n") else summary + "\n")
        payload = entry.get("files")
        if not isinstance(payload, dict):
            notes.append(f"Memory {mem_id}: no file payload available.")
            continue
        file_map = payload.get("files") if isinstance(payload.get("files"), dict) else {}
        wrote_any = False
        if isinstance(file_map, dict):
            for rel, content in file_map.items():
                rel_sanitized = _sanitize_rel_path(str(rel)) or "memory.txt"
                body = str(content or "")
                if not body.endswith("\n"):
                    body += "\n"
                files.setdefault(f"{base}/files/{rel_sanitized}", body)
                wrote_any = True
        artifact_preview = payload.get("artifact_preview")
        artifact_rel = payload.get("artifact")
        if artifact_preview:
            rel_sanitized = _sanitize_rel_path(str(artifact_rel or "artifact.txt"))
            body = str(artifact_preview)
            if not body.endswith("\n"):
                body += "\n"
            files.setdefault(f"{base}/artifact/{rel_sanitized}", body)
            wrote_any = True
        if not wrote_any:
            notes.append(f"Memory {mem_id}: no readable files captured (may exceed limits or be binary).")
    if files and not notes:
        notes.append("Memory context files included in zip (truncated previews).")
    return files, notes

def _infer_mode(job: Dict[str, Any]) -> str:
    meta = job.get("metadata") or {}
    hint = str(meta.get("mode_hint") or meta.get("mode") or "").strip().lower()
    if hint in {"chat","code","docs","planner"}:
        return hint
    job_type = str(job.get("type", "")).upper()
    inp = job.get("input") or {}
    goal = str(inp.get("goal", "")).strip()
    goal_l = goal.lower()
    output_contract = job.get("output_contract") or {}
    expected = output_contract.get("expected_files") or []
    repo = inp.get("repo") or {}
    include = repo.get("include") or []
    code_structure = bool(expected or include)

    code_clues = (
        job_type in {"CODE", "TEST", "REFACTOR"}
        or code_structure
        or any(kw in goal_l for kw in CODE_KEYWORDS)
    )
    doc_clues = job_type == "DOC" or any(kw in goal_l for kw in DOC_KEYWORDS)
    planner_clues = job_type == "PLAN" or any(kw in goal_l for kw in PLANNER_KEYWORDS)
    chat_clues = (
        any(kw in goal_l for kw in CHAT_KEYWORDS)
        or (goal and len(goal.split()) <= 8 and not code_clues)
    )

    if code_clues and (doc_clues or planner_clues or chat_clues):
        return "clarify"
    if code_clues:
        return "code"
    if doc_clues and not planner_clues:
        return "docs"
    if planner_clues and not doc_clues:
        return "planner"
    if chat_clues:
        return "chat"
    if doc_clues:
        return "docs"
    if planner_clues:
        return "planner"
    return "chat"

def _clarify_message(job: Dict[str, Any]) -> str:
    goal = str((job.get("input") or {}).get("goal", "")).strip()
    snippet = goal if goal else "your request"
    return (
        f"I can either share a code example or answer in plain language. "
        f"Would you like me to provide code or a conversational reply for: \"{snippet}\"?"
    )

def _derive_java_pkg_class(rel_path: str) -> Tuple[str, str]:
    parts = rel_path.strip("/").split("/")
    try:
        idx = parts.index("java")
        pkg_parts = parts[idx+1:-1]
        cls = os.path.splitext(parts[-1])[0]
        pkg = ".".join(pkg_parts) if pkg_parts else ""
        return pkg, cls
    except ValueError:
        pkg_parts = parts[:-1]
        cls = os.path.splitext(parts[-1])[0] if parts else "Main"
        pkg = ".".join(p for p in pkg_parts if p not in ("src","main"))
        return pkg, cls

def _detect_requested_components(goal: str) -> List[str]:
    goal_l = goal.lower()
    found: List[str] = []
    for label, variants in COMPONENT_SYNONYMS.items():
        if any(v in goal_l for v in variants):
            found.append(label)
    seen = set()
    ordered: List[str] = []
    for label in found:
        if label in seen:
            continue
        seen.add(label)
        ordered.append(label)
    return ordered

def _collect_repo_include_hints(job: Dict[str, Any], limit: int = 4) -> List[str]:
    repo = (job.get("input") or {}).get("repo") or {}
    includes = repo.get("include") or []
    hints: List[str] = []
    for raw in includes:
        path = str(raw).strip()
        if not path:
            continue
        hints.append(path)
        if len(hints) >= limit:
            break
    return hints

def _infer_example_base_path(candidates: List[str], language: str, preferred_base: Optional[str] = None) -> str:
    if preferred_base:
        return preferred_base
    for path in candidates:
        path_str = str(path).strip()
        if not path_str:
            continue
        if "/" in path_str:
            return path_str.rsplit("/", 1)[0]
    defaults = {
        "java": "src/main/java/com/example/demo",
        "kotlin": "src/main/kotlin/com/example",
        "python": "app",
        "typescript": "src",
        "javascript": "src",
        "csharp": "src",
        "go": "internal",
    }
    return defaults.get(language.lower(), "src")

def _example_extension_for_language(language: str) -> str:
    mapping = {
        "java": "java",
        "kotlin": "kt",
        "python": "py",
        "typescript": "ts",
        "javascript": "js",
        "csharp": "cs",
        "go": "go",
    }
    return mapping.get(language.lower(), "txt")

def _fence_for_language(language: str) -> str:
    mapping = {
        "csharp": "csharp",
        "java": "java",
        "kotlin": "kotlin",
        "python": "python",
        "typescript": "typescript",
        "javascript": "javascript",
        "go": "go",
    }
    lang = mapping.get(language.lower(), "")
    return f"```{lang}" if lang else "```"

def _detect_existing_java_base(job: Dict[str, Any]) -> Optional[str]:
    repo = (job.get("input") or {}).get("repo") or {}
    repo_path_raw = repo.get("path")
    base_rel = _normalize_repo_rel(str(repo_path_raw)) if repo_path_raw else "."
    base_rel = base_rel or "."
    repo_root, ok = resolve_safe_path(base_rel if base_rel != "." else ".")
    if not ok:
        return None
    base_dir = repo_root / "src" / "main" / "java"
    if not base_dir.exists():
        return None
    candidates: List[str] = []
    try:
        for idx, java_file in enumerate(sorted(base_dir.rglob("*.java"))):
            if idx >= 400:
                break
            try:
                with java_file.open("r", encoding="utf-8") as fh:
                    for _ in range(30):
                        line = fh.readline()
                        if not line:
                            break
                        stripped = line.strip()
                        if stripped.startswith("package "):
                            pkg = stripped[len("package "):].split(";", 1)[0].strip()
                            if pkg:
                                path = f"src/main/java/{pkg.replace('.', '/')}"
                                candidates.append(path)
                            break
            except Exception:
                continue
    except Exception:
        return None
    if not candidates:
        sample = next(base_dir.rglob("*.java"), None)
        if sample is not None:
            try:
                rel_parent = sample.relative_to(repo_root).parent.as_posix()
                return rel_parent
            except Exception:
                return None
        return None
    candidates.sort(key=lambda p: (-len(p.split("/")), p))
    return candidates[0]

def _infer_component_from_path(rel_path: str) -> Optional[str]:
    rel_lower = rel_path.lower()
    for component, info in COMPONENT_PLACEMENT.items():
        folder = info["folder"].lower()
        token = f"/{folder}/"
        if token in rel_lower:
            return component
        if rel_lower.endswith(f"/{folder}") or rel_lower.endswith(f"/{folder}.java"):
            return component
    return None

def _extract_code_blocks(text: str) -> List[Tuple[str, str]]:
    blocks: List[Tuple[str, str]] = []
    if not text:
        return blocks
    for match in CODE_BLOCK_RE.finditer(text):
        lang = (match.group(1) or "").strip().lower()
        body = match.group(2)
        blocks.append((lang, body))
    return blocks

def _extract_type_name(code: str) -> Optional[str]:
    TYPE_RX = re.compile(r"\b(class|interface|record)\s+([A-Z][A-Za-z0-9_]*)")
    m = TYPE_RX.search(code)
    if m:
        return m.group(2)
    return None

def _detect_component_from_code(code: str, components: List[str]) -> Optional[str]:
    code_lower = code.lower()
    for component in components:
        for marker in COMPONENT_ANNOTATIONS.get(component, ()):
            if marker in code_lower:
                return component
    type_name = _extract_type_name(code) or ""
    type_lower = type_name.lower()
    for component in components:
        suffixes = COMPONENT_CLASS_HINTS.get(component, ())
        if any(type_lower.endswith(suf) for suf in suffixes if suf):
            return component
    for component in components:
        for keyword in COMPONENT_CLASS_HINTS.get(component, ()):
            if keyword and keyword in code_lower:
                return component
    return None

def _pascal_case(word: str) -> str:
    parts = re.findall(r"[a-z0-9]+", word.lower())
    if not parts:
        return "Domain"
    return "".join(part.capitalize() for part in parts)

def _infer_domain_entity(goal: str) -> str:
    goal_l = goal.lower()
    match = re.search(r"\b([\w]+)\s+table\b", goal_l)
    if match:
        return _pascal_case(match.group(1))
    for keyword in ("entity", "model", "resource"):
        match = re.search(r"\b([\w]+)\s+" + keyword + r"\b", goal_l)
        if match:
            return _pascal_case(match.group(1))
    for name in ("user","customer","account","order","product","task","item","project"):
        if name in goal_l:
            return _pascal_case(name)
    return "Domain"

def _component_class_name(base_entity: str, component: str) -> str:
    suffix_map = {
        "repository": "Repository",
        "service": "Service",
        "controller": "Controller",
        "entity": "",
        "dto": "Dto",
    }
    suffix = suffix_map.get(component, component.capitalize())
    name = base_entity
    if not suffix:
        return name
    return f"{name}{suffix}"

def _file_matches_component(stem: str, component: str) -> bool:
    info = COMPONENT_PLACEMENT.get(component)
    if not info:
        return False
    stem_l = stem.lower()
    return any(keyword in stem_l for keyword in info["keywords"])

def _apply_component_directory_hints(
    files_map: Dict[str, str],
    components: List[str],
    language: str,
    base_candidates: List[str],
    preferred_base: Optional[str],
) -> Dict[str, str]:
    if not files_map or not components:
        return files_map
    base_path = _infer_example_base_path(base_candidates, language, preferred_base)
    adjusted: List[Tuple[str, str]] = []
    for rel, data in files_map.items():
        new_rel = rel
        rel_norm = rel.lower()
        stem = Path(rel).stem.lower()
        for component in components:
            info = COMPONENT_PLACEMENT.get(component)
            if not info:
                continue
            folder = info["folder"]
            folder_norm = folder.lower()
            segments = rel_norm.split("/")
            if folder_norm in segments or rel_norm.startswith(f"{folder_norm}/") or f"/{folder_norm}/" in rel_norm:
                continue
            if not _file_matches_component(stem, component):
                continue
            dest_dir = base_path
            if dest_dir in ("", "."):
                dest_dir = folder
            else:
                dest_dir_norm = dest_dir.lower()
                if dest_dir_norm.endswith(folder_norm):
                    dest_dir = dest_dir
                else:
                    dest_dir = f"{dest_dir}/{folder}"
            filename = Path(rel).name or f"{stem}"
            new_rel = _sanitize_rel_path(f"{dest_dir}/{filename}")
            break
        adjusted.append((new_rel, data))
    return dict(adjusted)

def _assign_component_blocks(
    raw_output: str,
    components: List[str],
    language: str,
    base_candidates: List[str],
    base_entity: str,
    preferred_base: Optional[str],
) -> Dict[str, str]:
    blocks = _extract_code_blocks(raw_output)
    if not blocks or not components:
        return {}
    base_path = _infer_example_base_path(base_candidates, language, preferred_base)
    ext = _example_extension_for_language(language)
    assigned: Dict[str, str] = {}
    used_components: set[str] = set()
    for _, code in blocks:
        if not code.strip():
            continue
        component = _detect_component_from_code(code, components)
        if not component or component in used_components:
            continue
        class_name = _extract_type_name(code) or _component_class_name(base_entity, component)
        folder = COMPONENT_PLACEMENT.get(component, {}).get("folder", component)
        if base_path in ("", "."):
            rel = f"{folder}/{class_name}.{ext}"
        else:
            rel = f"{base_path}/{folder}/{class_name}.{ext}"
        sanitized = _sanitize_rel_path(rel)
        body = code.strip()
        if not body.endswith("\n"):
            body += "\n"
        assigned[sanitized] = body
        used_components.add(component)
    return assigned

def _rebase_component_paths(
    files_map: Dict[str, str],
    preferred_base: Optional[str],
    components: List[str],
    notes: Optional[List[str]] = None,
) -> Dict[str, str]:
    if not preferred_base or not components:
        return files_map
    base = preferred_base.rstrip("/")
    rebased: Dict[str, str] = {}
    for rel, data in files_map.items():
        component = _infer_component_from_path(rel)
        new_rel = rel
        if component in components:
            folder = COMPONENT_PLACEMENT.get(component, {}).get("folder", component)
            class_name = Path(rel).name
            new_rel = _sanitize_rel_path(f"{base}/{folder}/{class_name}")
            if notes is not None and new_rel != rel:
                notes.append(f"Adjusted {rel} -> {new_rel} to match existing package layout")
        if new_rel in rebased:
            existing = rebased[new_rel]
            if len(str(data)) > len(str(existing)):
                rebased[new_rel] = data
        else:
            rebased[new_rel] = data
    return rebased

def _default_component_path(
    component: str,
    base_candidates: List[str],
    language: str,
    base_entity: str,
    preferred_base: Optional[str],
) -> Tuple[str, str]:
    base_path = _infer_example_base_path(base_candidates, language, preferred_base)
    folder = COMPONENT_PLACEMENT.get(component, {}).get("folder", component)
    class_name = _component_class_name(base_entity, component)
    ext = _example_extension_for_language(language)
    if base_path in ("", "."):
        rel = f"{folder}/{class_name}.{ext}"
    else:
        rel = f"{base_path}/{folder}/{class_name}.{ext}"
    return _sanitize_rel_path(rel), class_name

def _path_to_java_package(rel_path: str) -> Optional[str]:
    prefixes = ("src/main/java/", "src/test/java/")
    for prefix in prefixes:
        if rel_path.startswith(prefix):
            tail = rel_path[len(prefix):]
            if "/" not in tail:
                return None
            pkg = tail.rsplit("/", 1)[0].replace("/", ".")
            return pkg
    return None

def _generate_placeholder_component(
    component: str,
    class_name: str,
    rel_path: str,
    language: str,
) -> str:
    lang = language.lower()
    if lang == "java":
        pkg = _path_to_java_package(rel_path)
        lines: List[str] = []
        if pkg:
            lines.append(f"package {pkg};")
            lines.append("")
        lines.append(f"public class {class_name} " + "{")
        lines.append("    // TODO: implement generated logic")
        lines.append("}")
        return "\n".join(lines) + "\n"
    # Generic placeholder for other languages
    return f"# TODO: implement {component} component ({class_name})\n"

def _component_coverage(files_map: Dict[str, str], components: List[str]) -> Tuple[Dict[str, bool], List[str]]:
    coverage: Dict[str, bool] = {c: False for c in components}
    for rel in files_map:
        rel_norm = rel.lower()
        stem = Path(rel).stem.lower()
        for component in components:
            info = COMPONENT_PLACEMENT.get(component)
            if not info:
                continue
            folder = info["folder"].lower()
            keywords = info["keywords"]
            if folder and (f"/{folder}/" in rel_norm or rel_norm.startswith(f"{folder}/") or rel_norm.endswith(f"/{folder}") or rel_norm == folder):
                coverage[component] = True
                continue
            if _file_matches_component(stem, component):
                coverage[component] = True
                continue
            if any(keyword in rel_norm for keyword in keywords):
                coverage[component] = True
    missing = [c for c, ok in coverage.items() if not ok]
    return coverage, missing

def _build_prompt(job: dict) -> str:
    mode = job.get("_mode", "code")
    inp = job.get("input") or {}
    goal = inp.get("goal", "Provide assistance.")
    frameworks = ", ".join(inp.get("frameworks", [])) or "none"
    expected_files = (job.get("output_contract") or {}).get("expected_files", [])

    if mode == "chat":
        meta = job.get("metadata") or {}
        history_items = []
        for entry in (meta.get("conversation") or [])[-6:]:
            role = entry.get("role", "user")
            content = str(entry.get("content", "")).strip()
            if not content:
                continue
            label = "User" if role == "user" else "Assistant"
            history_items.append(f"{label}: {content}")
        history_block = "\n".join(history_items)
        history_section = f"Conversation so far:\n{history_block}\n\n" if history_block else ""
        memory_snippets = []
        for idx, entry in enumerate(meta.get("memory_context") or [], start=1):
            summary = str(entry.get("summary") or "").strip()
            goal = str(entry.get("goal") or "").strip()
            model = str(entry.get("model") or "").strip()
            if not summary and not goal:
                continue
            snippet_lines = []
            header = f"{idx}. Prior task"
            if goal:
                header += f" (goal: {goal})"
            if model:
                header += f" [model: {model}]"
            snippet_lines.append(header)
            if summary:
                trimmed = summary[:800]
                snippet_lines.append(trimmed)
            memory_snippets.append("\n".join(snippet_lines))
        memory_section = f"Relevant prior completions:\n{chr(10).join(memory_snippets)}\n\n" if memory_snippets else ""
        return textwrap.dedent(f"""
        You are a friendly engineering assistant. Answer in natural language, keep responses concise, and avoid writing source code unless the user clearly asks for it.
        When the user requests code, files, scaffolds, or archives, emit the actual file contents. For every file:
          - Add a line 'File: relative/path.ext' (relative to project root).
          - Follow with a fenced code block containing the file body.
          - Do NOT reference external download links or say 'see attached zip'; provide the real content inline instead.
        {memory_section}{history_section}Latest user message: {goal}
        """).strip()

    if mode == "docs":
        return textwrap.dedent(f"""
        You are a senior developer advocate. Write a clear, structured explanation or documentation snippet that addresses the user's goal.
        Use concise paragraphs and bullet lists when helpful. Avoid generating executable code unless explicitly requested.

        Topic:
        {goal}
        """).strip()

    if mode == "planner":
        return textwrap.dedent(f"""
        You are a staff engineer preparing a plan. Produce a numbered list of actionable steps, dependencies, and considerations to tackle the user's request.
        Highlight risks or unknowns where relevant. Avoid writing full code implementations.

        Planning target:
        {goal}
        """).strip()

    # default: code mode
    lang = inp.get("language", "general")
    files_str = "\n".join(f"- {p}" for p in expected_files) if expected_files else "- (decide suitable path)"
    pkg_hint, cls_hint = _derive_java_pkg_class(expected_files[0]) if (expected_files and expected_files[0].endswith(".java")) else ("", "")
    repo_hints = _collect_repo_include_hints(job)
    repo_section = ""
    if repo_hints:
        repo_lines = "\n".join(f"    - {p}" for p in repo_hints)
        repo_section = f"Existing repository structure to mirror:\n{repo_lines}\n"

    components = _detect_requested_components(goal if isinstance(goal, str) else "")
    multi_section = ""
    if len(components) >= 2:
        base_candidates = expected_files or repo_hints
        base_path = _infer_example_base_path(base_candidates, lang)
        ext = _example_extension_for_language(lang)
        fence = _fence_for_language(lang)
        base_entity = _infer_domain_entity(goal if isinstance(goal, str) else "")
        example_lines: List[str] = []
        mandatory_lines: List[str] = []
        for label in components:
            folder = COMPONENT_PLACEMENT.get(label, {}).get("folder", label)
            class_name = _component_class_name(base_entity, label)
            if base_path in ("", "."):
                rel_example = f"{folder}/{class_name}.{ext}"
            else:
                rel_example = f"{base_path}/{folder}/{class_name}.{ext}"
            mandatory_lines.append(f"    - File: {rel_example}  ({label})")
            example_lines.extend([
                f"File: {rel_example}",
                fence,
                f"// {label} implementation goes here",
                "```",
            ])
        example_block = textwrap.indent("\n".join(example_lines), "    ")
        comp_list = ", ".join(components)
        multi_section = (
            f"Detected multi-component request ({comp_list}). Emit one `File:` block per component so each lives in its own source file and they share a consistent package.\n"
            "MANDATORY FILES:\n"
            f"{chr(10).join(mandatory_lines)}\n"
            "Assume the necessary frameworks (e.g., Spring Boot + R2DBC) are available; do NOT ask follow-up questions—just implement the best reasonable defaults.\n"
            "Example (do not include literally):\n"
            f"{example_block}\n"
            "    Replace the sample bodies with real implementations. Missing any of the mandatory files is considered incorrect.\n"
        )

    repo_section = f"{repo_section}" if repo_section else ""
    multi_section = f"{multi_section}" if multi_section else ""

    return textwrap.dedent(f"""
    You are a senior {lang} engineer. Task: {goal}
    Frameworks: {frameworks}
    Output requirements (first file is primary target):
    {files_str}
    Package: {pkg_hint if pkg_hint else "(decide reasonable)"}
    ClassName: {cls_hint if cls_hint else "(decide reasonable)"}
    {repo_section}{multi_section}

    CRITICAL OUTPUT FORMAT:
    - For every file you create, write a line 'File: relative/path.ext' followed immediately by a fenced code block containing the entire file contents.
    - Emit all required files directly; do NOT reference external URLs or say that a zip was generated.
    - If multiple directories are needed, encode them via the relative paths (e.g., File: src/main/java/App.java).
    - Return ONLY these file blocks (no extra commentary outside fences).
    - For Java: include a correct package line and a compilable type.
    - Prefer plain JDK APIs (no third-party).
    """).strip()

def _sanitize_java(code: str, rel_path: str) -> str:
    lines = code.splitlines()
    cleaned: List[str] = []
    for ln in lines:
        if FENCE_RX.match(ln): continue
        if ln.strip().startswith(("http://","https://")): continue
        if ln.strip().lower().startswith(("for more information","status ","error ","warning ")): continue
        cleaned.append(ln)
    code2 = "\n".join(cleaned).strip()
    pkg_expected, _ = _derive_java_pkg_class(rel_path)
    out_lines: List[str] = []
    saw_pkg = False
    for ln in code2.splitlines():
        if PACKAGE_LINE_RX.match(ln):
            saw_pkg = True
            out_lines.append(f"package {pkg_expected};" if pkg_expected else ln)
        else:
            out_lines.append(ln)
    code3 = "\n".join(out_lines)
    if pkg_expected and not saw_pkg:
        code3 = f"package {pkg_expected};\n{code3}"
    return code3.strip() + "\n"

def _tail(s: str, nbytes: int = 2000) -> str:
    if not s: return ""
    enc = s.encode("utf-8", errors="ignore")
    return enc[-nbytes:].decode("utf-8", errors="ignore")

class JobQueue:
    def __init__(self, hub: StreamHub):
        self.queue: asyncio.Queue[dict] = asyncio.Queue()
        self.hub = hub
        self._task = None
        # Track inflight tasks for cancel
        self._inflight: Dict[str, List[asyncio.Task]] = {}

    async def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._runner())

    async def submit(self, task: dict):
        await self.queue.put(task)

    async def cancel(self, task_id: str):
        tasks = self._inflight.pop(task_id, [])
        for t in tasks:
            if not t.done():
                t.cancel()
        await self.hub.publish(task_id, json.dumps({"status":"canceled"}))
        log.info("task.canceled", {"id": task_id, "canceled_children": len(tasks)})

    async def _write_primary(self, rel_path: str, candidate_dir: Path, generated: str) -> Path:
        rel_path = rel_path.lstrip("/").replace("..","_")
        target = candidate_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(generated if generated.strip() else "// (empty)\n", encoding="utf-8")
        return target

    def _write_artifact_safely(self, task_id: str, payload: Dict[str, Any]) -> None:
        try:
            root = write_result(str(task_id), payload)
            text = None
            for key in ("content", "text", "result"):
                val = payload.get(key)
                if isinstance(val, str) and val.strip():
                    text = val
                    break
            if text:
                target = Path(root) / "result.md"
                target.write_text(text, encoding="utf-8")
            notes = payload.get("zip_notes")
            if isinstance(notes, list) and notes:
                try:
                    (Path(root) / "zip-notes.txt").write_text("\n".join(str(n) for n in notes), encoding="utf-8")
                except Exception:
                    pass
        except Exception:
            pass

    async def _run_candidate_inner(self, job: dict, candidate: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        """Inner function that we can time-limit with wait_for."""
        model_str = _format_model_name(candidate)
        set_candidate(model_str)
        t0 = time.time()
        mode = job.get("_mode", "code")
        inp = job.get("input") or {}
        lang_hint = str(inp.get("language") or "general")
        goal_text = str(inp.get("goal") or "")
        components = _detect_requested_components(goal_text)
        base_entity = _infer_domain_entity(goal_text)
        repo_hints = _collect_repo_include_hints(job)
        existing_java_base = _detect_existing_java_base(job)

        # isolated dir
        from .governance import enforce_fs_write
        safe_model = model_str.replace("/", "_").replace(":", "_").replace("-", "_")
        rel_dir = f".duel/{task_id}/{safe_model}"
        dir_path, ok = resolve_safe_path(rel_dir)
        if not enforce_fs_write(ok, rel_dir):
            raise RuntimeError("Write outside workspace denied")
        dir_path.mkdir(parents=True, exist_ok=True)

        # target path
        expected = (job.get("output_contract") or {}).get("expected_files", []) or []
        if expected:
            rel_primary = expected[0]
        elif mode == "chat":
            rel_primary = "response.md"
        elif mode == "docs":
            rel_primary = "documentation.md"
        elif mode == "planner":
            rel_primary = "plan.md"
        else:
            rel_primary = "main.txt"

        # prompt + stream
        prompt = _build_prompt(job)
        ctx = int(candidate.get("ctx_size", 8192) or 8192)
        buf_parts: List[str] = []
        try:
            async for chunk in generate_stream(model_str, prompt, num_ctx=ctx, temperature=0.2):
                if "response" in chunk and not chunk.get("done"):
                    buf_parts.append(chunk["response"])
            generated = "".join(buf_parts).strip()
        except OllamaError as e:
            generated = f"// ollama error: {e}\n"
        except asyncio.CancelledError:
            raise
        except Exception as e:
            generated = f"// runtime error: {e}\n"

        # sanitize + write
        raw_output = generated
        if mode == "code" and rel_primary.endswith(".java"):
            to_write = _sanitize_java(raw_output, rel_primary)
        else:
            to_write = raw_output

        files_map = _extract_files_from_content(raw_output)
        if rel_primary in files_map:
            files_map[rel_primary] = to_write
        if not files_map:
            files_map = {rel_primary: to_write}
        elif rel_primary not in files_map:
            new_map: Dict[str, str] = {rel_primary: to_write}
            new_map.update(files_map)
            files_map = new_map

        component_notes: List[str] = []
        missing_components: List[str] = []
        follow_up_steps: List[str] = []
        if components:
            base_candidates = expected or repo_hints
            rebase_notes: List[str] = []
            files_map = _rebase_component_paths(files_map, existing_java_base, components, rebase_notes)
            component_notes.extend(rebase_notes)
            for note in rebase_notes:
                follow_up_steps.append(f"Review adjusted path: {note}")
            component_files = _assign_component_blocks(raw_output, components, lang_hint, base_candidates, base_entity, existing_java_base)
            if component_files:
                files_map.update(component_files)
                if rel_primary in files_map and rel_primary.endswith(".txt"):
                    files_map.pop(rel_primary, None)
            files_map = _rebase_component_paths(files_map, existing_java_base, components, component_notes)
            files_map = _apply_component_directory_hints(files_map, components, lang_hint, base_candidates, existing_java_base)
            files_map = _rebase_component_paths(files_map, existing_java_base, components, component_notes)
            _, missing_components = _component_coverage(files_map, components)
            if missing_components:
                component_notes.append("Missing component files for: " + ", ".join(missing_components))
                placeholder_added = False
                for comp in missing_components:
                    rel_path, cls_name = _default_component_path(comp, base_candidates, lang_hint, base_entity, existing_java_base)
                    if rel_path in files_map:
                        continue
                    placeholder = _generate_placeholder_component(comp, cls_name, rel_path, lang_hint)
                    files_map[rel_path] = placeholder
                    component_notes.append(f"Placeholder generated for {comp}")
                    follow_up_steps.append(f"Replace placeholder {rel_path} with full implementation.")
                    placeholder_added = True
                if placeholder_added:
                    if rel_primary in files_map and rel_primary.endswith(".txt"):
                        files_map.pop(rel_primary, None)
                    _, missing_components = _component_coverage(files_map, components)
                    if missing_components:
                        component_notes.append("Placeholders could not satisfy: " + ", ".join(missing_components))
                        follow_up_steps.append("Some components still missing after placeholder pass: " + ", ".join(missing_components))

        if components:
            primary_rel = next((rel for rel in files_map if rel.lower().endswith((".java", ".py", ".ts", ".js", ".cs", ".go"))), None)
            if not primary_rel:
                primary_rel = next(iter(files_map))
        else:
            primary_rel = next(iter(files_map))
        primary_path = await self._write_primary(primary_rel, dir_path, files_map[primary_rel])
        for rel, data in files_map.items():
            if rel == primary_rel:
                continue
            await self._write_primary(rel, dir_path, data)

        # Mirror generated files into workspace under the target repo path
        repo_spec = (job.get("input") or {}).get("repo") or {}
        repo_path_raw = repo_spec.get("path")
        if repo_path_raw:
            base_rel = _normalize_repo_rel(repo_path_raw)
        else:
            base_rel = "."

        normalized_files_map: Dict[str, str] = {}
        base_prefix = base_rel.rstrip("/") if base_rel not in (".", "") else ""

        for rel, data in files_map.items():
            dest_rel = rel if base_rel in (".", "") else f"{base_rel}/{rel}"
            dest_path, ok = resolve_safe_path(dest_rel)
            if not ok:
                continue
            try:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                text_payload = data if isinstance(data, str) else str(data)
                if text_payload and not text_payload.endswith("\n"):
                    text_payload = text_payload + "\n"
                dest_path.write_text(text_payload, encoding="utf-8")
                if dest_path.suffix.lower() == ".java":
                    fix_java_package(dest_path)
                    dest_path = fix_java_filename(dest_path)
            except Exception:
                pass
            trimmed_rel = rel
            if base_prefix and trimmed_rel.startswith(base_prefix + "/"):
                trimmed_rel = trimmed_rel[len(base_prefix) + 1 :]
            elif base_prefix and trimmed_rel == base_prefix:
                trimmed_rel = ""
            trimmed_rel = trimmed_rel or rel
            normalized_files_map[trimmed_rel] = data

        if normalized_files_map:
            files_map = normalized_files_map

        merge_rel, merge_root = ensure_merge_tree(str(task_id), base_rel)

        for rel, data in files_map.items():
            target = merge_root / rel
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                text_payload = data if isinstance(data, str) else str(data)
                if text_payload and not text_payload.endswith("\n"):
                    text_payload = text_payload + "\n"
                target.write_text(text_payload, encoding="utf-8")
                if target.suffix.lower() == ".java":
                    fix_java_package(target)
                    target = fix_java_filename(target)
            except Exception:
                pass

        try:
            response_path = merge_root / "response.md"
            response_payload = content if content is not None else ""
            response_path.write_text(response_payload, encoding="utf-8")
        except Exception:
            pass

        # Build & tests
        compile_pass = False
        test_pass = False
        out_tail = ""
        err_tail = ""
        tool_used = "maven"

        if mode == "code":
            if primary_path.suffix.lower() == ".java":
                c, t, o, e, tool = await build_and_test_java(dir_path)
                compile_pass, test_pass, out_tail, err_tail, tool_used = c, t, o, e, tool
            else:
                compile_pass = bool(to_write.strip())
                test_pass = False
                tool_used = candidate.get("tool", "code")
        else:
            compile_pass = bool(to_write.strip())
            test_pass = False
            tool_used = mode

        if compile_pass: compile_pass_total.inc()
        if test_pass:    test_smoke_pass_total.inc()

        latency_ms = int((time.time() - t0) * 1000)

        content = to_write if to_write is not None else ""
        zip_path = None
        zip_url = None
        zip_notes: List[str] = []
        zip_notes.extend(component_notes)
        follow_up_steps = list(dict.fromkeys(step for step in follow_up_steps if step.strip()))
        if component_notes and not follow_up_steps:
            follow_up_steps.append("Review generated components for alignment with existing codebase.")
        if follow_up_steps:
            zip_notes.append("Follow-up:")
            zip_notes.extend(f"- {step}" for step in follow_up_steps)
        try:
            zip_files: Dict[str, str] = {}
            for path in merge_root.rglob("*"):
                if not path.is_file():
                    continue
                rel_name = path.relative_to(merge_root).as_posix()
                try:
                    text_payload = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    text_payload = path.read_text(encoding="latin-1", errors="ignore")
                zip_files[rel_name] = text_payload
            if zip_files:
                zip_file = write_zip(str(task_id), zip_files)
                zip_path = str(zip_file)
                zip_url = f"/zips/{zip_file.name}"
        except Exception as exc:
            zip_path = None
            zip_url = None
            msg = str(exc)
            if msg:
                zip_notes.append(f"Zip assembly failed: {msg}")
            else:
                zip_notes.append("Zip assembly failed.")
        has_primary = bool(content.strip())
        has_zip = bool(zip_url)
        has_artifact = bool(str(primary_path))
        success_flag = bool(test_pass or compile_pass) and not missing_components
        __RET__ = {
            "model": model_str,
            "success": success_flag,
            "latency_ms": latency_ms,
            "speed_rank": int(candidate.get("speed_rank", 999)),
            "human_score": 0,
            "compile_pass": bool(compile_pass),
            "test_pass": bool(test_pass),
            "tool": tool_used,
            "logs": {"build_stdout_tail": out_tail, "build_stderr_tail": err_tail},
            "artifact": str(primary_path),
            "content": content,
            "zip_path": zip_path,
            "zip_url": zip_url,
            "files": files_map,
            "zip_notes": zip_notes,
            "pending_final": bool(missing_components) or not (has_primary or has_zip or has_artifact),
            "missing_components": missing_components,
            "follow_up_steps": follow_up_steps,
        }
        # --- Bandit autolog (inserted) ---
        try:
            from .bandit_client import record as bandit_record
            _wm = __RET__.get('winner_model') or __RET__.get('winner') or __RET__.get('model') or __RET__.get('chosen')
            _ws = (__RET__.get('winner_score') or __RET__.get('score_winner') or
                  __RET__.get('score') or __RET__.get('reward'))
            _lm = __RET__.get('loser_model') or __RET__.get('loser')
            _ls = __RET__.get('loser_score') or __RET__.get('score_loser')
            if _wm is not None and _ws is not None:
                bandit_record(str(_wm), float(_ws), True,  task_type='duel')
            if _lm is not None and _ls is not None:
                bandit_record(str(_lm), float(_ls), False, task_type='duel')
        except Exception:
            pass
        # --- end autolog ---
        return __RET__

    async def _run_candidate(self, job: dict, candidate: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        try:
            return await asyncio.wait_for(self._run_candidate_inner(job, candidate, task_id), timeout=CANDIDATE_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            log.warning("candidate.timeout", {"task_id": task_id, "model": _format_model_name(candidate), "timeout_sec": CANDIDATE_TIMEOUT_SEC})
            __RET__ = {
                "model": _format_model_name(candidate),
                "success": False,
                "latency_ms": CANDIDATE_TIMEOUT_SEC*1000,
                "speed_rank": int(candidate.get("speed_rank", 999)),
                "human_score": 0,
                "compile_pass": False,
                "test_pass": False,
                "tool": "timeout",
                "logs": {"build_stdout_tail": "", "build_stderr_tail": f"candidate timed out after {CANDIDATE_TIMEOUT_SEC}s"},
                "artifact": "",
                "content": "",
                "pending_final": False,
            }
            # --- Bandit autolog (inserted) ---
            try:
                from .bandit_client import record as bandit_record
                _wm = __RET__.get('winner_model') or __RET__.get('winner') or __RET__.get('model') or __RET__.get('chosen')
                _ws = (__RET__.get('winner_score') or __RET__.get('score_winner') or
                      __RET__.get('score') or __RET__.get('reward'))
                _lm = __RET__.get('loser_model') or __RET__.get('loser')
                _ls = __RET__.get('loser_score') or __RET__.get('score_loser')
                if _wm is not None and _ws is not None:
                    bandit_record(str(_wm), float(_ws), True,  task_type='duel')
                if _lm is not None and _ls is not None:
                    bandit_record(str(_lm), float(_ls), False, task_type='duel')
            except Exception:
                pass
            # --- end autolog ---
            return __RET__
        except asyncio.CancelledError:
            log.info("candidate.canceled", {"task_id": task_id, "model": _format_model_name(candidate)})
            raise

    def _score(self, r: Dict[str, Any], cfg: Dict[str, Any]) -> float:
        base = (cfg["success_weight"] * (1.0 if r["success"] else 0.0))
        test_bonus = float(cfg.get("test_pass_weight", 0.5)) * (1.0 if r.get("test_pass") else 0.0)
        return base + test_bonus - (cfg["latency_penalty_ms"] * float(r["latency_ms"])) + (cfg["human_score_weight"] * float(r.get("human_score", 0) or 0))

    async def _runner(self):
        eng = await get_engine()
        while True:
            job = await self.queue.get()
            id = job["id"]
            set_task_id(str(id))
            language = job["input"]["language"]
            mode = _infer_mode(job)
            job["_mode"] = mode
            self._inflight[str(id)] = []
            await self.hub.publish(str(id), json.dumps({"status":"running", "mode": mode}))

            if mode == "clarify":
                question = _clarify_message(job)
                self._write_artifact_safely(str(id), {
                    "status": "done",
                    "mode": "clarify",
                    "model": "router-clarify",
                    "content": question
                })
                try:
                    async with eng.begin() as conn:
                        await update_task_status(conn, id, "done", model_used="router-clarify", latency_ms=0)
                except Exception:
                    pass
                await self.hub.publish(str(id), json.dumps({
                    "status": "done",
                    "mode": "clarify",
                    "message": question,
                    "content": question,
                    "model": "router-clarify"
                }))
                self.queue.task_done()
                self._inflight.pop(str(id), None)
                continue

            feats = extract_features(job)
            fh = feature_hash(feats)

            duel_cfg = (job.get("routing_hints") or {})
            is_duel = bool(duel_cfg.get("duel") or duel_cfg.get("duel_candidates"))
            if mode in {"chat", "docs", "planner"}:
                is_duel = False

            language_hint: str | None = language
            if mode == "chat":
                language_hint = None
            elif mode == "docs":
                language_hint = "docs"
            elif mode == "planner":
                language_hint = "planner"

            force_duel = bool((job.get("metadata") or {}).get("force_duel")) or FORCE_DUEL
            if force_duel:
                is_duel = True

            try:
                if not is_duel:
                    base_models = available_models(language_hint)
                    base = _order_models_for_mode(mode, base_models)
                    async with eng.connect() as conn:
                        ordered = await rank_models(conn, base, fh)
                    m = ordered[0] if ordered else None
                    if not m:
                        raise RuntimeError("no available models")
                    t = asyncio.create_task(self._run_candidate(job, m, str(id)))
                    self._inflight[str(id)].append(t)
                    res = await t
                    reward = 1.0 if res.get("test_pass") else (0.5 if res.get("compile_pass") else 0.0)

                    # bandit: log real single-run reward
                    try:
                        bandit_record_event(res.get("model") or "unknown", float(reward), {"src":"queue","task_id": str(id),"mode":"single"})
                    except Exception:
                        pass

                    async with eng.begin() as conn:
                        await update_task_status(conn, id, "done", model_used=res.get("model"), latency_ms=res.get("latency_ms"))
                        await upsert_stat(conn, res["model"], fh, reward)

                    # artifact for SSE completion
                    self._write_artifact_safely(str(id), {
                        "status":"done","mode":"single",
                        "model":res.get("model"), "latency_ms":res.get("latency_ms"),
                        "compile_pass":res.get("compile_pass"), "test_pass":res.get("test_pass"),
                        "tool":res.get("tool"), "artifact":res.get("artifact"), "logs":res.get("logs"),
                        "content": res.get("content"),
                        "zip_url": res.get("zip_url"),
                        "zip_notes": res.get("zip_notes"),
                    })

                    await self.hub.publish(str(id), json.dumps({
                        "status":"done",
                        "model":res.get("model"), "latency_ms":res.get("latency_ms"),
                        "compile_pass":res.get("compile_pass"), "test_pass":res.get("test_pass"),
                        "tool":res.get("tool"), "artifact":res.get("artifact"), "logs":res.get("logs"),
                        "content": res.get("content"),
                        "zip_url": res.get("zip_url"),
                        "zip_notes": res.get("zip_notes"),
                        "pending_final": bool(res.get("pending_final")),
                    }))
                    try:
                        res["status"] = res.get("status") or "done"
                    except Exception:
                        pass
                    try:
                        await record_completion(str(id), job, res)
                    except Exception:
                        pass
                else:
                    cand_names: List[str] = duel_cfg.get("duel_candidates") or []
                    reg_models = _order_models_for_mode(mode, available_models(language_hint))
                    name_map = { _format_model_name(m): m for m in reg_models }
                    candidates = [name_map[s] for s in cand_names if s in name_map] if cand_names else reg_models[:2]
                    async with eng.connect() as conn:
                        ordered = await rank_models(conn, candidates, fh)
                    if len(ordered) < 2:
                        # fallback to single
                        m = ordered[0] if ordered else (reg_models[0] if reg_models else None)
                        t = asyncio.create_task(self._run_candidate(job, m, str(id)))
                        self._inflight[str(id)].append(t)
                        res = await t
                        reward = 1.0 if res.get("test_pass") else (0.5 if res.get("compile_pass") else 0.0)
                        async with eng.begin() as conn:
                            await update_task_status(conn, id, "done", model_used=res.get("model"), latency_ms=res.get("latency_ms"))
                            await upsert_stat(conn, res["model"], fh, reward)

                        # artifact
                        self._write_artifact_safely(str(id), {
                            "status":"done","mode":"single",
                            "model":res.get("model"), "latency_ms":res.get("latency_ms"),
                            "compile_pass":res.get("compile_pass"), "test_pass":res.get("test_pass"),
                            "tool":res.get("tool"), "artifact":res.get("artifact"), "logs":res.get("logs"),
                            "content": res.get("content"),
                            "zip_url": res.get("zip_url"),
                            "zip_notes": res.get("zip_notes"),
                        })

                        await self.hub.publish(str(id), json.dumps({
                            "status":"done",
                            "model":res.get("model"),
                            "latency_ms":res.get("latency_ms"),
                            "compile_pass":res.get("compile_pass"),
                            "test_pass":res.get("test_pass"),
                            "tool":res.get("tool"),
                            "artifact":res.get("artifact"),
                            "logs":res.get("logs"),
                            "content": res.get("content"),
                            "zip_url": res.get("zip_url"),
                            "zip_notes": res.get("zip_notes"),
                            "pending_final": bool(res.get("pending_final")),
                        }))
                        try:
                            res["status"] = res.get("status") or "done"
                        except Exception:
                            pass
                        try:
                            await record_completion(str(id), job, res)
                        except Exception:
                            pass
                        self.queue.task_done()
                        self._inflight.pop(str(id), None)
                        continue

                    a_meta, b_meta = ordered[0], ordered[1]
                    a_name, b_name = _format_model_name(a_meta), _format_model_name(b_meta)
                    router_route_count.labels(model=a_name, language=language).inc()
                    router_route_count.labels(model=b_name, language=language).inc()
                    await self.hub.publish(str(id), json.dumps({"phase":"duel","candidate":a_name,"status":"running"}))
                    await self.hub.publish(str(id), json.dumps({"phase":"duel","candidate":b_name,"status":"running"}))

                    # run both with a global duel timeout
                    ta = asyncio.create_task(self._run_candidate(job, a_meta, str(id)))
                    tb = asyncio.create_task(self._run_candidate(job, b_meta, str(id)))
                    self._inflight[str(id)].extend([ta, tb])

                    try:
                        a_res, b_res = await asyncio.wait_for(asyncio.gather(ta, tb), timeout=DUEL_TIMEOUT_SEC)
                    except asyncio.TimeoutError:
                        log.warning("duel.timeout", {"task_id": str(id), "timeout_sec": DUEL_TIMEOUT_SEC})
                        # cancel any still-running tasks
                        for t in (ta, tb):
                            if not t.done(): t.cancel()
                        # gather partials
                        done = []
                        for t in (ta, tb):
                            try:
                                done.append(await t)
                            except asyncio.CancelledError:
                                done.append({"model": a_name if t is ta else b_name, "success": False, "latency_ms": DUEL_TIMEOUT_SEC*1000,
                                             "compile_pass": False, "test_pass": False, "tool": "timeout", "logs": {"build_stdout_tail":"","build_stderr_tail":"duel timed out"}, "artifact": ""})
                        a_res, b_res = done

                    await self.hub.publish(str(id), json.dumps({
                        "phase":"duel","candidate":a_res["model"],"status":"done",
                        "metrics":{"success":a_res["success"],"latency_ms":a_res["latency_ms"],"compile_pass":a_res["compile_pass"],"test_pass":a_res["test_pass"]},
                        "tool":a_res["tool"], "artifact":a_res["artifact"], "logs":a_res["logs"],
                        "content": a_res.get("content"),
                        "zip_url": a_res.get("zip_url"),
                        "zip_notes": a_res.get("zip_notes"),
                        "pending_final": bool(a_res.get("pending_final")),
                    }))
                    await self.hub.publish(str(id), json.dumps({
                        "phase":"duel","candidate":b_res["model"],"status":"done",
                        "metrics":{"success":b_res["success"],"latency_ms":b_res["latency_ms"],"compile_pass":b_res["compile_pass"],"test_pass":b_res["test_pass"]},
                        "tool":b_res["tool"], "artifact":b_res["artifact"], "logs":b_res["logs"],
                        "content": b_res.get("content"),
                        "zip_url": b_res.get("zip_url"),
                        "zip_notes": b_res.get("zip_notes"),
                        "pending_final": bool(b_res.get("pending_final")),
                    }))

                    cfg = get_duel_config()
                    def score(r):
                        base = (cfg["success_weight"] * (1.0 if r["success"] else 0.0))
                        test_bonus = float(cfg.get("test_pass_weight", 0.5)) * (1.0 if r.get("test_pass") else 0.0)
                        return base + test_bonus - (cfg["latency_penalty_ms"] * float(r["latency_ms"])) + (cfg["human_score_weight"] * float(r.get("human_score",0) or 0))
                    winner, loser = (a_res, b_res) if score(a_res) >= score(b_res) else (b_res, a_res)

                    duel_selection_decisions_total.labels(winner=winner["model"], loser=loser["model"]).inc()
                    duel_rule_decisions_total.labels(rule_version=str(cfg.get("rule_version","v1"))).inc()

                    reward_w = 1.0 if winner.get("test_pass") else (0.5 if winner.get("compile_pass") else 0.0)
                    reward_l = 1.0 if loser.get("test_pass") else (0.5 if loser.get("compile_pass") else 0.0)
                    # bandit: persist duel outcome (winner & loser)
                    try:
                        bandit_record(winner.get('model') or 'unknown', float(reward_w), True,  task_type='duel')
                        bandit_record(loser.get('model')  or 'unknown', float(reward_l), False, task_type='duel')
                    except Exception:
                        pass

                    # bandit: log duel rewards (winner & loser)
                    try:
                        bandit_record_event(winner.get("model") or "unknown", float(reward_w), {"src":"queue","task_id": str(id),"mode":"duel","role":"winner","opponent": (loser.get("model") or "unknown")})
                        bandit_record_event(loser.get("model") or "unknown", float(reward_l), {"src":"queue","task_id": str(id),"mode":"duel","role":"loser","opponent": (winner.get("model") or "unknown")})
                    except Exception:
                        pass

                    async with eng.begin() as conn:
                        await update_task_status(conn, id, "done", model_used=winner["model"], latency_ms=min(a_res["latency_ms"], b_res["latency_ms"]))
                        await conn.execute(text("""INSERT INTO rewards (id, task_id, model, success, latency_ms, human_score)
                                                   VALUES (gen_random_uuid(), :tid, :m1, :s1, :l1, NULL)"""),
                                           dict(tid=str(id), m1=winner["model"], s1=bool(winner["success"]), l1=int(winner["latency_ms"])))
                        await conn.execute(text("""INSERT INTO rewards (id, task_id, model, success, latency_ms, human_score)
                                                   VALUES (gen_random_uuid(), :tid, :m2, :s2, :l2, NULL)"""),
                                           dict(tid=str(id), m2=loser["model"], s2=bool(loser["success"]), l2=int(loser["latency_ms"])))
                        await upsert_stat(conn, winner["model"], fh, reward_w)
                        await upsert_stat(conn, loser["model"], fh, reward_l)

                    winner_has_final = bool(str(winner.get("content") or "").strip()) or bool(winner.get("zip_url")) or bool(winner.get("artifact"))

                    # artifact for duel completion
                    self._write_artifact_safely(str(id), {
                        "status":"done","mode":"duel",
                        "winner": winner["model"], "loser": loser["model"],
                        "rule_version": str(cfg.get("rule_version","v1")),
                        "winner_metrics":{"success":winner["success"], "latency_ms":winner["latency_ms"],
                                          "compile_pass":winner["compile_pass"], "test_pass":winner["test_pass"], "tool":winner["tool"]},
                        "loser_metrics":{"success":loser["success"], "latency_ms":loser["latency_ms"],
                                         "compile_pass":loser["compile_pass"], "test_pass":loser["test_pass"], "tool":loser["tool"]},
                        "content": winner.get("content"),
                        "zip_url": winner.get("zip_url"),
                        "zip_notes": winner.get("zip_notes"),
                    })

                    await self.hub.publish(str(id), json.dumps({
                        "status":"done",
                        "winner": winner["model"], "loser": loser["model"],
                        "rule_version": str(cfg.get("rule_version","v1")),
                        "winner_metrics":{"success":winner["success"], "latency_ms":winner["latency_ms"],
                                          "compile_pass":winner["compile_pass"], "test_pass":winner["test_pass"], "tool":winner["tool"]},
                        "loser_metrics":{"success":loser["success"], "latency_ms":loser["latency_ms"],
                                         "compile_pass":loser["compile_pass"], "test_pass":loser["test_pass"], "tool":loser["tool"]},
                        "content": winner.get("content"),
                        "zip_url": winner.get("zip_url"),
                        "zip_notes": winner.get("zip_notes"),
                        "pending_final": not winner_has_final,
                    }))
                    try:
                        winner_payload = dict(winner)
                        winner_payload.setdefault("status", "done")
                        winner_payload.setdefault("mode", "duel")
                        winner_payload.setdefault("pending_final", not winner_has_final)
                        await record_completion(str(id), job, winner_payload)
                    except Exception:
                        pass
            except asyncio.CancelledError:
                # task canceled
                async with eng.begin() as conn:
                    await update_task_status(conn, id, "canceled", model_used=None)
                await self.hub.publish(str(id), json.dumps({"status":"canceled"}))
                log.info("task.cancelled", {"id": str(id)})
            except Exception as e:
                err_summary = (str(e) or "").strip()
                if not err_summary:
                    err_summary = " ".join(str(x) for x in (getattr(e, "args", []) or []) if x) or e.__class__.__name__
                trace_txt = "".join(traceback.format_exception(type(e), e, e.__traceback__)).strip()
                if len(trace_txt) > 6000:
                    trace_txt = trace_txt[-6000:]
                async with eng.begin() as conn:
                    await update_task_status(conn, id, "error", model_used=None, error=err_summary)
                await self.hub.publish(str(id), json.dumps({
                    "status":"error",
                    "error": err_summary,
                    "traceback": trace_txt
                }))
                log.exception("task.error", {"id": str(id), "error": err_summary})
            finally:
                self._inflight.pop(str(id), None)
                self.queue.task_done()


# --- Bandit autolog helper (call this where you compute duel results) ---
def bandit_autolog(winner_model, winner_score, loser_model, loser_score, task_type="duel"):
    try:
        from .bandit_client import record as bandit_record
        bandit_record(str(winner_model), float(winner_score), True,  task_type=task_type)
        bandit_record(str(loser_model),  float(loser_score),  False, task_type=task_type)
    except Exception:
        pass
# --- end helper ---
