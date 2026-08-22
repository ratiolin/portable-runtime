from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from portable_runtime.api.http import create_app
from portable_runtime.core.runtime import Runtime
from portable_runtime.records.authorization import (
    AuthorizationGrant,
    CanonicalAuthorizationRequest,
    create_authorization_use,
    record_human_approval,
)
from portable_runtime.records.models import Assertion, EvidenceArtifact
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_record_write_requires_exact_predecessor_authorization(tmp_path: Path, backend: str) -> None:
    store = InMemoryStateStore() if backend == "memory" else SQLiteStateStore(tmp_path / f"{backend}.db")
    record = Assertion(id=f"record_{backend}", statement="before")
    store.save_record(record)
    grant = AuthorizationGrant(
        id=f"grant_{backend}",
        principal_ref="human:owner",
        grantee_ref="agent:writer",
        allowed_capabilities=["record.write"],
        resource_scope=[record.id],
        effect_ceiling="write-local",
        subject_version_refs=[f"{record.id}:v1"],
    )
    store.save_authorization(grant)
    use = create_authorization_use(
        grant,
        CanonicalAuthorizationRequest(
            capability="record.write",
            actor_ref="agent:writer",
            resource_ref=record.id,
            subject_version_refs=[f"{record.id}:v1"],
            effect_class="write-local",
        ),
    )
    store.save_authorization_use(use)
    updated = record.model_copy(
        update={
            "statement": "after",
            "version": 2,
            "metadata": {"authorization_use_ref": use.id},
        }
    )
    store.save_record(updated)
    assert store.get_record(record.id).statement == "after"

    wrong_grant = grant.model_copy(
        update={
            "id": f"wrong_{backend}",
            "allowed_capabilities": ["graph.write"],
            "subject_version_refs": [f"{record.id}:v2"],
        }
    )
    store.save_authorization(wrong_grant)
    wrong_use = create_authorization_use(
        wrong_grant,
        CanonicalAuthorizationRequest(
            capability="graph.write",
            actor_ref="agent:writer",
            resource_ref=record.id,
            subject_version_refs=[f"{record.id}:v2"],
            effect_class="write-local",
        ),
    )
    store.save_authorization_use(wrong_use)
    rejected = updated.model_copy(
        update={
            "statement": "third",
            "version": 3,
            "metadata": {"authorization_use_ref": wrong_use.id},
        }
    )
    with pytest.raises(ValueError, match="requires an applied Revision|AuthorizationUse"):
        store.save_record(rejected)


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_import_transition_is_atomic_and_proof_bound(tmp_path: Path, backend: str) -> None:
    store = InMemoryStateStore() if backend == "memory" else SQLiteStateStore(tmp_path / f"import-{backend}.db")
    record = Assertion(id=f"import_record_{backend}", statement="before")
    store.save_record(record)
    changed = record.model_copy(update={"statement": "tampered", "version": 2})
    baseline = store.export_state()
    with pytest.raises(ValueError):
        store.import_state({"record": [changed.model_dump(mode="json")]})
    assert store.export_state() == baseline

    grant = AuthorizationGrant(
        id=f"import_grant_{backend}",
        principal_ref="human:owner",
        grantee_ref="agent:writer",
        allowed_capabilities=["record.write"],
        resource_scope=[record.id],
        effect_ceiling="write-local",
        subject_version_refs=[f"{record.id}:v1"],
    )
    use = create_authorization_use(
        grant,
        CanonicalAuthorizationRequest(
            capability="record.write",
            actor_ref="agent:writer",
            resource_ref=record.id,
            subject_version_refs=[f"{record.id}:v1"],
            effect_class="write-local",
        ),
    )
    changed = changed.model_copy(update={"metadata": {"authorization_use_ref": use.id}})
    store.import_state(
        {
            "record": [changed.model_dump(mode="json")],
            "authorization": [grant.model_dump(mode="json")],
            "authorization_use": [use.model_dump(mode="json")],
        }
    )
    assert store.get_record(record.id).statement == "tampered"


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_authorization_use_is_immutable_but_identical_replay_is_idempotent(
    tmp_path: Path, backend: str
) -> None:
    store = InMemoryStateStore() if backend == "memory" else SQLiteStateStore(tmp_path / f"use-{backend}.db")
    grant = AuthorizationGrant(
        id=f"use_grant_{backend}",
        principal_ref="human:owner",
        grantee_ref="agent:writer",
        allowed_capabilities=["graph.write"],
        subject_version_refs=["object:v1"],
        effect_ceiling="write-local",
    )
    store.save_authorization(grant)
    use = create_authorization_use(
        grant,
        CanonicalAuthorizationRequest(
            capability="graph.write",
            actor_ref="agent:writer",
            resource_ref="object",
            subject_version_refs=["object:v1"],
            effect_class="write-local",
        ),
    )
    store.save_authorization_use(use)
    store.save_authorization_use(use.model_copy(deep=True))
    changed = use.model_copy(update={"actor_ref": "agent:other"})
    with pytest.raises(ValueError, match="immutable"):
        store.save_authorization_use(changed)


def test_http_relation_requires_matching_graph_use_and_rejects_fake_reopen() -> None:
    store = InMemoryStateStore()
    subject = Assertion(id="http_subject", statement="claim")
    evidence = EvidenceArtifact(id="http_evidence", uri="memory:evidence")
    store.save_record(subject)
    store.save_record(evidence)
    grant = AuthorizationGrant(
        id="http_grant",
        principal_ref="human:owner",
        grantee_ref="agent:graph",
        allowed_capabilities=["graph.write"],
        resource_scope=[subject.id],
        effect_ceiling="write-local",
        subject_version_refs=[f"{subject.id}:v1"],
    )
    store.save_authorization(grant)
    use = create_authorization_use(
        grant,
        CanonicalAuthorizationRequest(
            capability="graph.write",
            actor_ref="agent:graph",
            resource_ref=subject.id,
            subject_version_refs=[f"{subject.id}:v1"],
            effect_class="write-local",
        ),
    )
    store.save_authorization_use(use)
    client = TestClient(create_app(Runtime(store=store)))
    good = client.post(
        "/v1/relations",
        json={
            "relation_type": "validated-under",
            "subject_ref": subject.id,
            "object_ref": evidence.id,
            "metadata": {"authorization_use_ref": use.id},
        },
    )
    assert good.status_code == 200, good.text
    fake_reopen = client.post(
        "/v1/relations",
        json={
            "relation_type": "supersedes",
            "subject_ref": subject.id,
            "object_ref": evidence.id,
            "metadata": {"reopen_assessment_id": "reopen_fake"},
        },
    )
    assert fake_reopen.status_code == 422


def test_record_human_approval_does_not_alias_memory_snapshot() -> None:
    store = InMemoryStateStore()
    _decision, grant = record_human_approval(
        store,
        principal_ref="human:owner",
        grantee_ref="agent:writer",
        allowed_capabilities=["record.write"],
        subject_version_refs=["record:v1"],
    )
    grant.allowed_capabilities.append("deploy.prod")
    persisted = store.get_authorization(grant.id)
    assert persisted is not None
    assert "deploy.prod" not in persisted.allowed_capabilities
