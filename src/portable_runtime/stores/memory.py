from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from portable_runtime.core.models import (
    Action,
    Artifact,
    Decision,
    Event,
    Evidence,
    KnowledgeItem,
    Outcome,
    Run,
    Work,
)


class InMemoryStateStore:
    """Deterministic store used by core tests and provider conformance tests."""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, BaseModel]] = {
            "work": {},
            "run": {},
            "artifact": {},
            "evidence": {},
            "decision": {},
            "action": {},
            "outcome": {},
            "knowledge": {},
            "event": {},
        }

    def _save(self, kind: str, value: BaseModel) -> None:
        identifier = getattr(value, "id", None)
        if not isinstance(identifier, str):
            raise ValueError("runtime records require a string id")
        self._records[kind][identifier] = value

    def _get(self, kind: str, value_type: type[Any], identifier: str) -> Any | None:
        value = self._records[kind].get(identifier)
        return value if isinstance(value, value_type) else None

    def _list(self, kind: str, value_type: type[Any]) -> list[Any]:
        values = [value for value in self._records[kind].values() if isinstance(value, value_type)]
        return sorted(values, key=lambda value: value.created_at, reverse=True)

    def save_work(self, value: Work) -> None: self._save("work", value)
    def get_work(self, work_id: str) -> Work | None: return self._get("work", Work, work_id)
    def list_work(self, status: str | None = None) -> list[Work]:
        return [value for value in self._list("work", Work) if status is None or value.status == status]

    def save_run(self, value: Run) -> None: self._save("run", value)
    def get_run(self, run_id: str) -> Run | None: return self._get("run", Run, run_id)
    def list_runs(self, work_id: str | None = None) -> list[Run]:
        return [value for value in self._list("run", Run) if work_id is None or value.work_id == work_id]

    def save_artifact(self, value: Artifact) -> None: self._save("artifact", value)
    def get_artifact(self, artifact_id: str) -> Artifact | None: return self._get("artifact", Artifact, artifact_id)

    def save_evidence(self, value: Evidence) -> None: self._save("evidence", value)
    def list_evidence(self, subject_ref: str | None = None) -> list[Evidence]:
        return [
            value
            for value in self._list("evidence", Evidence)
            if subject_ref is None or subject_ref in value.subject_refs
        ]

    def save_decision(self, value: Decision) -> None: self._save("decision", value)
    def save_action(self, value: Action) -> None: self._save("action", value)
    def save_outcome(self, value: Outcome) -> None: self._save("outcome", value)
    def save_knowledge(self, value: KnowledgeItem) -> None: self._save("knowledge", value)
    def get_knowledge(self, knowledge_id: str) -> KnowledgeItem | None:
        return self._get("knowledge", KnowledgeItem, knowledge_id)
    def list_knowledge(self, status: str | None = None) -> list[KnowledgeItem]:
        return [value for value in self._list("knowledge", KnowledgeItem) if status is None or value.status == status]

    def append_event(self, value: Event) -> None: self._save("event", value)

    def export_state(self) -> dict[str, list[dict[str, object]]]:
        return {
            kind: [value.model_dump(mode="json") for value in values.values()]
            for kind, values in self._records.items()
        }

    def import_state(self, state: dict[str, list[dict[str, object]]]) -> None:
        types: dict[str, type[object]] = {
            "work": Work,
            "run": Run,
            "artifact": Artifact,
            "evidence": Evidence,
            "decision": Decision,
            "action": Action,
            "outcome": Outcome,
            "knowledge": KnowledgeItem,
            "event": Event,
        }
        for kind, values in state.items():
            model_type = types.get(kind)
            if model_type is None:
                continue
            for raw in values:
                value = model_type.model_validate(raw)  # type: ignore[attr-defined]
                self._records[kind][value.id] = value
