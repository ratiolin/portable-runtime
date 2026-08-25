from __future__ import annotations

import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from portable_runtime.core.models import utcnow
from portable_runtime.governance.distinction import (
    APPLY_REVIEW_DISCHARGE,
    ApplicationReceipt,
    DistinctionState,
    GovernanceConfiguration,
    GovernanceDecision,
    GovernanceRuntime,
    GovernedApplication,
    ReviewObligation,
    candidate_state_effect,
    effect_matches_decision,
    linked,
    obligation_key,
    obligations_anchor,
    review_decision_input_matches,
    state_admissible_for,
    state_anchor,
)
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore

GOVERNANCE_STATE_KIND = "distinction_state"
GOVERNANCE_OBLIGATION_KIND = "review_obligation"
GOVERNANCE_DECISION_KIND = "governance_decision"
GOVERNANCE_APPLICATION_KIND = "governed_application"
GOVERNANCE_KINDS = frozenset(
    {
        GOVERNANCE_STATE_KIND,
        GOVERNANCE_OBLIGATION_KIND,
        GOVERNANCE_DECISION_KIND,
        GOVERNANCE_APPLICATION_KIND,
    }
)


class GovernancePersistenceError(ValueError):
    """A durable governance invariant would be violated."""


class _GovernanceEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    created_at: datetime = Field(default_factory=utcnow)


class PersistedDistinctionState(_GovernanceEnvelope):
    scheme_id: str
    qualification: str
    activation: str
    scope: frozenset[str]
    partition: tuple[frozenset[str], ...]
    version: int


class PersistedReviewObligation(_GovernanceEnvelope):
    target: str
    trigger_ref: str
    basis_refs: tuple[str, ...]
    context: str
    blocking: bool = True
    closure_requirements: frozenset[str] = frozenset()
    invalidates_decisions: frozenset[str] = frozenset()


class PersistedGovernanceDecision(_GovernanceEnvelope):
    actor: str
    operation: str
    target: str
    context: str
    review_refs: tuple[str, ...]
    disposition: str
    expected_state_anchor: str
    basis_anchors: tuple[tuple[str, str], ...]
    scope_snapshot: frozenset[str]
    partition_snapshot: tuple[frozenset[str], ...]
    closure_facts: frozenset[str] = frozenset()
    required_qualification: str | None = None
    required_activation: str | None = None
    superseded: bool = False


class PersistedGovernedApplication(_GovernanceEnvelope):
    actor: str
    operation: str
    scheme_id: str
    target: str
    decision_ref: str
    context: str
    new_qualification: str | None = None
    new_activation: str | None = None
    review_obligation_id: str | None = None
    effect_kind: str
    pre_anchor: str
    post_anchor: str
    committed_at: datetime = Field(default_factory=utcnow)


_MODEL_BY_KIND: dict[str, type[_GovernanceEnvelope]] = {
    GOVERNANCE_STATE_KIND: PersistedDistinctionState,
    GOVERNANCE_OBLIGATION_KIND: PersistedReviewObligation,
    GOVERNANCE_DECISION_KIND: PersistedGovernanceDecision,
    GOVERNANCE_APPLICATION_KIND: PersistedGovernedApplication,
}


def _semantic_dump(value: _GovernanceEnvelope) -> dict[str, object]:
    return cast(
        dict[str, object],
        value.model_dump(mode="json", exclude={"created_at", "committed_at"}),
    )


def _same_semantics(left: _GovernanceEnvelope, right: _GovernanceEnvelope) -> bool:
    return type(left) is type(right) and _semantic_dump(left) == _semantic_dump(right)


def _persist_state(scheme_id: str, state: DistinctionState) -> PersistedDistinctionState:
    return PersistedDistinctionState(
        id=scheme_id,
        scheme_id=scheme_id,
        qualification=state.qualification,
        activation=state.activation,
        scope=state.scope,
        partition=state.partition,
        version=state.version,
    )


def _restore_state(value: PersistedDistinctionState) -> DistinctionState:
    return DistinctionState(
        qualification=value.qualification,
        activation=value.activation,
        scope=value.scope,
        partition=value.partition,
        version=value.version,
    )


