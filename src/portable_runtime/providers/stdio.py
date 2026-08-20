from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    InvocationContext,
    ProviderDescriptor,
    ProviderHealth,
)
from portable_runtime.protocol.manifest import ProviderManifest
from portable_runtime.protocol.messages import InvokeMessage, ResultMessage


class StdioJsonlProvider:
    """One-shot language-neutral provider using a JSONL subprocess exchange."""

    def __init__(self, manifest: ProviderManifest, *, working_directory: Path | None = None) -> None:
        self.manifest = manifest
        self.working_directory = working_directory
        self._descriptor = ProviderDescriptor(
            id=manifest.id,
            name=manifest.name,
            version=manifest.version,
            capabilities=manifest.capabilities,
            metadata=manifest.metadata,
            tags={"external", "stdio-jsonl"},
        )

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    async def health(self) -> ProviderHealth:
        cmd = self.manifest.command
        if not cmd:
            return ProviderHealth(
                provider_id=self.descriptor.id, available=False, detail="no command"
            )
        executable = shutil.which(cmd[0])
        return ProviderHealth(
            provider_id=self.descriptor.id,
            available=executable is not None,
            detail="command not found" if executable is None else "ready",
        )

    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        cmd = self.manifest.command
        if not cmd:
            return CapabilityResult(
                request_id=request.id,
                provider_id=self.descriptor.id,
                status="failed",
                error={"type": "protocol", "message": "no command for stdio provider"},
            )
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.working_directory,
        )
        message = InvokeMessage(
            id=request.id,
            capability=request.capability,
            work_id=request.work_id,
            run_id=request.run_id,
            instruction=request.instruction,
            input_artifact_refs=request.input_artifact_refs,
            parameters=request.parameters,
        )
        if process.stdin is None or process.stdout is None:
            return CapabilityResult(
                request_id=request.id,
                provider_id=self.descriptor.id,
                status="failed",
                error={"type": "protocol", "message": "provider pipes unavailable"},
            )
        process.stdin.write((message.model_dump_json() + "\n").encode())
        await process.stdin.drain()
        process.stdin.close()
        timeout = request.timeout_seconds or 60
        try:
            raw = await asyncio.wait_for(process.stdout.readline(), timeout=timeout)
            await asyncio.wait_for(process.wait(), timeout=timeout)
        except TimeoutError:
            process.kill()
            await process.wait()
            return CapabilityResult(
                request_id=request.id,
                provider_id=self.descriptor.id,
                status="failed",
                error={"type": "timeout", "message": "provider timed out"},
            )
        if not raw:
            stderr_data = b""
            if process.stderr is not None:
                stderr_data = await process.stderr.read()
            return CapabilityResult(
                request_id=request.id,
                provider_id=self.descriptor.id,
                status="failed",
                error={
                    "type": "protocol",
                    "message": "provider returned no result",
                    "stderr": stderr_data.decode(errors="replace")[-2_000:],
                },
            )
        try:
            result = ResultMessage.model_validate(json.loads(raw))
        except Exception as exc:  # noqa: BLE001 - untrusted provider output
            return CapabilityResult(
                request_id=request.id,
                provider_id=self.descriptor.id,
                status="failed",
                error={"type": "protocol", "message": str(exc)},
            )
        return CapabilityResult(
            request_id=request.id,
            provider_id=self.descriptor.id,
            status=result.status,
            evidence_refs=result.evidence_refs,
            message=result.message,
            error=result.error,
            metadata={"output_artifacts": [artifact.model_dump(mode="json") for artifact in result.output_artifacts]},
        )

    async def cancel(self, request_id: str) -> None:
        return None
