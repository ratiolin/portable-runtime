"""Opt-in local authority stores for application-bound RecoveryObservation.

These subclasses add only the store-owned commit/replay surface for one
RecoveryApplication-bound observation. They do not add provider calls,
Runtime consumption, repeatability authority, configured-provider binding,
retry, or fresh execution authority.
"""

from __future__ import annotations

from pathlib import Path

from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore
from portable_runtime.workflows.recovery_application_observation import (
    RecoveryApplicationObservationCommitRequest,
    prepare_recovery_application_observation_commit,
)
from portable_runtime.workflows.recovery_observation import (
    RECOVERY_OBSERVATION_EVENT,
    RecoveryObservation,
    recovery_application_observation_identity,
    recovery_observation_from_event,
    same_recovery_observation_semantics,
)


def _contains_application_bound_observation(
    state: dict[str, list[dict[str, object]]],
) -> bool:
    for raw in state.get("event", ()):
        if not isinstance(raw, dict) or raw.get("type") != RECOVERY_OBSERVATION_EVENT:
            continue
        payload = raw.get("payload")
        if isinstance(payload, dict) and payload.get("recovery_application_ref") is not None:
            return True
    return False


class RecoveryApplicationObservationInMemoryStateStore(InMemoryStateStore):
    """In-memory StateStore with explicit application-observation authority."""

    def commit_recovery_application_observation(
        self,
        request: RecoveryApplicationObservationCommitRequest,
    ) -> RecoveryObservation:
        with self.transaction():
            prepared = prepare_recovery_application_observation_commit(self, request)
            existing = self.get_event(prepared.event.id)
            if existing is not None:
                if not same_recovery_observation_semantics(existing, prepared.event):
                    raise ValueError("RecoveryApplicationObservation identity semantics rebound")
                return recovery_observation_from_event(existing)
            self._recovery_observation_commit_depth += 1
            try:
                self.append_event(prepared.event)
            finally:
                self._recovery_observation_commit_depth -= 1
            return prepared.observation

    def get_recovery_application_observation(
        self,
        recovery_application_ref: str,
    ) -> RecoveryObservation | None:
        event = self.get_event(
            recovery_application_observation_identity(recovery_application_ref)
        )
        if event is None:
            return None
        observation = recovery_observation_from_event(event)
        if observation.recovery_application_ref != recovery_application_ref:
            raise ValueError("RecoveryApplicationObservation application binding mismatch")
        return observation

    def import_state(self, state: dict[str, list[dict[str, object]]]) -> None:
        if _contains_application_bound_observation(state):
            raise ValueError(
                "P5 application-bound RecoveryObservation authority import is unsupported; "
                "durable authority must be created by commit_recovery_application_observation"
            )
        super().import_state(state)


class RecoveryApplicationObservationSQLiteStateStore(SQLiteStateStore):
    """SQLite StateStore with writer-serialized application-observation authority."""

    def commit_recovery_application_observation(
        self,
        request: RecoveryApplicationObservationCommitRequest,
    ) -> RecoveryObservation:
        with self._lock:
            owns_transaction = not self._connection.in_transaction
            if owns_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            try:
                prepared = prepare_recovery_application_observation_commit(self, request)
                existing = self.get_event(prepared.event.id)
                if existing is not None:
                    if not same_recovery_observation_semantics(existing, prepared.event):
                        raise ValueError(
                            "RecoveryApplicationObservation identity semantics rebound"
                        )
                    observation = recovery_observation_from_event(existing)
                    if owns_transaction:
                        self._connection.execute("COMMIT")
                    return observation
                self._recovery_observation_commit_depth += 1
                try:
                    self.append_event(prepared.event)
                finally:
                    self._recovery_observation_commit_depth -= 1
                if owns_transaction:
                    self._connection.execute("COMMIT")
                return prepared.observation
            except Exception:
                if owns_transaction:
                    self._rollback(self._connection.cursor())
                raise

    def get_recovery_application_observation(
        self,
        recovery_application_ref: str,
    ) -> RecoveryObservation | None:
        event = self.get_event(
            recovery_application_observation_identity(recovery_application_ref)
        )
        if event is None:
            return None
        observation = recovery_observation_from_event(event)
        if observation.recovery_application_ref != recovery_application_ref:
            raise ValueError("RecoveryApplicationObservation application binding mismatch")
        return observation

    def import_state(self, state: dict[str, list[dict[str, object]]]) -> None:
        if _contains_application_bound_observation(state):
            raise ValueError(
                "P5 application-bound RecoveryObservation authority import is unsupported; "
                "durable authority must be created by commit_recovery_application_observation"
            )
        super().import_state(state)
