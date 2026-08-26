"""Authority-capable local stores for DurableInvocationSpecification.

These subclasses intentionally opt in to invocation-specification authority
without expanding the baseline StateStore used by Runtime. Specification
persistence is therefore available locally while Runtime/retry consumption
remains structurally absent.
"""

from __future__ import annotations

from pathlib import Path

from portable_runtime.core.models import Event
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore
from portable_runtime.workflows.invocation_specification import (
    INVOCATION_SPECIFICATION_EVENT,
    DurableInvocationSpecification,
    InvocationSpecificationCommitRequest,
    invocation_specification_from_event,
    prepare_invocation_specification_commit,
)


class InvocationSpecificationInMemoryStateStore(InMemoryStateStore):
    """In-memory StateStore with explicit local specification authority."""

    def __init__(self) -> None:
        super().__init__()
        self._invocation_specification_commit_depth = 0

    def commit_invocation_specification(
        self,
        request: InvocationSpecificationCommitRequest,
    ) -> DurableInvocationSpecification:
        with self.transaction():
            plan = prepare_invocation_specification_commit(self, request)
            if plan.replayed:
                return plan.specification
            if plan.event is None:
                raise ValueError("InvocationSpecification commit plan is missing durable event")
            self._invocation_specification_commit_depth += 1
            try:
                self.append_event(plan.event)
            finally:
                self._invocation_specification_commit_depth -= 1
            return plan.specification

    def append_event(self, value: Event) -> None:
        if (
            value.type == INVOCATION_SPECIFICATION_EVENT
            and self._invocation_specification_commit_depth <= 0
        ):
            raise ValueError(
                "InvocationSpecification events require commit_invocation_specification"
            )
        super().append_event(value)

    def get_invocation_specification(
        self,
        specification_id: str,
    ) -> DurableInvocationSpecification | None:
        event = self.get_event(specification_id)
        if event is None:
            return None
        if event.type != INVOCATION_SPECIFICATION_EVENT:
            return None
        return invocation_specification_from_event(event)

    def import_state(self, state: dict[str, list[dict[str, object]]]) -> None:
        if any(
            isinstance(raw, dict) and raw.get("type") == INVOCATION_SPECIFICATION_EVENT
            for raw in state.get("event", ())
        ):
            raise ValueError(
                "P5 InvocationSpecification authority import is unsupported; "
                "durable specification authority must be created by commit_invocation_specification"
            )
        super().import_state(state)


class InvocationSpecificationSQLiteStateStore(SQLiteStateStore):
    """SQLite StateStore with writer-serialized local specification authority."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self._invocation_specification_commit_depth = 0

    def commit_invocation_specification(
        self,
        request: InvocationSpecificationCommitRequest,
    ) -> DurableInvocationSpecification:
        with self._lock:
            owns_transaction = not self._connection.in_transaction
            if owns_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            try:
                plan = prepare_invocation_specification_commit(self, request)
                if not plan.replayed:
                    if plan.event is None:
                        raise ValueError(
                            "InvocationSpecification commit plan is missing durable event"
                        )
                    self._invocation_specification_commit_depth += 1
                    try:
                        self.append_event(plan.event)
                    finally:
                        self._invocation_specification_commit_depth -= 1
                if owns_transaction:
                    self._connection.execute("COMMIT")
                return plan.specification
            except Exception:
                if owns_transaction:
                    self._rollback(self._connection.cursor())
                raise

    def append_event(self, value: Event) -> None:
        if (
            value.type == INVOCATION_SPECIFICATION_EVENT
            and self._invocation_specification_commit_depth <= 0
        ):
            raise ValueError(
                "InvocationSpecification events require commit_invocation_specification"
            )
        super().append_event(value)

    def get_invocation_specification(
        self,
        specification_id: str,
    ) -> DurableInvocationSpecification | None:
        event = self.get_event(specification_id)
        if event is None:
            return None
        if event.type != INVOCATION_SPECIFICATION_EVENT:
            return None
        return invocation_specification_from_event(event)

    def import_state(self, state: dict[str, list[dict[str, object]]]) -> None:
        if any(
            isinstance(raw, dict) and raw.get("type") == INVOCATION_SPECIFICATION_EVENT
            for raw in state.get("event", ())
        ):
            raise ValueError(
                "P5 InvocationSpecification authority import is unsupported; "
                "durable specification authority must be created by commit_invocation_specification"
            )
        super().import_state(state)
