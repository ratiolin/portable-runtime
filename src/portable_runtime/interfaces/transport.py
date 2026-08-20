"""Provider transport with HMAC verification, idempotent dedup, and error classification."""

from __future__ import annotations

import hashlib
import hmac
import time
from enum import Enum
from typing import Protocol

import httpx


class ProviderTransport(Protocol):
    async def request(self, payload: dict[str, object], timeout_seconds: float | None = None) -> dict[str, object]: ...


class TransportErrorCategory(str, Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    TIMEOUT = "timeout"
    AUTH = "auth"
    RATE_LIMITED = "rate_limited"
    UNKNOWN = "unknown"


class TransportError(Exception):
    def __init__(self, message: str, category: TransportErrorCategory, status_code: int | None = None) -> None:
        super().__init__(message)
        self.category = category
        self.status_code = status_code


def classify_transport_error(status_code: int | None = None, exception: BaseException | None = None) -> TransportErrorCategory:
    if exception is not None:
        name = type(exception).__name__.lower()
        msg = str(exception).lower()
        if "timeout" in name or "timeout" in msg:
            return TransportErrorCategory.TIMEOUT
        if "auth" in msg or "unauthorized" in msg or "forbidden" in msg:
            return TransportErrorCategory.AUTH
    if status_code is None:
        return TransportErrorCategory.UNKNOWN
    if status_code in (408, 429):
        return TransportErrorCategory.RATE_LIMITED if status_code == 429 else TransportErrorCategory.TIMEOUT
    if status_code == 401 or status_code == 403:
        return TransportErrorCategory.AUTH
    if 500 <= status_code < 600:
        return TransportErrorCategory.TRANSIENT
    if 400 <= status_code < 500:
        return TransportErrorCategory.PERMANENT
    return TransportErrorCategory.UNKNOWN


def verify_webhook_signature(payload: bytes, signature: str, secret: str, algorithm: str = "sha256") -> bool:
    """Timing-safe HMAC verification. Supports hex and sha256= prefix."""
    if not secret:
        return False
    sig = signature.strip()
    if "=" in sig:
        _, sig = sig.split("=", 1)
        sig = sig.strip()
    try:
        if algorithm == "sha256":
            expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        elif algorithm == "sha1":
            expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha1).hexdigest()
        else:
            expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    except Exception:
        return False
    return hmac.compare_digest(expected, sig)


def compute_webhook_signature(payload: bytes, secret: str, algorithm: str = "sha256") -> str:
    if algorithm == "sha256":
        digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return f"sha256={digest}"
    if algorithm == "sha1":
        digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha1).hexdigest()
        return f"sha1={digest}"
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return digest


class IdempotencyStore:
    """In-memory deduplication with TTL. Thread-safe for single-process use."""

    def __init__(self, ttl_seconds: float = 3600, max_entries: int = 10000) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries: dict[str, float] = {}

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, ts in self._entries.items() if now - ts > self.ttl_seconds]
        for k in expired:
            self._entries.pop(k, None)
        if len(self._entries) > self.max_entries:
            sorted_keys = sorted(self._entries, key=lambda k: self._entries[k])
            for k in sorted_keys[: len(self._entries) - self.max_entries]:
                self._entries.pop(k, None)

    def check_and_store(self, key: str) -> bool:
        """Return True if key is new (stored), False if duplicate."""
        self._evict_expired()
        if key in self._entries:
            return False
        self._entries[key] = time.monotonic()
        return True

    def contains(self, key: str) -> bool:
        self._evict_expired()
        return key in self._entries

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        self._evict_expired()
        return len(self._entries)


class HttpxProviderTransport:
    """httpx-based ProviderTransport with error classification and retry awareness."""

    def __init__(self, base_url: str, *, timeout: float = 30.0, idempotency_store: IdempotencyStore | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.idempotency_store = idempotency_store

    async def request(self, payload: dict[str, object], timeout_seconds: float | None = None) -> dict[str, object]:
        idem_key = str(payload.get("id") or payload.get("request_id") or "")
        if self.idempotency_store is not None and idem_key:
            if not self.idempotency_store.check_and_store(idem_key):
                raise TransportError(f"duplicate request: {idem_key}", TransportErrorCategory.PERMANENT)
        timeout = timeout_seconds if timeout_seconds is not None else self.timeout
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(self.base_url, json=payload)
                if resp.status_code >= 400:
                    cat = classify_transport_error(resp.status_code)
                    raise TransportError(f"http {resp.status_code}: {resp.text[:500]}", cat, resp.status_code)
                data = resp.json()
                if not isinstance(data, dict):
                    return {"result": data}
                return data
        except TransportError:
            raise
        except httpx.TimeoutException as exc:
            raise TransportError(str(exc), TransportErrorCategory.TIMEOUT) from exc
        except httpx.HTTPStatusError as exc:
            cat = classify_transport_error(exc.response.status_code, exc)
            raise TransportError(str(exc), cat, exc.response.status_code) from exc
        except Exception as exc:  # noqa: BLE001
            cat = classify_transport_error(None, exc)
            raise TransportError(str(exc), cat) from exc

    def is_transient(self, error: TransportError) -> bool:
        return error.category in (TransportErrorCategory.TRANSIENT, TransportErrorCategory.TIMEOUT, TransportErrorCategory.RATE_LIMITED)


def http_status_for_category(category: TransportErrorCategory) -> int:
    mapping: dict[TransportErrorCategory, int] = {
        TransportErrorCategory.TRANSIENT: 503,
        TransportErrorCategory.PERMANENT: 400,
        TransportErrorCategory.TIMEOUT: 504,
        TransportErrorCategory.AUTH: 401,
        TransportErrorCategory.RATE_LIMITED: 429,
        TransportErrorCategory.UNKNOWN: 500,
    }
    return mapping.get(category, 500)
