"""Batch8 API integration tests — covers new semantic plane endpoints."""
from __future__ import annotations

from fastapi.testclient import TestClient

from portable_runtime.api.http import create_app
from portable_runtime.core.models import KnowledgeItem
from portable_runtime.core.runtime import Runtime
from portable_runtime.records.models import Assertion, EvidenceArtifact
from portable_runtime.records.relations import RecordRelation
from portable_runtime.stores.memory import InMemoryStateStore


def _client() -> tuple[TestClient, Runtime, InMemoryStateStore]:
    store = InMemoryStateStore()
    runtime = Runtime(store=store)
    app = create_app(runtime)
    client = TestClient(app)
    return client, runtime, store


# /v1/records
def test_records_list_and_get():
    client, runtime, store = _client()
    resp = client.get("/v1/records")
    assert resp.status_code == 200
    assert resp.json() == [] or isinstance(resp.json(), list)

    rec = Assertion(statement="hello world", epistemic_status="supported", lifecycle_status="draft")
    store.save_record(rec)
    resp = client.get("/v1/records")
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json()]
    assert rec.id in ids

    resp = client.get("/v1/records", params={"record_type": "Assertion"})
    assert resp.status_code == 200
    assert all(r["record_type"] == "Assertion" for r in resp.json())

    resp = client.get(f"/v1/records/{rec.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == rec.id

    resp = client.get("/v1/records/nonexistent-id-xyz")
    assert resp.status_code == 404


# /v1/relations
def test_relations_create_and_list():
    client, _runtime, store = _client()
    resp = client.get("/v1/relations")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    store.save_record(EvidenceArtifact(id="evidence_1", uri="memory:evidence"))
    store.save_record(Assertion(id="assertion_1", statement="claim", lifecycle_status="draft"))
    payload = {
        "relation_type": "supports",
        "subject_ref": "evidence_1",
        "object_ref": "assertion_1",
    }
    resp = client.post("/v1/relations", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["relation_type"] == "supports"
    assert data["subject_ref"] == "evidence_1"

    resp = client.get("/v1/relations")
    assert any(r["subject_ref"] == "evidence_1" for r in resp.json())

    resp = client.post("/v1/relations", json={"subject_ref": "a"})
    assert resp.status_code == 400

    resp = client.post(
        "/v1/relations",
        json={"relation_type": "", "subject_ref": "a", "object_ref": "b"},
    )
    assert resp.status_code in (200, 400)


def test_relations_filter_by_type():
    client, _runtime, store = _client()
    for rid in ("e1", "e2"):
        store.save_record(EvidenceArtifact(id=rid, uri=f"memory:{rid}"))
    store.save_record(Assertion(id="a1", statement="claim", lifecycle_status="draft"))
    r1 = RecordRelation(relation_type="supports", subject_ref="e1", object_ref="a1")
    r2 = RecordRelation(relation_type="contradicts", subject_ref="e2", object_ref="a1")
    store.save_relation(r1)
    store.save_relation(r2)
    resp = client.get("/v1/relations", params={"relation_type": "supports"})
    assert resp.status_code == 200
    for item in resp.json():
        assert item["relation_type"] == "supports"


# /v1/revalidation/pending
def test_revalidation_pending():
    client, _runtime, store = _client()
    resp = client.get("/v1/revalidation/pending")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    a1 = Assertion(
        statement="needs revalidation",
        epistemic_status="revalidation-required",
        lifecycle_status="draft",
    )
    a2 = Assertion(statement="ok", epistemic_status="supported", lifecycle_status="draft")
    store.save_record(a1)
    store.save_record(a2)
    resp = client.get("/v1/revalidation/pending")
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json()]
    assert a1.id in ids
    assert a2.id not in ids


# /v1/revalidation/affected-by
def test_affected_by_endpoint():
    client, _runtime, store = _client()
    store.save_record(Assertion(id="assertion_X", statement="claim", lifecycle_status="draft"))
    rel = RecordRelation(
        relation_type="validated-under",
        subject_ref="assertion_X",
        object_ref="evaluator:v9",
    )
    store.save_relation(rel)
    resp = client.get(
        "/v1/revalidation/affected-by/evaluator:v9",
        params={"change_type": "evaluator"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(item["affected_ref"] == "assertion_X" for item in data)

    resp = client.get("/v1/revalidation/affected-by/unknown:change_xyz")
    assert resp.status_code == 200
    assert resp.json() == [] or isinstance(resp.json(), list)

    resp = client.get(
        "/v1/revalidation/affected-by/evaluator:v9",
        params={"change_type": "invalid-type"},
    )
    assert resp.status_code == 200


def test_affected_by_get_is_pure_and_materialization_is_explicit_control_action():
    client, _runtime, store = _client()
    store.save_record(
        Assertion(id="assertion_read_only", statement="claim", lifecycle_status="draft")
    )
    store.save_relation(
        RecordRelation(
            relation_type="validated-under",
            subject_ref="assertion_read_only",
            object_ref="evaluator:read-only",
        )
    )
    before = len(store.list_events())
    response = client.get(
        "/v1/revalidation/affected-by/evaluator:read-only",
        params={"change_type": "evaluator"},
    )
    assert response.status_code == 200
    assert len(store.list_events()) == before

    materialized = client.post(
        "/v1/revalidation/affected-by/evaluator:read-only/materialize",
        params={"change_type": "evaluator"},
    )
    assert materialized.status_code == 200
    assert len(store.list_events()) == before + 1
    assert store.list_events()[-1].type == "RevalidationRequired"


# /v1/reopen
def test_legacy_reopen_endpoint_cannot_create_work():
    client, runtime, store = _client()
    work = runtime.create_work(title="original work", description="desc", kind="generic-task")
    resp = client.post(
        f"/v1/reopen/{work.id}",
        json={"revision_scope": "problem-definition", "reason": "fix needed"},
    )
    assert resp.status_code == 422, resp.text
    assert "direct reopen-to-Work is retired" in resp.json()["detail"]
    assert [item.id for item in store.list_work()] == [work.id]

    resp = client.post("/v1/reopen/nonexistent-xyz", json={})
    assert resp.status_code == 404


# /v1/authorizations
def test_authorizations_and_policies():
    client, _runtime, _store = _client()
    resp = client.get("/v1/authorizations")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    resp = client.get("/v1/authorizations/nonexistent")
    assert resp.status_code == 404

    resp = client.get("/v1/policies")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert any("id" in p for p in resp.json())


# /v1/procedures
def test_procedures_endpoint():
    client, runtime, _store = _client()
    work = runtime.create_work(title="proc work")
    resp = client.get(f"/v1/procedures/{work.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["work_id"] == work.id
    assert "gates" in data

    resp = client.get("/v1/procedures/nonexistent-work-id")
    assert resp.status_code == 404


# /v1/steps
def test_steps_endpoint():
    client, runtime, _store = _client()
    work = runtime.create_work(title="step work")
    run = runtime.start_run(work.id, workflow_id="generic-task")
    from portable_runtime.core.models import Step

    step = Step(run_id=run.id, step_key="k1", kind="generic", status="pending")
    runtime.store.save_step(step)
    resp = client.get("/v1/steps")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    resp = client.get("/v1/steps", params={"run_id": run.id})
    assert resp.status_code == 200
    assert any(s["id"] == step.id for s in resp.json())


# /v1/knowledge negative filtering
def test_knowledge_and_negative():
    client, _runtime, store = _client()
    k1 = KnowledgeItem(
        kind="doc",
        title="positive",
        content_ref="ref1",
        status="candidate",
        evidence_refs=["ev1"],
        metadata={},
    )
    k2 = KnowledgeItem(
        kind="doc",
        title="negative with counterexample",
        content_ref="ref2",
        status="candidate",
        evidence_refs=[],
        metadata={"counterexample_refs": ["counter1"]},
    )
    k3 = KnowledgeItem(
        kind="doc",
        title="another negative",
        content_ref="ref3",
        status="candidate",
        metadata={"counterexample_refs": ["c2"]},
    )
    store.save_knowledge(k1)
    store.save_knowledge(k2)
    store.save_knowledge(k3)

    resp = client.get("/v1/knowledge")
    assert resp.status_code == 200
    data = resp.json()
    items = data["items"] if isinstance(data, dict) and "items" in data else data
    assert len(items) >= 3

    resp = client.get("/v1/knowledge", params={"negative": "true"})
    assert resp.status_code == 200
    data = resp.json()
    items = data["items"] if isinstance(data, dict) and "items" in data else data
    assert len(items) == 2
    titles = {i["title"] for i in items}
    assert "negative with counterexample" in titles
    assert "another negative" in titles
    assert "positive" not in titles

    resp = client.get(
        "/v1/knowledge",
        params={"limit": "1", "offset": "0", "negative": "true"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert data["total"] == 2

    resp = client.get("/v1/knowledge", params={"negative": "false"})
    assert resp.status_code == 200
    resp2 = client.get("/v1/knowledge")
    assert isinstance(resp2.json(), list)
    assert len(resp2.json()) == 3


def test_knowledge_get_single():
    client, _runtime, store = _client()
    k = KnowledgeItem(kind="doc", title="single", content_ref="ref", status="candidate")
    store.save_knowledge(k)
    resp = client.get(f"/v1/knowledge/{k.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == k.id
    resp = client.get("/v1/knowledge/nonexistent")
    assert resp.status_code == 404


# /v1/explain /v1/why /v1/lineage
def test_explain_why_lineage():
    client, _runtime, store = _client()
    rec = Assertion(
        statement="explain me",
        epistemic_status="supported",
        lifecycle_status="draft",
    )
    store.save_record(rec)
    rel = RecordRelation(
        relation_type="supports",
        subject_ref="evidence:42",
        object_ref=rec.id,
    )
    store.save_relation(rel)

    resp = client.get(f"/v1/explain/{rec.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["record_id"] == rec.id
    assert "lineage" in data
    assert any(r["id"] == rel.id for r in data["lineage"])

    resp = client.get(f"/v1/lineage/{rec.id}")
    assert resp.status_code == 200
    assert resp.json()["record_id"] == rec.id
    assert isinstance(resp.json()["lineage"], list)

    act_id = "action:123"
    r_why = RecordRelation(
        relation_type="produces",
        subject_ref=act_id,
        object_ref="outcome:1",
    )
    store.save_relation(r_why)
    resp = client.get(f"/v1/why/{act_id}")
    assert resp.status_code == 200
    assert resp.json()["action_id"] == act_id
    assert len(resp.json()["relations"]) >= 1


# /v1/recovery/status
def test_recovery_status():
    client, _runtime, _store = _client()
    resp = client.get("/v1/recovery/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "stale_steps" in data
    assert "count" in data
    assert isinstance(data["stale_steps"], list)
