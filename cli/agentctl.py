from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

import httpx

DEFAULT_API_URL = os.getenv("API_URL", "http://localhost:8080").rstrip("/")
DEFAULT_API_KEY = os.getenv("API_KEY", "")
DEFAULT_TIMEOUT = float(os.getenv("AGENT_HTTP_TIMEOUT", "60"))
DEFAULT_POLL_INTERVAL = float(os.getenv("AGENT_POLL_INTERVAL", "1.5"))
DEFAULT_WAIT_TIMEOUT = float(os.getenv("AGENT_WAIT_TIMEOUT", "300"))
DEFAULT_REPO_PATH = "./workspace"
SUPPORTED_LANGUAGES = ("python", "java", "graphql")


class CLIError(RuntimeError):
    pass


def _pretty_json(data: Any) -> str:
    try:
        return json.dumps(data, indent=2, sort_keys=True)
    except Exception:
        return str(data)


def _sanitize_repo_path(value: Optional[str]) -> str:
    if not value:
        return DEFAULT_REPO_PATH
    s = str(value).strip().replace("\\", "/")
    if not s:
        return DEFAULT_REPO_PATH
    while s.startswith("./"):
        s = s[2:]
    s = s.strip("/")
    if not s or s == "." or s == "workspace":
        return DEFAULT_REPO_PATH
    if not s.startswith("workspace/"):
        s = f"workspace/{s}"
    return f"./{s}"


def _ensure_language(lang: Optional[str]) -> str:
    if not lang:
        return "python"
    lang_lc = str(lang).lower()
    if lang_lc not in SUPPORTED_LANGUAGES:
        raise CLIError(f"Unsupported language '{lang}'. Choose from {', '.join(SUPPORTED_LANGUAGES)}.")
    return lang_lc


