"""Webhook trigger generic."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from ..base import TriggerDescriptor, TriggerEmitter, TriggerEvent


class WebhookTrigger:
    def __init__(self, trigger_id: str = "webhook") -> None:
        self._descriptor = TriggerDescriptor(id=trigger_id, name="Webhook Trigger")
        self._emit: TriggerEmitter | None = None

    @property
    def descriptor(self) -> TriggerDescriptor:
        return self._descriptor

    async def start(self, emit: TriggerEmitter) -> None:
        self._emit = emit

    async def stop(self) -> None:
        self._emit = None

    async def handle(self, payload: dict[str, Any], kind: str = "webhook") -> TriggerEvent:
        event = TriggerEvent(
            id=f"evt_webhook_{uuid.uuid4().hex[:8]}",
            source=self.descriptor.id,
            kind=kind,
            payload=payload,
            occurred_at=datetime.now(UTC),
        )
        if self._emit:
            await self._emit(event)
        return event
