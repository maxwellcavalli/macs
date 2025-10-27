from __future__ import annotations
from .bandit_client import record as bandit_record
import asyncio, time, json, textwrap, os, re, traceback
from typing import Dict, Any, List, Tuple
from pathlib import Path
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

# additions
from .bandit_store import record_event as bandit_record_event
from .artifacts import write_result
from .zips import write_zip

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

CANDIDATE_TIMEOUT_SEC = int(os.getenv("CANDIDATE_TIMEOUT_SEC", "180"))
DUEL_TIMEOUT_SEC = int(os.getenv("DUEL_TIMEOUT_SEC", "120"))

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
            m = PATH_HINT_RE.match(first)
            if m:
                path = _sanitize_rel_path(m.group(1))
                lines = lines[1:]
        if not path:
            context = text[:match.start()].splitlines()
            for line in reversed(context[-4:]):
                m = PATH_HINT_RE.search(line)
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
        return textwrap.dedent(f"""
        You are a friendly engineering assistant. Answer in natural language, keep responses concise, and avoid writing source code unless the user clearly asks for it.
        When the user requests code, files, scaffolds, or archives, emit the actual file contents. For every file:
          - Add a line 'File: relative/path.ext' (relative to project root).
          - Follow with a fenced code block containing the file body.
          - Do NOT reference external download links or say 'see attached zip'; provide the real content inline instead.
        {history_section}Latest user message: {goal}
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
    return textwrap.dedent(f"""
    You are a senior {lang} engineer. Task: {goal}
    Frameworks: {frameworks}
    Output requirements (first file is primary target):
    {files_str}
    Package: {pkg_hint if pkg_hint else "(decide reasonable)"}
    ClassName: {cls_hint if cls_hint else "(decide reasonable)"}

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
        except Exception:
            pass

    async def _run_candidate_inner(self, job: dict, candidate: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        """Inner function that we can time-limit with wait_for."""
        model_str = _format_model_name(candidate)
        set_candidate(model_str)
        t0 = time.time()
        mode = job.get("_mode", "code")

        # isolated dir
        from .fs_sandbox import resolve_safe_path
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

        primary_rel = next(iter(files_map))
        primary_path = await self._write_primary(primary_rel, dir_path, files_map[primary_rel])
        for rel, data in files_map.items():
            if rel == primary_rel:
                continue
            await self._write_primary(rel, dir_path, data)

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
        try:
            zip_files = dict(files_map)
            zip_files.setdefault("response.md", content if content is not None else "")
            if any(v.strip() for v in zip_files.values()):
                zip_file = write_zip(str(task_id), zip_files)
                zip_path = str(zip_file)
                zip_url = f"/zips/{zip_file.name}"
        except Exception:
            zip_path = None
            zip_url = None
        __RET__ = {
            "model": model_str,
            "success": bool(test_pass or compile_pass),
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
            "zip_url": zip_url
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
                "content": ""
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
                        "zip_url": res.get("zip_url")
                    })

                    await self.hub.publish(str(id), json.dumps({
                        "status":"done",
                        "model":res.get("model"), "latency_ms":res.get("latency_ms"),
                        "compile_pass":res.get("compile_pass"), "test_pass":res.get("test_pass"),
                        "tool":res.get("tool"), "artifact":res.get("artifact"), "logs":res.get("logs"),
                        "content": res.get("content"),
                        "zip_url": res.get("zip_url")
                    }))
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
                            "zip_url": res.get("zip_url")
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
                            "zip_url": res.get("zip_url")
                        }))
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
                        "zip_url": a_res.get("zip_url")
                    }))
                    await self.hub.publish(str(id), json.dumps({
                        "phase":"duel","candidate":b_res["model"],"status":"done",
                        "metrics":{"success":b_res["success"],"latency_ms":b_res["latency_ms"],"compile_pass":b_res["compile_pass"],"test_pass":b_res["test_pass"]},
                        "tool":b_res["tool"], "artifact":b_res["artifact"], "logs":b_res["logs"],
                        "content": b_res.get("content"),
                        "zip_url": b_res.get("zip_url")
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
                        "zip_url": winner.get("zip_url")
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
                        "zip_url": winner.get("zip_url")
                    }))
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
