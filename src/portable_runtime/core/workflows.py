"""Workflow contract kept independent from concrete providers — hardened."""

from __future__ import annotations

from typing import Any, Protocol

from .models import Run, Work


class Workflow(Protocol):
    id: str
    version: str

    def accepts(self, work: Work) -> bool: ...

    async def run(self, work: Work, run: Run) -> str: ...


# --- Hardened helpers (testable, no provider import) ---

_WORKFLOW_REQUIRED_ATTRS = ("id", "version", "accepts", "run")


def is_valid_workflow(obj: Any) -> bool:
    return all(hasattr(obj, attr) for attr in _WORKFLOW_REQUIRED_ATTRS)


def validate_workflow(obj: Any) -> list[str]:
    errors: list[str] = []
    for attr in _WORKFLOW_REQUIRED_ATTRS:
        if not hasattr(obj, attr):
            errors.append(f"missing attribute: {attr}")
    wf_id = getattr(obj, "id", None)
    if not isinstance(wf_id, str) or not wf_id:
        errors.append("id must be non-empty str")
    version = getattr(obj, "version", None)
    if not isinstance(version, str) or not version:
        errors.append("version must be non-empty str")
    return errors


class WorkflowRegistry:
    """In-memory registry for workflow lookup without importing providers."""

    def __init__(self) -> None:
        self._workflows: dict[str, Any] = {}

    def register(self, workflow: Any) -> None:
        errs = validate_workflow(workflow)
        if errs:
            raise ValueError(f"invalid workflow {getattr(workflow, 'id', '?')}: {errs}")
        self._workflows[workflow.id] = workflow

    def get(self, workflow_id: str) -> Any | None:
        return self._workflows.get(workflow_id)

    def list(self) -> list[Any]:
        return list(self._workflows.values())

    def resolve_for_work(self, work: Work) -> Any | None:
        for wf in self._workflows.values():
            try:
                if wf.accepts(work):
                    return wf
            except Exception:
                continue
        return None