def _persist_obligation(value: ReviewObligation) -> PersistedReviewObligation:
    return PersistedReviewObligation(
        id=value.id,
        target=value.target,
        trigger_ref=value.trigger_ref,
        basis_refs=value.basis_refs,
        context=value.context,
        blocking=value.blocking,
        closure_requirements=value.closure_requirements,
        invalidates_decisions=value.invalidates_decisions,
    )


def _restore_obligation(value: PersistedReviewObligation) -> ReviewObligation:
    return ReviewObligation(
        id=value.id,
        target=value.target,
        trigger_ref=value.trigger_ref,
        basis_refs=value.basis_refs,
        context=value.context,
        blocking=value.blocking,
        closure_requirements=value.closure_requirements,
        invalidates_decisions=value.invalidates_decisions,
    )


def _persist_decision(value: GovernanceDecision) -> PersistedGovernanceDecision:
    return PersistedGovernanceDecision(
        id=value.id,
        actor=value.actor,
        operation=value.operation,
        target=value.target,
        context=value.context,
        review_refs=value.review_refs,
        disposition=value.disposition,
        expected_state_anchor=value.expected_state_anchor,
        basis_anchors=value.basis_anchors,
        scope_snapshot=value.scope_snapshot,
        partition_snapshot=value.partition_snapshot,
        closure_facts=value.closure_facts,
        required_qualification=value.required_qualification,
        required_activation=value.required_activation,
        superseded=value.superseded,
    )


def _restore_decision(value: PersistedGovernanceDecision) -> GovernanceDecision:
    return GovernanceDecision(
        id=value.id,
        actor=value.actor,
        operation=value.operation,
        target=value.target,
        context=value.context,
        review_refs=value.review_refs,
        disposition=value.disposition,
        expected_state_anchor=value.expected_state_anchor,
        basis_anchors=value.basis_anchors,
        scope_snapshot=value.scope_snapshot,
        partition_snapshot=value.partition_snapshot,
        closure_facts=value.closure_facts,
        required_qualification=value.required_qualification,
        required_activation=value.required_activation,
        superseded=value.superseded,
    )


def _persist_application(value: ApplicationReceipt) -> PersistedGovernedApplication:
    application = value.application
    return PersistedGovernedApplication(
        id=application.id,
        actor=application.actor,
        operation=application.operation,
        scheme_id=application.scheme_id,
        target=application.target,
        decision_ref=application.decision_ref,
        context=application.context,
        new_qualification=application.new_qualification,
        new_activation=application.new_activation,
        review_obligation_id=application.review_obligation_id,
        effect_kind=value.effect_kind,
        pre_anchor=value.pre_anchor,
        post_anchor=value.post_anchor,
    )


def _restore_application(value: PersistedGovernedApplication) -> ApplicationReceipt:
    application = GovernedApplication(
        id=value.id,
        actor=value.actor,
        operation=value.operation,
        scheme_id=value.scheme_id,
        target=value.target,
        decision_ref=value.decision_ref,
        context=value.context,
        new_qualification=value.new_qualification,
        new_activation=value.new_activation,
        review_obligation_id=value.review_obligation_id,
    )
    return ApplicationReceipt(
        application=application,
        effect_kind=value.effect_kind,
        pre_anchor=value.pre_anchor,
        post_anchor=value.post_anchor,
    )


