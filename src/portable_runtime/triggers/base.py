"""Trigger abstractions (Alertmanager, Schedule, Webhook) – B2.

Extends base with webhook HMAC verification, idempotent dedup, error classification.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field


class TriggerEvent(BaseModel):
    id: str
    source: str
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TriggerEmitter(Protocol):
    async def __call__(self, event: TriggerEvent) -> None: ...


class TriggerDescriptor(BaseModel):
    id: str
    name: str
    version: str = "1.0.0"
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class TriggerSource(Protocol):
    @property
    def descriptor(self) -> TriggerDescriptor: ...

    async def start(self, emit: TriggerEmitter) -> None: ...

    async def stop(self) -> None: ...


class TriggerErrorCategory(str, Enum):
    VALIDATION = "validation"
    SIGNATURE = "signature"
    DUPLICATE = "duplicate"
    PROCESSING = "processing"
    TRANSIENT = "transient"
    PERMANENT = "permanent"


class TriggerError(Exception):
    def __init__(self, message: str, category: TriggerErrorCategory, status_code: int = 400) -> None:
        super().__init__(message)
        self.category = category
        self.status_code = status_code


def classify_trigger_error(exc: BaseException) -> TriggerErrorCategory:
    if isinstance(exc, TriggerError):
        return exc.category
    msg = str(exc).lower()
    if "signature" in msg or "hmac" in msg or "unauthorized" in msg:
        return TriggerErrorCategory.SIGNATURE
    if "duplicate" in msg or "idempotent" in msg:
        return TriggerErrorCategory.DUPLICATE
    if "validation" in msg or "invalid" in msg or "missing" in msg:
        return TriggerErrorCategory.VALIDATION
    if "timeout" in msg or "transient" in msg:
        return TriggerErrorCategory.TRANSIENT
    return TriggerErrorCategory.PROCESSING


def http_status_for_trigger_error(category: TriggerErrorCategory) -> int:
    mapping: dict[TriggerErrorCategory, int] = {
        TriggerErrorCategory.VALIDATION: 400,
        TriggerErrorCategory.SIGNATURE: 401,
        TriggerErrorCategory.DUPLICATE: 409,
        TriggerErrorCategory.PROCESSING: 500,
        TriggerErrorCategory.TRANSIENT: 503,
        TriggerErrorCategory.PERMANENT: 400,
    }
    return mapping.get(category, 500)


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Timing-safe HMAC-SHA256 verification for webhook triggers."""
    if not secret:
        return False
    sig = signature.strip()
    if "=" in sig:
        _, sig = sig.split("=", 1)
        sig = sig.strip()
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def compute_signature(payload: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class TriggerIdempotencyStore:
    """Deduplication for trigger events by id/fingerprint."""

    def __init__(self, ttl_seconds: float = 3600, max_entries: int = 10000) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries: dict[str, float] = {}

    def _evict(self) -> None:
        now = time.monotonic()
        expired = [k for k, ts in self._entries.items() if now - ts > self.ttl_seconds]
        for k in expired:
            self._entries.pop(k, None)
        if len(self._entries) > self.max_entries:
            sorted_keys = sorted(self._entries, key=lambda k: self._entries[k])
            for k in sorted_keys[: len(self._entries) - self.max_entries]:
                self._entries.pop(k, None)

    def is_duplicate(self, key: str) -> bool:
        self._evict()
        return key in self._entries

    def mark_processed(self, key: str) -> bool:
        """Return False if duplicate, True if newly marked."""
        self._evict()
        if key in self._entries:
            return False
        self._entries[key] = time.monotonic()
        return True

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        self._evict()
        return len(self._entries)
