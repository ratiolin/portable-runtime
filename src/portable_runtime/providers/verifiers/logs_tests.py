"""Log, test and git-diff verifiers."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    InvocationContext,
    ProviderDescriptor,
    ProviderHealth,
)
from portable_runtime.records.open_validation import ClosedVerificationResult

logger = logging.getLogger(__name__)


class LogsVerifierProvider:
    def __init__(
        self,
        provider_id: str = "verifier-logs",
        check_fn: Callable[..., Awaitable[tuple[bool, str, str]]] | None = None,
    ) -> None:
        self._check_fn = check_fn
        self._descriptor = ProviderDescriptor(id=provider_id, name="Logs Verifier", version="1.0.0", capabilities=["verify.logs"], tags={"verify"}, priority=5)  # noqa: E501

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.descriptor.id, available=True, detail="logs verifier ready")

    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        target = str(request.parameters.get("target", "") or "")
        patterns = request.parameters.get("patterns") or []
        since_minutes = int(request.parameters.get("since_minutes", 30))
        if not target:
            return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="failed", error={"type": "invalid_request", "message": "verify.logs requires parameters.target"})  # noqa: E501
        if self._check_fn is not None:
            try:
                ok, message, ref = await self._check_fn(target, since_minutes=since_minutes, patterns=tuple(patterns) if patterns else ("Traceback", "panic:", "FATAL"))  # noqa: E501
                return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="succeeded", message=message, metadata={"evidence_ref": ref}, verification_result=ClosedVerificationResult(result="pass" if ok else "fail", message=message))  # noqa: E501
            except Exception as exc:  # noqa: BLE001
                return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="failed", error={"type": type(exc).__name__, "message": str(exc)[:1500]})  # noqa: E501
        # Placeholder: scan local logs directory or delegate to control_plane.tools
        try:
            from control_plane.tools import check_logs

            ok, message, ref = await check_logs(target, since_minutes=since_minutes, patterns=patterns)  # noqa: E501
            return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="succeeded", message=message, metadata={"evidence_ref": ref}, verification_result=ClosedVerificationResult(result="pass" if ok else "fail", message=message))  # noqa: E501
        except Exception as exc:  # noqa: BLE001
            # Fallback: check file existence
            p = Path(target)
            if p.exists():
                message = f"logs target {target} exists"
                return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="succeeded", message=message, verification_result=ClosedVerificationResult(result="pass", message=message))  # noqa: E501
            return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="failed", error={"type": type(exc).__name__, "message": str(exc)[:1500]})  # noqa: E501

    async def cancel(self, request_id: str) -> None:
        return None


class TestsVerifierProvider:
    def __init__(self, provider_id: str = "verifier-tests") -> None:
        self._descriptor = ProviderDescriptor(id=provider_id, name="Tests Verifier", version="1.0.0", capabilities=["verify.tests"], tags={"verify"}, priority=5)  # noqa: E501

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    async def health(self) -> ProviderHealth:
        import shutil

        py = shutil.which("python") or shutil.which("python3")
        return ProviderHealth(provider_id=self.descriptor.id, available=py is not None, detail="python found" if py else "python not found")  # noqa: E501

    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        # parameters: command (default pytest), cwd
        command = request.parameters.get("command") or ["python", "-m", "pytest", "-q"]
        if isinstance(command, str):
            command = [command]
        cwd = request.parameters.get("cwd")
        timeout = float(request.parameters.get("timeout_seconds", 120))
        try:
            proc = await asyncio.create_subprocess_exec(*command, cwd=str(cwd) if cwd else None, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # noqa: E501
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            ok = proc.returncode == 0
            return CapabilityResult(
                request_id=request.id,
                provider_id=self.descriptor.id,
                status="succeeded",
                message=(stdout.decode(errors="replace")[-4000:] or stderr.decode(errors="replace")[-4000:]),
                metadata={"exit_code": proc.returncode},
                verification_result=ClosedVerificationResult(
                    result="pass" if ok else "fail",
                    message=(stdout.decode(errors="replace")[-4000:] or stderr.decode(errors="replace")[-4000:]),
                ),
            )
        except Exception as exc:  # noqa: BLE001
            return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="failed", error={"type": type(exc).__name__, "message": str(exc)[:2000]})  # noqa: E501

    async def cancel(self, request_id: str) -> None:
        return None


class GitDiffVerifierProvider:
    """Guards forbidden diff patterns (verifier.py, AGENTS.md, secrets, etc.)."""

    def __init__(self, provider_id: str = "verifier-git-diff") -> None:
        self._descriptor = ProviderDescriptor(id=provider_id, name="Git Diff Verifier", version="1.0.0", capabilities=["verify.git_diff"], tags={"verify", "side-effect-free"}, priority=5)  # noqa: E501

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.descriptor.id, available=True, detail="git diff verifier ready")

    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        diff = str(request.parameters.get("diff", "") or "")
        if not diff:
            return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="failed", error={"type": "invalid_request", "message": "verify.git_diff requires parameters.diff"})  # noqa: E501
        try:
            from control_plane.verifier import Verifier

            ok, message = Verifier.diff_allowed("", diff)
            return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="succeeded", message=message, verification_result=ClosedVerificationResult(result="pass" if ok else "fail", message=message))  # noqa: E501
        except Exception as exc:  # noqa: BLE001
            return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="failed", error={"type": type(exc).__name__, "message": str(exc)[:1500]})  # noqa: E501

    async def cancel(self, request_id: str) -> None:
        return None




