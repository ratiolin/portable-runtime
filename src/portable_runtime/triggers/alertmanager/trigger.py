"""Alertmanager trigger: webhook -> TriggerEvent (no direct Codex call)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from ..base import TriggerDescriptor, TriggerEmitter, TriggerEvent


class AlertmanagerTrigger:
    """Receives Alertmanager webhooks and emits portable TriggerEvents."""

    def __init__(self, trigger_id: str = "alertmanager") -> None:
        self._descriptor = TriggerDescriptor(id=trigger_id, name="Alertmanager Trigger")
        self._emit: TriggerEmitter | None = None

    @property
    def descriptor(self) -> TriggerDescriptor:
        return self._descriptor

    async def start(self, emit: TriggerEmitter) -> None:
        self._emit = emit

    async def stop(self) -> None:
        self._emit = None

    async def handle_webhook(self, payload: dict[str, Any]) -> list[TriggerEvent]:
        """Parse Alertmanager payload into TriggerEvents."""
        events: list[TriggerEvent] = []
        alerts = payload.get("alerts", [payload]) if isinstance(payload, dict) else []
        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            labels = alert.get("labels", {})
            fingerprint = alert.get("fingerprint") or labels.get("fingerprint") or uuid.uuid4().hex
            event = TriggerEvent(
                id=f"evt_{fingerprint}_{uuid.uuid4().hex[:6]}",
                source=self.descriptor.id,
                kind=str(labels.get("alertname", "alert")),
                payload=alert,
                occurred_at=datetime.now(UTC),
            )
            events.append(event)
            if self._emit:
                await self._emit(event)
        return events

    def to_work_fields(self, event: TriggerEvent) -> dict[str, Any]:
        return {
            "kind": "incident",
            "title": f"Alert {event.kind}",
            "description": str(event.payload)[:20000],
            "requested_capabilities": ["reason.generate"],
            "metadata": {"trigger_event_id": event.id, "fingerprint": event.payload.get("fingerprint", "")},
        }
