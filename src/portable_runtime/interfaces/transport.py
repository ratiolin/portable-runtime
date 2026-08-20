from __future__ import annotations

from typing import Protocol


class ProviderTransport(Protocol):
    async def request(self, payload: dict[str, object], timeout_seconds: float | None = None) -> dict[str, object]: ...
