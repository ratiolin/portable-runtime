"""Feishu interaction split: FeishuTrigger + Human/Notify providers."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path
from typing import Any

from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    InvocationContext,
    ProviderDescriptor,
    ProviderHealth,
)
from portable_runtime.triggers.base import TriggerDescriptor, TriggerEmitter, TriggerEvent

logger = logging.getLogger(__name__)


class FeishuHumanProvider:
    """Implements human.review / human.approve as a CapabilityProvider."""

    def __init__(self, provider_id: str = "feishu-human") -> None:
        self._descriptor = ProviderDescriptor(
            id=provider_id, name="Feishu Human Provider", version="1.0.0",
            capabilities=["human.review", "human.approve"], tags={"human"}, priority=5
        )

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.descriptor.id, available=True, detail="feishu human ready (stub)")

    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        # In portable-local, human approval can be satisfied via CLI; Feishu is optional.
        if request.capability == "human.approve":
            # If workflow requires approval, we surface needs-input
            return CapabilityResult(  # noqa: E501
                request_id=request.id,
                provider_id=self.descriptor.id,
                status="needs-input",
                message="approval required via Feishu or CLI",
            )
        return CapabilityResult(  # noqa: E501
            request_id=request.id,
            provider_id=self.descriptor.id,
            status="succeeded",
            message=f"reviewed: {request.instruction}",
        )

    async def cancel(self, request_id: str) -> None:
        return None


class FeishuNotificationProvider:
    def __init__(self, provider_id: str = "feishu-notify") -> None:
        self._descriptor = ProviderDescriptor(
            id=provider_id, name="Feishu Notification Provider", version="1.0.0",
            capabilities=["notify.send"], tags={"notify"}, priority=5
        )

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.descriptor.id, available=True, detail="notify ready")

    def _result(
        self,
        request: CapabilityRequest,
        *,
        status: str,
        provider_accepted: bool | None,
        message: str,
        error: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CapabilityResult:
        # The legacy script contract exposes only its process exit code.  It
        # has no response channel containing a Feishu message id or delivery
        # receipt, so delivery is never confirmed by this provider.
        result_metadata: dict[str, Any] = {
            "provider_accepted": provider_accepted,
            "delivery_confirmed": False,
            "delivery_confirmation": "not_available",
        }
        if metadata:
            result_metadata.update(metadata)
        return CapabilityResult(
            request_id=request.id,
            provider_id=self.descriptor.id,
            status=status,
            message=message,
            error=error,
            metadata=result_metadata,
        )

    @staticmethod
    async def _terminate_process(process: Any) -> None:
        with contextlib.suppress(Exception):
            process.kill()
        with contextlib.suppress(Exception):
            await process.wait()

    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        script = Path.home() / ".local" / "bin" / "feishu-notify.ps1"
        if not script.is_file():
            return self._result(
                request,
                status="unavailable",
                provider_accepted=False,
                message="Feishu notification script is unavailable",
                error={
                    "code": "feishu_script_missing",
                    "type": "script_missing",
                    "message": f"notification script not found: {script}",
                },
                metadata={"failure_phase": "script_lookup"},
            )

        timeout_seconds = (
            request.timeout_seconds if request.timeout_seconds is not None else 10.0
        )
        try:
            proc = await asyncio.create_subprocess_exec(  # noqa: S607
                "powershell.exe",
                "-File",
                str(script),
                request.instruction or "",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except Exception as exc:  # noqa: BLE001 - subprocess startup is provider I/O
            return self._result(
                request,
                status="failed",
                provider_accepted=False,
                message="Feishu notification script failed to start",
                error={
                    "code": "feishu_script_start_failed",
                    "type": "script_start_failed",
                    "message": str(exc)[:500] or type(exc).__name__,
                },
                metadata={"failure_phase": "script_start"},
            )

        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout_seconds)
        except TimeoutError:
            await self._terminate_process(proc)
            return self._result(
                request,
                status="unknown",
                provider_accepted=None,
                message="Feishu notification script timed out; delivery is unknown",
                error={
                    "code": "feishu_script_timeout",
                    "type": "timeout",
                    "message": f"notification script timed out after {timeout_seconds:g}s",
                },
                metadata={
                    "failure_phase": "script_wait",
                    "timeout_seconds": timeout_seconds,
                },
            )
        except Exception as exc:  # noqa: BLE001 - provider wait is untrusted I/O
            await self._terminate_process(proc)
            return self._result(
                request,
                status="unknown",
                provider_accepted=None,
                message="Feishu notification script result could not be observed",
                error={
                    "code": "feishu_script_wait_failed",
                    "type": "script_wait_failed",
                    "message": str(exc)[:500] or type(exc).__name__,
                },
                metadata={"failure_phase": "script_wait"},
            )

        exit_code = proc.returncode
        if exit_code != 0:
            return self._result(
                request,
                status="failed",
                provider_accepted=False,
                message=f"Feishu notification script exited with code {exit_code}",
                error={
                    "code": "feishu_script_exit_nonzero",
                    "type": "script_exit",
                    "exit_code": exit_code,
                    "message": f"notification script exited with code {exit_code}",
                },
                metadata={"failure_phase": "script_exit", "exit_code": exit_code},
            )

        return self._result(
            request,
            status="succeeded",
            provider_accepted=True,
            message="Feishu notification provider accepted the request; delivery is not confirmed",
            metadata={"script_exit_code": 0},
        )

    async def cancel(self, request_id: str) -> None:
        return None


class FeishuTrigger:
    """Feishu message -> TriggerEvent (legacy /cp commands mapped via compat)."""

    def __init__(self, trigger_id: str = "feishu") -> None:
        self._descriptor = TriggerDescriptor(id=trigger_id, name="Feishu Trigger")
        self._emit: TriggerEmitter | None = None

    @property
    def descriptor(self) -> TriggerDescriptor:
        return self._descriptor

    async def start(self, emit: TriggerEmitter) -> None:
        self._emit = emit

    async def stop(self) -> None:
        self._emit = None

    async def handle_message(self, payload: dict[str, Any]) -> TriggerEvent:
        import uuid
        from datetime import UTC, datetime
        event = TriggerEvent(
            id=f"evt_feishu_{uuid.uuid4().hex[:8]}",
            source=self.descriptor.id,
            kind=str(payload.get("command", "message")),
            payload=payload,
            occurred_at=datetime.now(UTC),
        )
        if self._emit:
            await self._emit(event)
        return event