class DistinctionGovernancePersistence(ABC):
    """Durable projection of Gamma=(Q, Dec, App) plus governed state.

    Semantic admission remains owned by ``governance.distinction``. This layer
    preserves durable identity, responsibility linkage, provenance, and atomic
    commit invariants after admission.
    """

    @abstractmethod
    def _get_model(self, kind: str, identifier: str) -> _GovernanceEnvelope | None:
        raise NotImplementedError

    @abstractmethod
    def _list_models(self, kind: str) -> list[_GovernanceEnvelope]:
        raise NotImplementedError

    @abstractmethod
    def _put_model(self, kind: str, value: _GovernanceEnvelope) -> None:
        raise NotImplementedError

    @abstractmethod
    def _delete_model(self, kind: str, identifier: str) -> None:
        raise NotImplementedError

    @abstractmethod
    @contextmanager
    def _transaction(self) -> Iterator[None]:
        raise NotImplementedError

    def get_state(self, scheme_id: str) -> DistinctionState | None:
        value = self._get_model(GOVERNANCE_STATE_KIND, scheme_id)
        return _restore_state(value) if isinstance(value, PersistedDistinctionState) else None

    def list_states(self) -> dict[str, DistinctionState]:
        return {
            value.scheme_id: _restore_state(value)
            for value in self._list_models(GOVERNANCE_STATE_KIND)
            if isinstance(value, PersistedDistinctionState)
        }

    def seed_state(self, scheme_id: str, state: DistinctionState) -> None:
        if not state_admissible_for(scheme_id, state):
            raise GovernancePersistenceError("cannot seed an inadmissible distinction state")
        incoming = _persist_state(scheme_id, state)
        with self._transaction():
            existing = self._get_model(GOVERNANCE_STATE_KIND, scheme_id)
            if existing is not None:
                if isinstance(existing, PersistedDistinctionState) and _same_semantics(existing, incoming):
                    return
                message = (
                    f"distinction state {scheme_id!r} already exists; "
                    "governed transitions require an application receipt"
                )
                raise GovernancePersistenceError(message)
            self._put_model(GOVERNANCE_STATE_KIND, incoming)

    def get_obligation(self, obligation_id: str) -> ReviewObligation | None:
        value = self._get_model(GOVERNANCE_OBLIGATION_KIND, obligation_id)
        return _restore_obligation(value) if isinstance(value, PersistedReviewObligation) else None

    def list_obligations(self) -> dict[str, ReviewObligation]:
        return {
            value.id: _restore_obligation(value)
            for value in self._list_models(GOVERNANCE_OBLIGATION_KIND)
            if isinstance(value, PersistedReviewObligation)
        }

    def open_obligation(self, obligation: ReviewObligation) -> None:
        incoming = _persist_obligation(obligation)
        with self._transaction():
            existing = self._get_model(GOVERNANCE_OBLIGATION_KIND, obligation.id)
            if existing is not None:
                if isinstance(existing, PersistedReviewObligation) and _same_semantics(existing, incoming):
                    return
                raise GovernancePersistenceError(
                    f"review obligation {obligation.id!r} cannot be rebound"
                )
            key = obligation_key(obligation)
            if any(obligation_key(item) == key for item in self.list_obligations().values()):
                raise GovernancePersistenceError(
                    "equivalent review obligation is already open for this event instance"
                )
            self._put_model(GOVERNANCE_OBLIGATION_KIND, incoming)

    def get_decision(self, decision_id: str) -> GovernanceDecision | None:
        value = self._get_model(GOVERNANCE_DECISION_KIND, decision_id)
        return _restore_decision(value) if isinstance(value, PersistedGovernanceDecision) else None

    def list_decisions(self) -> dict[str, GovernanceDecision]:
        return {
            value.id: _restore_decision(value)
            for value in self._list_models(GOVERNANCE_DECISION_KIND)
            if isinstance(value, PersistedGovernanceDecision)
        }

    def get_application(self, application_id: str) -> ApplicationReceipt | None:
        value = self._get_model(GOVERNANCE_APPLICATION_KIND, application_id)
        return _restore_application(value) if isinstance(value, PersistedGovernedApplication) else None

    def list_applications(self) -> dict[str, ApplicationReceipt]:
        return {
            value.id: _restore_application(value)
            for value in self._list_models(GOVERNANCE_APPLICATION_KIND)
            if isinstance(value, PersistedGovernedApplication)
        }

    def _configuration(self) -> GovernanceConfiguration:
        runtime = GovernanceRuntime(
            obligations=self.list_obligations(),
            decisions=self.list_decisions(),
            applications=self.list_applications(),
        )
        return GovernanceConfiguration(states=self.list_states(), runtime=runtime)

    def record_decision(self, decision: GovernanceDecision) -> None:
        incoming = _persist_decision(decision)
        with self._transaction():
            existing = self._get_model(GOVERNANCE_DECISION_KIND, decision.id)
            if existing is not None:
                if isinstance(existing, PersistedGovernanceDecision) and _same_semantics(existing, incoming):
                    return
                raise GovernancePersistenceError(
                    f"governance decision {decision.id!r} cannot be rebound"
                )
            if decision.target not in self.list_states():
                raise GovernancePersistenceError(
                    "governance decision references unknown target state"
                )
            if not review_decision_input_matches(decision, self._configuration()):
                raise GovernancePersistenceError(
                    "governance decision does not match its open review inputs"
                )
            self._put_model(GOVERNANCE_DECISION_KIND, incoming)

    def _require_fresh_application_id(self, application_id: str) -> None:
        if self._get_model(GOVERNANCE_APPLICATION_KIND, application_id) is not None:
            raise GovernancePersistenceError(
                f"governed application {application_id!r} is immutable and cannot be replayed or rebound"
            )

    def commit_state_application(
        self,
        scheme_id: str,
        next_state: DistinctionState,
        receipt: ApplicationReceipt,
    ) -> None:
        application = receipt.application
        with self._transaction():
            self._require_fresh_application_id(application.id)
            current = self.get_state(scheme_id)
            if current is None:
                raise GovernancePersistenceError(
                    "state application references unknown distinction state"
                )
            decision = self.get_decision(application.decision_ref)
            if decision is None:
                raise GovernancePersistenceError(
                    "state application references unknown governance decision"
                )
            linked_correctly = (
                receipt.effect_kind == "state"
                and application.scheme_id == scheme_id
                and application.target == scheme_id
                and decision.target == scheme_id
                and linked(application, decision)
            )
            if not linked_correctly:
                raise GovernancePersistenceError(
                    "state application responsibility linkage is invalid"
                )
            if receipt.pre_anchor != state_anchor(current):
                raise GovernancePersistenceError(
                    "state application pre-anchor does not match persisted state"
                )
            if receipt.pre_anchor != decision.expected_state_anchor:
                raise GovernancePersistenceError(
                    "state application does not start from the decision basis state"
                )
            candidate = candidate_state_effect(application, current)
            if candidate != next_state:
                raise GovernancePersistenceError(
                    "state application next state is not its declared candidate effect"
                )
            candidate_valid = state_admissible_for(
                scheme_id,
                next_state,
            ) and effect_matches_decision(decision, next_state)
            if not candidate_valid:
                raise GovernancePersistenceError(
                    "state application candidate violates governed state invariants"
                )
            if receipt.post_anchor != state_anchor(next_state):
                raise GovernancePersistenceError(
                    "state application post-anchor does not match next state"
                )

            self._put_model(
                GOVERNANCE_STATE_KIND,
                _persist_state(scheme_id, next_state),
            )
            # Receipt second is deliberate: failure must roll back the state write.
            self._put_model(
                GOVERNANCE_APPLICATION_KIND,
                _persist_application(receipt),
            )

    def commit_review_discharge(
        self,
        obligation_id: str,
        receipt: ApplicationReceipt,
    ) -> None:
        application = receipt.application
        with self._transaction():
            self._require_fresh_application_id(application.id)
            obligation = self.get_obligation(obligation_id)
            if obligation is None:
                raise GovernancePersistenceError(
                    "review discharge references unknown obligation"
                )
            decision = self.get_decision(application.decision_ref)
            if decision is None:
                raise GovernancePersistenceError(
                    "review discharge references unknown governance decision"
                )
            linked_correctly = (
                receipt.effect_kind == "review_discharge"
                and application.operation == APPLY_REVIEW_DISCHARGE
                and application.review_obligation_id == obligation_id
                and application.target == f"review_obligation:{obligation_id}"
                and application.scheme_id == decision.target
                and obligation_id in decision.review_refs
                and obligation.target == decision.target
                and obligation.context == decision.context
                and linked(application, decision)
            )
            if not linked_correctly:
                raise GovernancePersistenceError(
                    "review discharge responsibility linkage is invalid"
                )

            current = self.list_obligations()
            if receipt.pre_anchor != obligations_anchor(current):
                raise GovernancePersistenceError(
                    "review discharge pre-anchor does not match open obligations"
                )
            remaining = dict(current)
            remaining.pop(obligation_id)
            if receipt.post_anchor != obligations_anchor(remaining):
                raise GovernancePersistenceError(
                    "review discharge post-anchor does not match remaining obligations"
                )

            self._delete_model(GOVERNANCE_OBLIGATION_KIND, obligation_id)
            # Receipt second is deliberate: failure must restore the obligation.
            self._put_model(
                GOVERNANCE_APPLICATION_KIND,
                _persist_application(receipt),
            )


