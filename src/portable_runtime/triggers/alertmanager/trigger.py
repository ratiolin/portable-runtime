"""Alertmanager trigger: webhook -> TriggerEvent with dedup and signature verification."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from portable_runtime.core import metrics as runtime_metrics

from ..base import (
    TriggerDescriptor,
    TriggerEmitter,
    TriggerError,
    TriggerErrorCategory,
    TriggerEvent,
    TriggerIdempotencyStore,
    verify_signature,
)


class AlertmanagerTrigger:
    """Receives Alertmanager webhooks and emits portable TriggerEvents."""

    def __init__(
        self,
        trigger_id: str = "alertmanager",
        secret: str | None = None,
        idempotency_store: TriggerIdempotencyStore | None = None,
    ) -> None:
        self._descriptor = TriggerDescriptor(id=trigger_id, name="Alertmanager Trigger")
        self._emit: TriggerEmitter | None = None
        self._secret = secret
        self._store = idempotency_store or TriggerIdempotencyStore()

    @property
    def descriptor(self) -> TriggerDescriptor:
        return self._descriptor

    async def start(self, emit: TriggerEmitter) -> None:
        self._emit = emit

    async def stop(self) -> None:
        self._emit = None

    def verify(self, payload: bytes, signature: str) -> bool:
        if self._secret is None:
            return True
        if not signature:
            return False
        return verify_signature(payload, signature, self._secret)

    async def handle_webhook(
        self,
        payload: dict[str, Any],
        signature: str | None = None,
        raw_body: bytes | None = None,
    ) -> list[TriggerEvent]:
        """Parse Alertmanager payload into TriggerEvents."""
        if self._secret is not None:
            body = raw_body if raw_body is not None else json.dumps(payload, sort_keys=True).encode()
            if not signature:
                raise TriggerError("missing alertmanager signature", TriggerErrorCategory.SIGNATURE, 401)
            if not self.verify(body, signature):
                raise TriggerError("invalid alertmanager signature", TriggerErrorCategory.SIGNATURE, 401)
        events: list[TriggerEvent] = []
        alerts = payload.get("alerts", [payload]) if isinstance(payload, dict) else []
        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            labels = alert.get("labels", {}) if isinstance(alert.get("labels"), dict) else {}
            fingerprint = alert.get("fingerprint") or labels.get("fingerprint") or ""
            dedup_key = f"{fingerprint}:{labels.get('alertname', '')}:{alert.get('startsAt','')}"
            if fingerprint and not self._store.mark_processed(dedup_key):
                raise TriggerError(f"duplicate alert: {fingerprint}", TriggerErrorCategory.DUPLICATE, 409)
            event = TriggerEvent(
                id=f"evt_{fingerprint or uuid.uuid4().hex}_{uuid.uuid4().hex[:6]}",
                source=self.descriptor.id,
                kind=str(labels.get("alertname", "alert")),
                payload=alert,
                occurred_at=datetime.now(UTC),
            )
            events.append(event)
            try:
                runtime_metrics.inc_trigger(self.descriptor.id, event.kind)
            except Exception:
                pass
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
