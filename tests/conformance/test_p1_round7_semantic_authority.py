"""Round-seven P1 regression tests for semantic mutation and reopen authority."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from portable_runtime.api.cli import run_cli
from portable_runtime.api.http import create_app
from portable_runtime.core.runtime import Runtime
from portable_runtime.records.authorization import (
    CanonicalAuthorizationRequest,
    create_authorization_use,
)
from portable_runtime.records.models import Assertion
from portable_runtime.records.relations import RecordRelation
from portable_runtime.records.revision import apply_revision, create_revision
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore
from portable_runtime.records.authorization import AuthorizationGrant


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_existing_semantic_fact_cannot_be_overwritten_without_authority(tmp_path: Path, backend: str) -> None:
    store = (
        InMemoryStateStore()
        if backend == "memory"
        else SQLiteStateStore(tmp_path / "semantic.db")
    )
    try:
        record = Assertion(
            id=f"assertion_round7_{backend}",
            statement="canonical fact",
            lifecycle_status="draft",
        )
        store.save_record(record)

        # Caller-owned mutation must not mutate the durable snapshot before a
        # validated save, and a version-only write is not an authority proof.
        record.statement = "tampered in place"
        assert store.get_record(record.id).statement == "canonical fact"  # type: ignore[union-attr]
        changed = record.model_copy(update={"version": 2})
        with pytest.raises(ValueError, match="authority proof|version must advance"):
            store.save_record(changed)
        assert store.get_record(record.id).statement == "canonical fact"  # type: ignore[union-attr]
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_existing_relation_is_append_only(tmp_path: Path, backend: str) -> None:
    store = (
        InMemoryStateStore()
        if backend == "memory"
        else SQLiteStateStore(tmp_path / "relations.db")
    )
    try:
        relation = RecordRelation(
            id=f"relation_round7_{backend}",
            relation_type="supports",
            subject_ref="assertion:subject",
            object_ref="evidence:object",
        )
        store.save_relation(relation)
        changed = relation.model_copy(update={"relation_type": "contradicts"})
        with pytest.raises(ValueError, match="append-only|Revision authority"):
            store.save_relation(changed)
        assert store.get_relation(relation.id).relation_type == "supports"  # type: ignore[union-attr]
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()


def test_http_local_governance_edge_requires_authority() -> None:
    store = InMemoryStateStore()
    runtime = Runtime(store=store)
    old = Assertion(id="assertion_edge_old", statement="old", lifecycle_status="draft")
    new = Assertion(id="assertion_edge_new", statement="new", lifecycle_status="draft")
    store.save_record(old)
    store.save_record(new)
    client = TestClient(create_app(runtime))

    response = client.post(
        "/v1/relations",
        json={
            "relation_type": "validated-under",
            "subject_ref": old.id,
            "object_ref": new.id,
        },
    )
    assert response.status_code == 422
    assert store.list_relations() == []


def test_http_local_governance_edge_accepts_explicit_authority_ref() -> None:
    store = InMemoryStateStore()
    runtime = Runtime(store=store)
    old = Assertion(id="assertion_edge_authorized_old", statement="old", lifecycle_status="draft")
    new = Assertion(id="assertion_edge_authorized_new", statement="new", lifecycle_status="draft")
    store.save_record(old)
    store.save_record(new)
    client = TestClient(create_app(runtime))

    response = client.post(
        "/v1/relations",
        json={
            "relation_type": "validated-under",
            "subject_ref": old.id,
            "object_ref": new.id,
            "metadata": {"authorization_use_ref": "authuse:edge"},
        },
    )
    assert response.status_code == 200


def test_semantic_content_update_accepts_applied_revision_authority() -> None:
    store = InMemoryStateStore()
    old = Assertion(id="assertion_revision_target", statement="old", lifecycle_status="current", epistemic_status="supported")
    replacement = Assertion(id="assertion_revision_replacement", statement="replacement", lifecycle_status="draft")
    store.save_record(old)
    store.save_record(replacement)
    revision = create_revision(old.id, replacement.id)
    store.save_record(revision)
    grant = AuthorizationGrant(
        id="grant_round7_revision",
        principal_ref="human:owner",
        grantee_ref="agent:revision",
        allowed_capabilities=["revision.apply"],
        subject_version_refs=[revision.id],
    )
    store.save_authorization(grant)
    applied = apply_revision(
        revision,
        store=store,
        authorization_ref=grant.id,
        actor_ref="agent:revision",
        resource_ref=old.id,
    )
    changed = old.model_copy(
        update={
            "statement": "revised fact",
            "version": old.version + 1,
            "metadata": {"revision_ref": applied.id},
        }
    )
    store.save_record(changed)
    assert store.get_record(old.id).statement == "revised fact"  # type: ignore[union-attr]


def test_semantic_content_update_accepts_durable_authorization_use() -> None:
    store = InMemoryStateStore()
    record = Assertion(id="assertion_authuse_target", statement="old", lifecycle_status="draft")
    store.save_record(record)
    grant = AuthorizationGrant(
        id="grant_round7_record_write",
        principal_ref="human:owner",
        grantee_ref="agent:writer",
        allowed_capabilities=["record.write"],
        resource_scope=[record.id],
        effect_ceiling="write-local",
        subject_version_refs=[record.id, f"{record.id}:v{record.version}"],
    )
    store.save_authorization(grant)
    request = CanonicalAuthorizationRequest(
        capability="record.write",
        actor_ref="agent:writer",
        resource_ref=record.id,
        subject_version_refs=[record.id, f"{record.id}:v{record.version}"],
        effect_class="write-local",
    )
    use = create_authorization_use(grant, request)
    store.save_authorization_use(use)
    changed = record.model_copy(
        update={
            "statement": "authorized fact",
            "version": record.version + 1,
            "metadata": {
                "authorization_use_ref": use.id,
                "actor_ref": use.actor_ref,
                "resource_ref": use.resource_ref,
            },
        }
    )
    store.save_record(changed)
    assert store.get_record(record.id).statement == "authorized fact"  # type: ignore[union-attr]


def test_cli_reopen_record_is_atomic_and_materializes_lineage(tmp_path: Path) -> None:
    db = tmp_path / "cli-reopen.db"
    store = SQLiteStateStore(db)
    record = Assertion(id="assertion_cli_reopen", statement="claim", lifecycle_status="draft")
    store.save_record(record)
    store.close()
    assert run_cli(["--state", str(db), "reopen", record.id, "--reason", "reframe"]) == 0
    reopened = SQLiteStateStore(db)
    try:
        assert len(reopened.list_relations("supersedes")) == 1
        assert any(event.type == "ReopenCreated" for event in reopened.list_events())
    finally:
        reopened.close()


def test_reopen_lineage_failure_rolls_back_work_and_events() -> None:
    class FailingRelationStore(InMemoryStateStore):
        def save_relation(self, value: RecordRelation) -> None:  # type: ignore[override]
            raise RuntimeError("injected lineage failure")

    store = FailingRelationStore()
    runtime = Runtime(store=store)
    original = runtime.create_work(title="original", description="desc", kind="generic-task")
    client = TestClient(create_app(runtime))

    response = client.post(f"/v1/reopen/{original.id}", json={"reason": "reopen"})
    assert response.status_code == 422
    assert len(store.list_work()) == 1
    assert store.list_work()[0].id == original.id
    assert store.list_events() == []


def test_invalid_procedure_profile_is_not_silently_downgraded() -> None:
    runtime = Runtime(store=InMemoryStateStore())
    work = runtime.create_work(title="procedure", description="test")
    client = TestClient(create_app(runtime))

    response = client.get(f"/v1/procedures/{work.id}", params={"profile": "not-a-profile"})
    assert response.status_code == 422
    assert "invalid procedure profile" in response.json()["detail"]