class InMemoryDistinctionGovernancePersistence(DistinctionGovernancePersistence):
    """Private sidecar for ``InMemoryStateStore`` excluded from public export."""

    def __init__(self, store: InMemoryStateStore) -> None:
        self.store = store
        namespace = vars(store)
        raw_records = namespace.setdefault(
            "_distinction_governance_records",
            {kind: {} for kind in GOVERNANCE_KINDS},
        )
        self._records = cast(
            dict[str, dict[str, _GovernanceEnvelope]],
            raw_records,
        )
        self._lock: Any = namespace.setdefault(
            "_distinction_governance_lock",
            threading.RLock(),
        )
        for kind in GOVERNANCE_KINDS:
            self._records.setdefault(kind, {})

    def _get_model(self, kind: str, identifier: str) -> _GovernanceEnvelope | None:
        with self._lock:
            return self._records[kind].get(identifier)

    def _list_models(self, kind: str) -> list[_GovernanceEnvelope]:
        with self._lock:
            return list(self._records[kind].values())

    def _put_model(self, kind: str, value: _GovernanceEnvelope) -> None:
        self._records[kind][value.id] = value

    def _delete_model(self, kind: str, identifier: str) -> None:
        self._records[kind].pop(identifier, None)

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock:
            snapshot = {
                kind: dict(values)
                for kind, values in self._records.items()
            }
            try:
                yield
            except Exception:
                self._records.clear()
                self._records.update(snapshot)
                raise


