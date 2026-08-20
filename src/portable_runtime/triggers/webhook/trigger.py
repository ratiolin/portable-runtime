"""Webhook trigger generic with HMAC verification and idempotent dedup."""

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


class WebhookTrigger:
    def __init__(
        self,
        trigger_id: str = "webhook",
        secret: str | None = None,
        idempotency_store: TriggerIdempotencyStore | None = None,
    ) -> None:
        self._descriptor = TriggerDescriptor(id=trigger_id, name="Webhook Trigger")
        self._emit: TriggerEmitter | None = None
        self._secret = secret
        self._store = idempotency_store or TriggerIdempotencyStore()
        self._seen_signatures: set[str] = set()

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

    async def handle(
        self,
        payload: dict[str, Any],
        kind: str = "webhook",
        signature: str | None = None,
        raw_body: bytes | None = None,
    ) -> TriggerEvent:
        if self._secret is not None:
            if signature is None and raw_body is not None:
                raise TriggerError("missing signature", TriggerErrorCategory.SIGNATURE, 401)
            if signature is not None:
                body = raw_body if raw_body is not None else json.dumps(payload, sort_keys=True).encode()
                if not self.verify(body, signature):
                    raise TriggerError("invalid webhook signature", TriggerErrorCategory.SIGNATURE, 401)
        dedup_key = str(payload.get("id") or payload.get("dedup_key") or payload.get("fingerprint") or "")
        if not dedup_key:
            dedup_key = json.dumps(payload, sort_keys=True)
        if not self._store.mark_processed(dedup_key):
            raise TriggerError(f"duplicate webhook event: {dedup_key[:80]}", TriggerErrorCategory.DUPLICATE, 409)
        event = TriggerEvent(
            id=f"evt_webhook_{uuid.uuid4().hex[:8]}",
            source=self.descriptor.id,
            kind=kind,
            payload=payload,
            occurred_at=datetime.now(UTC),
        )
        try:
            runtime_metrics.inc_trigger(self.descriptor.id, kind)
        except Exception:
            pass
        if self._emit:
            await self._emit(event)
        return event
