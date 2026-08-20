"""Portable process execution abstraction.

Core never calls taskkill/pwsh/cmd/bash directly. Providers depend on this
abstraction; Windows/Posix specifics live in the concrete executors.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
import os
import sys
import time
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclasses.dataclass(slots=True, frozen=True)
class ProcessSpec:
    argv: list[str]
    cwd: Path | None = None
    env: dict[str, str] | None = None
    timeout_seconds: float | None = None
    stdin_text: str | None = None


@dataclasses.dataclass(slots=True, frozen=True)
class ProcessResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    duration_ms: int = 0
    truncated: bool = False


class ProcessExecutor(Protocol):
    async def run(self, spec: ProcessSpec) -> ProcessResult: ...

    async def terminate(self, pid: int) -> None: ...


def _truncate(text: str, limit: int = 200_000) -> tuple[str, bool]:
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text, False
    return data[:limit].decode("utf-8", errors="replace"), True


async def _run_subprocess(spec: ProcessSpec) -> ProcessResult:
    started = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *spec.argv,
        cwd=str(spec.cwd) if spec.cwd else None,
        env=spec.env,
        stdin=asyncio.subprocess.PIPE if spec.stdin_text is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if proc.stdout is None or proc.stderr is None:
        raise RuntimeError("process pipes unavailable")
    timeout = spec.timeout_seconds
    try:
        stdin_bytes = spec.stdin_text.encode() if spec.stdin_text is not None else None
        if stdin_bytes is not None and proc.stdin is not None:
            proc.stdin.write(stdin_bytes)
            await proc.stdin.drain()
            proc.stdin.close()
        stdout_b, stderr_b = await (
            asyncio.wait_for(proc.communicate(), timeout=timeout) if timeout else proc.communicate()
        )
        timed_out = False
    except TimeoutError:
        await PortableSubprocessExecutor().terminate(proc.pid or 0)
        stdout_b, stderr_b = b"", b"provider timed out"
        timed_out = True
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(proc.wait(), timeout=5)
    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    duration_ms = int((time.monotonic() - started) * 1000)
    stdout, trunc_out = _truncate(stdout)
    stderr, trunc_err = _truncate(stderr)
    return ProcessResult(
        exit_code=proc.returncode or (124 if timed_out else 0),
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        duration_ms=duration_ms,
        truncated=trunc_out or trunc_err,
    )


class PortableSubprocessExecutor:
    """Cross-platform executor using asyncio subprocess; tree kill is best-effort."""

    async def run(self, spec: ProcessSpec) -> ProcessResult:
        return await _run_subprocess(spec)

    async def terminate(self, pid: int) -> None:
        if pid <= 0:
            return
        with contextlib.suppress(Exception):
            if sys.platform == "win32":
                proc = await asyncio.create_subprocess_exec(
                    "taskkill",  # noqa: S607
                    "/PID",
                    str(pid),
                    "/T",
                    "/F",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(proc.wait(), timeout=10)
                return
            os.kill(pid, 9)  # noqa: S606
            return
        with contextlib.suppress(Exception):
            if sys.platform == "win32":
                proc2 = await asyncio.create_subprocess_exec(  # noqa: S607
                    "taskkill",
                    "/PID",
                    str(pid),
                    "/T",
                    "/F",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(proc2.wait(), timeout=10)
            else:
                os.kill(pid, 9)  # noqa: S606


class WindowsProcessExecutor(PortableSubprocessExecutor):
    """Windows-specific executor: taskkill /T /F semantics."""

    async def terminate(self, pid: int) -> None:
        if pid <= 0:
            return
        try:
            proc = await asyncio.create_subprocess_exec(
                "taskkill",  # noqa: S607
                "/PID",
                str(pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=10)
            return
        except Exception:
            await super().terminate(pid)


class PosixProcessExecutor(PortableSubprocessExecutor):
    """POSIX executor: sigkill group."""

    async def terminate(self, pid: int) -> None:
        if pid <= 0:
            return
        with contextlib.suppress(ProcessLookupError, OSError):
            os.kill(pid, 9)  # noqa: S606
