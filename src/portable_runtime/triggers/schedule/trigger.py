"""Schedule trigger replacing Windows Task Scheduler (§14.2, §56).

Core must never depend on Windows Task Scheduler / PowerShell / VBS.
This trigger uses a cross-platform ``asyncio`` scheduler (``asyncio.sleep`` loop)
and can be driven by the Runtime internally or by external cron via HTTP/CLI.

Deployment layer decides whether to run the loop or to call ``emit_once()``
from cron / webhook.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from ..base import TriggerDescriptor, TriggerEmitter, TriggerEvent


class ScheduleTrigger:
    """Cross-platform periodic trigger (asyncio-based, portable-local friendly)."""

    def __init__(
        self,
        trigger_id: str = "schedule",
        interval_seconds: float = 3600,
        kind: str = "maintenance-scan",
    ) -> None:
        self._descriptor = TriggerDescriptor(id=trigger_id, name="Schedule Trigger")
        self.interval_seconds = interval_seconds
        self.kind = kind
        self._task: asyncio.Task[None] | None = None
        self._emit: TriggerEmitter | None = None

    @property
    def descriptor(self) -> TriggerDescriptor:
        return self._descriptor

    async def start(self, emit: TriggerEmitter) -> None:
        """Start the periodic loop; each tick emits a ``TriggerEvent`` via ``emit``."""
        self._emit = emit
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Stop the periodic loop gracefully."""
        if self._task:
            self._task.cancel()
            with __import__("contextlib").suppress(asyncio.CancelledError):
                await self._task
        self._task = None
        self._emit = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.interval_seconds)
            if self._emit is None:
                continue
            event = TriggerEvent(
                id=f"evt_schedule_{uuid.uuid4().hex[:8]}",
                source=self.descriptor.id,
                kind=self.kind,
                payload={"kind": self.kind},
                occurred_at=datetime.now(UTC),
            )
            await self._emit(event)

    async def emit_once(self) -> TriggerEvent:
        """Emit a single event immediately (used by cron / HTTP ``/v1/triggers/schedule/emit``)."""
        event = TriggerEvent(
            id=f"evt_schedule_{uuid.uuid4().hex[:8]}",
            source=self.descriptor.id,
            kind=self.kind,
            payload={"kind": self.kind},
            occurred_at=datetime.now(UTC),
        )
        if self._emit:
            await self._emit(event)
        return event
