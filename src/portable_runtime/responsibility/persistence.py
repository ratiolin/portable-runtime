from __future__ import annotations

import hashlib
from typing import Any

from portable_runtime.core.models import Event
from portable_runtime.responsibility.models import ResponsibilityObject, parse_responsibility_object

RESPONSIBILITY_EVENT_TYPE = "persistent-responsibility.object-recorded"
RESPONSIBILITY_EVENT_SCHEMA = "persistent-responsibility-event-v1"


def responsibility_event_id(object_id: str) -> str:
    digest = hashlib.sha256(object_id.encode("utf-8")).hexdigest()[:32]
    return f"event_responsibility_{digest}"


def responsibility_subject_ref(value: ResponsibilityObject) -> str:
    responsibility_ref = getattr(value, "responsibility_ref", None)
    if isinstance(responsibility_ref, str) and responsibility_ref:
        return responsibility_ref
    return value.id


def responsibility_event(value: ResponsibilityObject) -> Event:
    return Event(
        id=responsibility_event_id(value.id),
        type=RESPONSIBILITY_EVENT_TYPE,
        subject_ref=responsibility_subject_ref(value),
        payload={
            "schema_version": RESPONSIBILITY_EVENT_SCHEMA,
            "object": value.model_dump(mode="json"),
        },
    )


def responsibility_object_from_event(event: Event) -> ResponsibilityObject:
    if event.type != RESPONSIBILITY_EVENT_TYPE:
        raise ValueError("event is not a persistent-responsibility object event")
    if event.payload.get("schema_version") != RESPONSIBILITY_EVENT_SCHEMA:
        raise ValueError("unsupported persistent-responsibility event schema")
    return parse_responsibility_object(event.payload.get("object"))


def _semantic_event_dump(event: Event) -> dict[str, Any]:
    raw = event.model_dump(mode="json")
    raw = dict(raw)
    raw.pop("created_at", None)
    return raw


class ResponsibilityJournal:
    """Append-only persistence adapter over the canonical runtime event journal.

    Reusing the existing Event namespace gives responsibility objects the same
    Memory/SQLite/export/import/bundle durability as other runtime history
    without creating a second store or workflow engine.
    """

    def __init__(self, store: Any) -> None:
        self.store = store

    def save(self, value: ResponsibilityObject) -> ResponsibilityObject:
        event = responsibility_event(value)
        existing = self.store.get_event(event.id)
        if existing is not None:
            if _semantic_event_dump(existing) != _semantic_event_dump(event):
                raise ValueError(f"responsibility object {value.id!r} is append-only")
            return responsibility_object_from_event(existing)
        self.store.append_event(event)
        return value

    def get(self, object_id: str) -> ResponsibilityObject | None:
        event = self.store.get_event(responsibility_event_id(object_id))
        if event is None:
            return None
        return responsibility_object_from_event(event)

    def list(
        self,
        object_type: str | None = None,
        responsibility_ref: str | None = None,
    ) -> list[ResponsibilityObject]:
        values: list[ResponsibilityObject] = []
        for event in self.store.list_events(subject_ref=responsibility_ref):
            if event.type != RESPONSIBILITY_EVENT_TYPE:
                continue
            value = responsibility_object_from_event(event)
            if object_type is not None and value.object_type != object_type:
                continue
            values.append(value)
        return sorted(values, key=lambda value: (value.created_at, value.id))


__all__ = [
    "RESPONSIBILITY_EVENT_SCHEMA",
    "RESPONSIBILITY_EVENT_TYPE",
    "ResponsibilityJournal",
    "responsibility_event",
    "responsibility_event_id",
    "responsibility_object_from_event",
]