class SQLiteDistinctionGovernancePersistence(DistinctionGovernancePersistence):
    """Private durable sidecar for ``SQLiteStateStore``.

    One generic table carries all governance kinds. Keeping it separate from
    ``runtime_records`` leaves current export/import bundles and Runtime
    Protocol 2.0 unchanged.
    """

    _CREATE_SQL = (
        "CREATE TABLE IF NOT EXISTS runtime_governance_records ("
        "kind TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL, "
        "created_at TEXT NOT NULL, PRIMARY KEY(kind, id))"
    )
    _GET_SQL = (
        "SELECT data FROM runtime_governance_records "
        "WHERE kind=? AND id=?"
    )
    _LIST_SQL = (
        "SELECT data FROM runtime_governance_records "
        "WHERE kind=? ORDER BY created_at, id"
    )
    _PUT_SQL = (
        "INSERT INTO runtime_governance_records(kind, id, data, created_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(kind, id) DO UPDATE SET "
        "data=excluded.data, created_at=excluded.created_at"
    )
    _DELETE_SQL = (
        "DELETE FROM runtime_governance_records WHERE kind=? AND id=?"
    )

    def __init__(self, store: SQLiteStateStore) -> None:
        self.store = store
        namespace = vars(store)
        self._connection = cast(sqlite3.Connection, namespace["_connection"])
        self._lock: Any = namespace["_lock"]
        with self._lock:
            self._connection.execute(self._CREATE_SQL)

    def _get_model(self, kind: str, identifier: str) -> _GovernanceEnvelope | None:
        model_type = _MODEL_BY_KIND[kind]
        with self._lock:
            row = self._connection.execute(
                self._GET_SQL,
                (kind, identifier),
            ).fetchone()
        return None if row is None else model_type.model_validate_json(row["data"])

    def _list_models(self, kind: str) -> list[_GovernanceEnvelope]:
        model_type = _MODEL_BY_KIND[kind]
        with self._lock:
            rows = self._connection.execute(
                self._LIST_SQL,
                (kind,),
            ).fetchall()
        return [model_type.model_validate_json(row["data"]) for row in rows]

    def _put_model(self, kind: str, value: _GovernanceEnvelope) -> None:
        payload = value.model_dump(mode="json")
        self._connection.execute(
            self._PUT_SQL,
            (
                kind,
                value.id,
                json.dumps(payload, ensure_ascii=False),
                value.created_at.isoformat(),
            ),
        )

    def _delete_model(self, kind: str, identifier: str) -> None:
        self._connection.execute(
            self._DELETE_SQL,
            (kind, identifier),
        )

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock:
            owns_transaction = not self._connection.in_transaction
            if owns_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield
                if owns_transaction:
                    self._connection.execute("COMMIT")
            except Exception:
                if owns_transaction and self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise
