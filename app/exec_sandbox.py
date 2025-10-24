from __future__ import annotations
import asyncio
from typing import List, Optional

ALLOWLIST = {
    "javac", "mvn", "gradlew", "./gradlew",
    "pytest", "ruff", "black", "node", "npm", "pnpm", "npx"
}

SAFE_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

class ExecResult:
    def __init__(self, returncode: int, stdout: str, stderr: str):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

async def run_sandboxed(cmd: List[str], cwd: Optional[str] = None, timeout: int = 60) -> ExecResult:
    if not cmd:
        return ExecResult(1, "", "empty command")
    tool = cmd[0]
    if tool not in ALLOWLIST:
        return ExecResult(1, "", f"tool '{tool}' not allowed")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            env={"PATH": SAFE_PATH},   # minimal, safe PATH so tools are found
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return ExecResult(124, "", "timeout")
        return ExecResult(proc.returncode, stdout.decode(), stderr.decode())
    except FileNotFoundError:
        return ExecResult(127, "", f"tool '{tool}' not found")