class AgentClient:
    def __init__(self, base_url: str, api_key: str, timeout: float):
        headers = {"accept": "application/json"}
        if api_key:
            headers["x-api-key"] = api_key
        self._client = httpx.Client(base_url=base_url, headers=headers, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "AgentClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def submit_task(self, payload: Dict[str, Any]) -> str:
        try:
            resp = self._client.post("/v1/tasks", json=payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError as err:
            raise CLIError(f"Failed to submit task: HTTP {err.response.status_code} - {err.response.text}") from err
        except httpx.RequestError as err:
            raise CLIError(f"Failed to submit task: {err}") from err
        data = resp.json()
        task_id = data.get("task_id")
        if not task_id:
            raise CLIError(f"API response missing task_id: {_pretty_json(data)}")
        return str(task_id)

    def get_status(self, task_id: str) -> Dict[str, Any]:
        try:
            resp = self._client.get(f"/v1/tasks/{task_id}")
            resp.raise_for_status()
        except httpx.HTTPStatusError as err:
            raise CLIError(f"Failed to fetch status: HTTP {err.response.status_code} - {err.response.text}") from err
        except httpx.RequestError as err:
            raise CLIError(f"Failed to fetch status: {err}") from err
        return resp.json()

    def wait_for_final(self, task_id: str, poll_interval: float, timeout: float) -> Dict[str, Any]:
        deadline = time.time() + timeout if timeout > 0 else None
        while True:
            try:
                resp = self._client.get(f"/v1/tasks/{task_id}/final")
                if resp.status_code == 404:
                    if deadline and time.time() >= deadline:
                        raise CLIError(f"Timed out waiting for task {task_id}.")
                    time.sleep(poll_interval)
                    continue
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict):
                    data.setdefault("id", task_id)
                return data
            except httpx.HTTPStatusError as err:
                if err.response.status_code == 404:
                    if deadline and time.time() >= deadline:
                        raise CLIError(f"Timed out waiting for task {task_id}.")
                    time.sleep(poll_interval)
                    continue
                raise CLIError(f"Failed to fetch final result: HTTP {err.response.status_code} - {err.response.text}") from err
            except httpx.RequestError as err:
                if deadline and time.time() >= deadline:
                    raise CLIError(f"Timed out waiting for task {task_id}: {err}")
                time.sleep(poll_interval)

    def download_zip(self, zip_url: str, dest_dir: Path) -> Path:
        if not zip_url:
            raise CLIError("No zip URL provided.")
        parsed = urlparse(zip_url)
        if parsed.scheme and parsed.netloc:
            url = zip_url
            filename = Path(parsed.path).name
        else:
            url = zip_url if zip_url.startswith("/") else f"/{zip_url}"
            filename = Path(url).name
        if not filename:
            filename = f"{uuid.uuid4()}.zip"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / filename
        try:
            with self._client.stream("GET", url) as resp:
                resp.raise_for_status()
                with dest_path.open("wb") as fh:
                    for chunk in resp.iter_bytes():
                        fh.write(chunk)
        except httpx.HTTPStatusError as err:
            raise CLIError(f"Failed to download zip: HTTP {err.response.status_code} - {err.response.text}") from err
        except httpx.RequestError as err:
            raise CLIError(f"Failed to download zip: {err}") from err
        return dest_path

    def upload_memory(self, archive: Path, session_id: str, repo_path: Optional[str]) -> Dict[str, Any]:
        if not archive.is_file():
            raise CLIError(f"Attachment not found: {archive}")
        files = {"file": (archive.name, archive.read_bytes(), "application/zip")}
        data = {"session_id": session_id}
        if repo_path:
            data["repo_path"] = repo_path
        try:
            resp = self._client.post("/v1/memory/upload", files=files, data=data)
            resp.raise_for_status()
        except httpx.HTTPStatusError as err:
            raise CLIError(f"Upload failed for {archive}: HTTP {err.response.status_code} - {err.response.text}") from err
        except httpx.RequestError as err:
            raise CLIError(f"Upload failed for {archive}: {err}") from err
        return resp.json()

    def cancel_task(self, task_id: str) -> Dict[str, Any]:
        try:
            resp = self._client.post(f"/v1/tasks/{task_id}/cancel")
            resp.raise_for_status()
        except httpx.HTTPStatusError as err:
            raise CLIError(f"Failed to cancel task: HTTP {err.response.status_code} - {err.response.text}") from err
        except httpx.RequestError as err:
            raise CLIError(f"Failed to cancel task: {err}") from err
        return resp.json()

    def submit_feedback(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            resp = self._client.post("/v1/feedback", json=payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError as err:
            raise CLIError(f"Feedback failed: HTTP {err.response.status_code} - {err.response.text}") from err
        except httpx.RequestError as err:
            raise CLIError(f"Feedback failed: {err}") from err
        return resp.json()


def _build_chat_payload(
    message: str,
    language: str,
    repo_path: str,
    memory_ids: Iterable[str],
    session_id: str,
    max_tokens: int,
    latency_ms: int,
    conversation: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    conversation_entries = conversation if conversation is not None else [{"role": "user", "content": message}]
    return {
        "type": "DOC",
        "input": {
            "language": language,
            "frameworks": [],
            "repo": {"path": repo_path, "include": [], "exclude": []},
            "constraints": {"max_tokens": max_tokens, "latency_ms": latency_ms},
            "goal": message,
        },
        "metadata": {
            "mode_hint": "chat",
            "conversation": conversation_entries,
            "memory_context_ids": list(memory_ids),
            "session_id": session_id,
        },
        "output_contract": {"expected_files": []},
    }


def _build_code_payload(
    goal: str,
    language: str,
    repo_path: str,
    expected_files: Iterable[str],
    max_tokens: int,
    latency_ms: int,
    frameworks: Iterable[str],
    session_id: Optional[str],
) -> Dict[str, Any]:
    return {
        "type": "CODE",
        "input": {
            "language": language,
            "frameworks": list(frameworks),
            "repo": {"path": repo_path, "include": [], "exclude": []},
            "constraints": {"max_tokens": max_tokens, "latency_ms": latency_ms},
            "goal": goal,
        },
        "metadata": {
            "mode_hint": "code",
            "conversation": [{"role": "user", "content": goal}],
            **({"session_id": session_id} if session_id else {}),
        },
        "output_contract": {"expected_files": list(expected_files)},
    }


def _open_client(args: argparse.Namespace) -> AgentClient:
    return AgentClient(args.api_url, args.api_key, args.timeout)


def _extract_result_text(result: Dict[str, Any]) -> str:
    return (
        result.get("result")
        or result.get("content")
        or result.get("message")
        or result.get("note")
        or ""
    )


def _print_response(text: str, follow_up_steps: Optional[Iterable[str]]) -> None:
    if text:
        print(text)
    else:
        print("No textual response returned.")
    if follow_up_steps:
        steps = list(follow_up_steps)
        if steps:
            print("\nFollow-up steps:")
            for idx, step in enumerate(steps, start=1):
                print(f"  {idx}. {step}")
            print()


def _handle_result(
    client: AgentClient,
    task_id: str,
    result: Dict[str, Any],
    download_target: Optional[str],
) -> None:
    text = _extract_result_text(result)
    _print_response(text, result.get("follow_up_steps"))
    zip_url = result.get("zip_url")
    if download_target and zip_url:
        target_dir = Path(download_target)
        saved = client.download_zip(zip_url, target_dir)
        print(f"\nArtifacts saved to {saved}")
    elif zip_url:
        print(f"\nArtifacts available at: {zip_url} (use `agentctl download {task_id}` or --download)")


def cmd_chat(args: argparse.Namespace) -> None:
    language = _ensure_language(args.language)
    repo_path = _sanitize_repo_path(args.repo)
    attachments = [Path(p).expanduser() for p in args.attach]
    session_id = args.session or str(uuid.uuid4())
    memory_ids: List[str] = []

    with _open_client(args) as client:
        for archive in attachments:
            upload = client.upload_memory(archive, session_id=session_id, repo_path=None)
            session_id = upload.get("session_id", session_id)
            repo_path = upload.get("workspace_path") or repo_path
            memory_ids.extend(str(mem["id"]) for mem in upload.get("memories", []))
            print(f"Attached {archive.name} -> memory {memory_ids[-1] if memory_ids else 'n/a'} (session {session_id})")

        payload = _build_chat_payload(
            message=args.message,
            language=language,
            repo_path=repo_path,
            memory_ids=memory_ids,
            session_id=session_id,
            max_tokens=args.max_tokens,
            latency_ms=args.latency_ms,
        )
        task_id = client.submit_task(payload)
        print(f"Task {task_id} submitted.")
        if args.no_wait:
            return
        print("Waiting for completion…", file=sys.stderr)
        result = client.wait_for_final(task_id, args.poll_interval, args.wait_timeout)
        _handle_result(client, task_id, result, args.download)


def cmd_code(args: argparse.Namespace) -> None:
    language = _ensure_language(args.language)
    repo_path = _sanitize_repo_path(args.repo)
    payload = _build_code_payload(
        goal=args.goal,
        language=language,
        repo_path=repo_path,
        expected_files=args.expected_file,
        max_tokens=args.max_tokens,
        latency_ms=args.latency_ms,
        frameworks=args.framework,
        session_id=args.session,
    )
    with _open_client(args) as client:
        task_id = client.submit_task(payload)
        print(f"Task {task_id} submitted.")
        if args.no_wait:
            return
        print("Waiting for completion…", file=sys.stderr)
        result = client.wait_for_final(task_id, args.poll_interval, args.wait_timeout)
        _handle_result(client, task_id, result, args.download)


def cmd_submit(args: argparse.Namespace) -> None:
    with Path(args.file).expanduser().open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    with _open_client(args) as client:
        task_id = client.submit_task(payload)
        print(task_id)


def cmd_status(args: argparse.Namespace) -> None:
    with _open_client(args) as client:
        status = client.get_status(args.id)
    print(_pretty_json(status))


def cmd_cancel(args: argparse.Namespace) -> None:
    with _open_client(args) as client:
        response = client.cancel_task(args.id)
    print(_pretty_json(response))


def cmd_feedback(args: argparse.Namespace) -> None:
    with Path(args.file).expanduser().open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    with _open_client(args) as client:
        resp = client.submit_feedback(payload)
    print(_pretty_json(resp))


def cmd_download(args: argparse.Namespace) -> None:
    target_dir = Path(args.dest).expanduser()
    with _open_client(args) as client:
        zip_path = client.download_zip(f"/v1/tasks/{args.id}/zip" if args.id else args.url, target_dir)
    print(zip_path)


def cmd_upload(args: argparse.Namespace) -> None:
    archive = Path(args.archive).expanduser()
    session_id = args.session or str(uuid.uuid4())
    repo_path = args.repo
    with _open_client(args) as client:
        resp = client.upload_memory(archive, session_id=session_id, repo_path=repo_path)
    print(_pretty_json(resp))


def cmd_chat_session(args: argparse.Namespace) -> None:
    language = _ensure_language(args.language)
    repo_path = _sanitize_repo_path(args.repo)
    attachments = [Path(p).expanduser() for p in args.attach]
    session_id = args.session or str(uuid.uuid4())
    memory_ids: List[str] = []
    conversation: List[Dict[str, str]] = []
    last_zip_url: Optional[str] = None

    def show_banner() -> None:
        print("Interactive chat session commands:")
        print("  /exit or /quit            Exit the session")
        print("  /history                  Display conversation so far")
        print("  /reset                    Clear conversation history")
        print("  /attach <zip>             Upload and attach another archive")
        print("  /download [dir]           Download last artifact zip (uses --download if omitted)")
        print()

    with _open_client(args) as client:
        def attach_archive(path: Path) -> None:
            nonlocal session_id, repo_path, memory_ids
            upload = client.upload_memory(path, session_id=session_id, repo_path=None)
            session_id = upload.get("session_id", session_id)
            repo_path = upload.get("workspace_path") or repo_path
            new_ids = [str(mem["id"]) for mem in upload.get("memories", [])]
            memory_ids.extend(new_ids)
            if new_ids:
                print(f"Attached {path.name} -> memories {', '.join(new_ids)}")
            else:
                print(f"Attached {path.name} (no memory ids emitted)")

        for archive in attachments:
            try:
                attach_archive(archive)
            except CLIError as err:
                print(f"Attachment failed for {archive}: {err}")

        show_banner()
        while True:
            try:
                line = input("You> ").strip()
            except EOFError:
                print()
                break
            if not line:
                continue
            if line.startswith("/"):
                cmd, _, arg = line.partition(" ")
                cmd_lc = cmd.lower()
                if cmd_lc in ("/exit", "/quit"):
                    print("Session ended.")
                    break
                if cmd_lc == "/history":
                    if not conversation:
                        print("(history empty)")
                    else:
                        for idx, entry in enumerate(conversation, start=1):
                            role = entry.get("role", "unknown").capitalize()
                            content = entry.get("content", "")
                            print(f"{idx:02d} {role}: {content}")
                    continue
                if cmd_lc == "/reset":
                    conversation.clear()
                    print("Conversation cleared.")
                    continue
                if cmd_lc == "/attach":
                    if not arg:
                        print("Usage: /attach <path/to/archive.zip>")
                        continue
                    archive_path = Path(arg).expanduser()
                    try:
                        attach_archive(archive_path)
                    except CLIError as err:
                        print(f"Attachment failed: {err}")
                    continue
                if cmd_lc == "/download":
                    if not last_zip_url:
                        print("No artifact zip available yet.")
                        continue
                    target = arg or args.download or "workspace/zips"
                    try:
                        saved = client.download_zip(last_zip_url, Path(target))
                        print(f"Saved artifact to {saved}")
                    except CLIError as err:
                        print(f"Download failed: {err}")
                    continue
                print(f"Unknown command: {cmd}")
                continue

            conversation.append({"role": "user", "content": line})
            payload = _build_chat_payload(
                message=line,
                language=language,
                repo_path=repo_path,
                memory_ids=memory_ids,
                session_id=session_id,
                max_tokens=args.max_tokens,
                latency_ms=args.latency_ms,
                conversation=conversation,
            )
            try:
                task_id = client.submit_task(payload)
            except CLIError as err:
                print(f"Submit failed: {err}", file=sys.stderr)
                conversation.pop()
                continue

            print(f"[task {task_id}] waiting for reply…", file=sys.stderr)
            try:
                result = client.wait_for_final(task_id, args.poll_interval, args.wait_timeout)
            except CLIError as err:
                print(f"Task failed: {err}", file=sys.stderr)
                continue

            text = _extract_result_text(result)
            print()
            print("Assistant>")
            _print_response(text, result.get("follow_up_steps"))
            conversation.append({"role": "assistant", "content": text})

            zip_url = result.get("zip_url")
            if zip_url:
                last_zip_url = zip_url
                target_dir = args.download
                if target_dir:
                    try:
                        saved = client.download_zip(zip_url, Path(target_dir))
                        print(f"[Artifacts saved to {saved}]")
                    except CLIError as err:
                        print(f"[Artifact download failed: {err}]")
                else:
                    print(f"[Artifact available at: {zip_url}]")
            print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentctl", description="Command-line interface for the Multi-Agent Code System.")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help=f"API base URL (default: {DEFAULT_API_URL})")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="API key for authentication (env API_KEY).")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="HTTP timeout in seconds.")
    parser.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL, help="Polling interval when waiting for tasks.")
    parser.add_argument("--wait-timeout", type=float, default=DEFAULT_WAIT_TIMEOUT, help="Max seconds to wait for task completion (0 = no limit).")

    sub = parser.add_subparsers(dest="command", required=True)

    chat = sub.add_parser("chat", help="Send a chat-style request to the agent.")
    chat.add_argument("message", help="User message.")
    chat.add_argument("--language", choices=SUPPORTED_LANGUAGES, default="python", help="Programming language hint.")
    chat.add_argument("--repo", default=DEFAULT_REPO_PATH, help="Workspace repo path for context.")
    chat.add_argument("--attach", action="append", default=[], help="Zip archive to upload as context (repeatable).")
    chat.add_argument("--session", help="Reuse an existing upload session id.")
    chat.add_argument("--max-tokens", type=int, default=1024, help="Token budget hint.")
    chat.add_argument("--latency-ms", type=int, default=60000, help="Latency budget hint.")
    chat.add_argument("--download", nargs="?", const="workspace/zips", help="Directory to save the result zip (omit value to use workspace/zips).")
    chat.add_argument("--no-wait", action="store_true", help="Submit and return without waiting for completion.")
    chat.set_defaults(func=cmd_chat)

    code = sub.add_parser("code", help="Run a code-generation request.")
    code.add_argument("goal", help="Description of the code task.")
    code.add_argument("--language", choices=SUPPORTED_LANGUAGES, default="java", help="Primary language.")
    code.add_argument("--repo", default=DEFAULT_REPO_PATH, help="Workspace repo path for context.")
    code.add_argument("--expected-file", action="append", default=[], help="Expected file path (repeatable).")
    code.add_argument("--framework", action="append", default=[], help="Framework hint (repeatable).")
    code.add_argument("--session", help="Optional session id to associate with the task.")
    code.add_argument("--max-tokens", type=int, default=2048, help="Token budget hint.")
    code.add_argument("--latency-ms", type=int, default=120000, help="Latency budget hint.")
    code.add_argument("--download", nargs="?", const="workspace/zips", help="Directory to save the result zip (omit value to use workspace/zips).")
    code.add_argument("--no-wait", action="store_true", help="Submit and return without waiting for completion.")
    code.set_defaults(func=cmd_code)

    submit = sub.add_parser("submit", help="Submit a raw task JSON payload.")
    submit.add_argument("file", help="Path to JSON file.")
    submit.set_defaults(func=cmd_submit)

    status = sub.add_parser("status", help="Show status for a task id.")
    status.add_argument("id", help="Task id.")
    status.set_defaults(func=cmd_status)

    cancel = sub.add_parser("cancel", help="Cancel a running task.")
    cancel.add_argument("id", help="Task id.")
    cancel.set_defaults(func=cmd_cancel)

    feedback = sub.add_parser("feedback", help="Submit feedback JSON.")
    feedback.add_argument("file", help="Path to feedback JSON.")
    feedback.set_defaults(func=cmd_feedback)

    download = sub.add_parser("download", help="Download the zip for a task id or explicit URL.")
    group = download.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", help="Task id to download from /v1/tasks/{id}/zip.")
    group.add_argument("--url", help="Explicit zip URL.")
    download.add_argument("--dest", default="workspace/zips", help="Destination directory for the zip.")
    download.set_defaults(func=cmd_download)

    upload = sub.add_parser("upload", help="Upload a zip archive as workspace memory.")
    upload.add_argument("archive", help="Zip archive path.")
    upload.add_argument("--session", help="Session id to reuse (defaults to random UUID).")
    upload.add_argument("--repo", help="Optional repo label for staging.")
    upload.set_defaults(func=cmd_upload)

    chat_session = sub.add_parser("chat-session", help="Start an interactive chat loop.")
    chat_session.add_argument("--language", choices=SUPPORTED_LANGUAGES, default="python", help="Programming language hint.")
    chat_session.add_argument("--repo", default=DEFAULT_REPO_PATH, help="Workspace repo path for context.")
    chat_session.add_argument("--attach", action="append", default=[], help="Zip archive to upload before starting (repeatable).")
    chat_session.add_argument("--session", help="Reuse an existing upload session id.")
    chat_session.add_argument("--max-tokens", type=int, default=1024, help="Token budget hint.")
    chat_session.add_argument("--latency-ms", type=int, default=60000, help="Latency budget hint.")
    chat_session.add_argument("--download", nargs="?", const="workspace/zips", help="Auto-download artifact zips to this directory (omit value to use workspace/zips).")
    chat_session.set_defaults(func=cmd_chat_session)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except CLIError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nAborted by user.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
