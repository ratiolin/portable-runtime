"""Trigger abstractions (Alertmanager, Schedule, Webhook) – B2."""

from __future__ import annotations

from datetime import UTC, datetime
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
