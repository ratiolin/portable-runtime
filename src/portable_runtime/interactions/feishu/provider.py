"""Feishu interaction split: FeishuTrigger + Human/Notify providers."""

from __future__ import annotations

import contextlib
import logging
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

    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        # Delegate to feishu-notify.ps1 if present, else no-op
        import asyncio
        import pathlib

        script = pathlib.Path.home() / ".local" / "bin" / "feishu-notify.ps1"
        if script.is_file():
            with contextlib.suppress(Exception):  # noqa: SIM105,S110
                proc = await asyncio.create_subprocess_exec(  # noqa: S607
                    "powershell.exe",
                    "-File",
                    str(script),
                    request.instruction or "",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(proc.wait(), timeout=10)
        return CapabilityResult(  # noqa: E501
            request_id=request.id,
            provider_id=self.descriptor.id,
            status="succeeded",
            message="notified",
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
