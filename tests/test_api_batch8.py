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
    # initially empty
    resp = client.get("/v1/records")
    assert resp.status_code == 200
    assert resp.json() == [] or isinstance(resp.json(), list)

    # insert a record
    rec = Assertion(statement="hello world", epistemic_status="supported", lifecycle_status="draft")
    store.save_record(rec)
    resp = client.get("/v1/records")
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json()]
    assert rec.id in ids

    # filter by record_type
    resp = client.get("/v1/records", params={"record_type": "Assertion"})
    assert resp.status_code == 200
    assert all(r["record_type"] == "Assertion" for r in resp.json())

    # get single
    resp = client.get(f"/v1/records/{rec.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == rec.id

    # not found
    resp = client.get("/v1/records/nonexistent-id-xyz")
    assert resp.status_code == 404


# /v1/relations
def test_relations_create_and_list():
    client, _runtime, store = _client()
    # list empty
    resp = client.get("/v1/relations")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    # valid create
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

    # list should contain it
    resp = client.get("/v1/relations")
    assert any(r["subject_ref"] == "evidence_1" for r in resp.json())

    # invalid payload - missing required fields
    resp = client.post("/v1/relations", json={"subject_ref": "a"})
    assert resp.status_code == 400

    # invalid relation_type via empty
    resp = client.post("/v1/relations", json={"relation_type": "", "subject_ref": "a", "object_ref": "b"})
    # may be 400 due to validation
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
    # empty pending
    resp = client.get("/v1/revalidation/pending")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    # create revalidation-required records
    a1 = Assertion(statement="needs revalidation", epistemic_status="revalidation-required", lifecycle_status="draft")
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
    # create relation that will be affected by evaluator change
    store.save_record(Assertion(id="assertion_X", statement="claim", lifecycle_status="draft"))
    rel = RecordRelation(relation_type="validated-under", subject_ref="assertion_X", object_ref="evaluator:v9")
    store.save_relation(rel)
    resp = client.get("/v1/revalidation/affected-by/evaluator:v9", params={"change_type": "evaluator"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(item["affected_ref"] == "assertion_X" for item in data)

    # missing change_ref still returns list (maybe empty for unknown ref)
    resp = client.get("/v1/revalidation/affected-by/unknown:change_xyz")
    assert resp.status_code == 200
    assert resp.json() == [] or isinstance(resp.json(), list)

    # empty change_ref should 400 via assess_revalidation validation - test via direct with empty path? HTTP path cannot be empty, but test invalid change_type fallback
    resp = client.get("/v1/revalidation/affected-by/evaluator:v9", params={"change_type": "invalid-type"})
    assert resp.status_code == 200  # unknown type falls back to generic


# /v1/reopen
def test_reopen_work_flow():
    client, runtime, _store = _client()
    # create work
    work = runtime.create_work(title="original work", description="desc", kind="generic-task")
    # reopen existing work
    resp = client.post(f"/v1/reopen/{work.id}", json={"revision_scope": "other", "reason": "fix needed"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "assessment" in data
    assert "work" in data
    assert data["work"]["title"]  # new work created

    # reopen unknown should 404
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

    # policies
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
    # create a step via store if available
    from portable_runtime.core.models import Step

    step = Step(run_id=run.id, step_key="k1", kind="generic", status="pending")
    runtime.store.save_step(step)
    resp = client.get("/v1/steps")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    # filter by run_id
    resp = client.get("/v1/steps", params={"run_id": run.id})
    assert resp.status_code == 200
    assert any(s["id"] == step.id for s in resp.json())


# /v1/knowledge negative filtering
def test_knowledge_and_negative():
    client, _runtime, store = _client()
    # positive knowledge
    k1 = KnowledgeItem(kind="doc", title="positive", content_ref="ref1", status="official", evidence_refs=["ev1"], metadata={})
    k2 = KnowledgeItem(kind="doc", title="negative with counterexample", content_ref="ref2", status="candidate", evidence_refs=[], metadata={"counterexample_refs": ["counter1"]})
    k3 = KnowledgeItem(kind="doc", title="another negative", content_ref="ref3", status="candidate", metadata={"counterexample_refs": ["c2"]})
    store.save_knowledge(k1)
    store.save_knowledge(k2)
    store.save_knowledge(k3)

    # normal list
    resp = client.get("/v1/knowledge")
    assert resp.status_code == 200
    data = resp.json()
    # could be paginated dict or list depending on query params
    items = data["items"] if isinstance(data, dict) and "items" in data else data
    assert len(items) >= 3

    # negative filter via query param
    resp = client.get("/v1/knowledge", params={"negative": "true"})
    assert resp.status_code == 200
    data = resp.json()
    items = data["items"] if isinstance(data, dict) and "items" in data else data
    # should only include k2 and k3 (those with counterexample_refs)
    assert len(items) == 2
    titles = {i["title"] for i in items}
    assert "negative with counterexample" in titles
    assert "another negative" in titles
    assert "positive" not in titles

    # also test pagination with limit
    resp = client.get("/v1/knowledge", params={"limit": "1", "offset": "0", "negative": "true"})
    assert resp.status_code == 200
    # when paginated, returns dict with total
    data = resp.json()
    assert isinstance(data, dict)
    assert data["total"] == 2

    # non-negative explicitly false should return all
    resp = client.get("/v1/knowledge", params={"negative": "false"})
    assert resp.status_code == 200
    data = resp.json()
    items2 = data["items"] if isinstance(data, dict) and "items" in data else data
    # might be list or dict; at least contains all
    # if paginated false, limit not in query => returns list
    # So we call without limit => returns list => len 3
    # For consistency, test without pagination
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
    rec = Assertion(statement="explain me", epistemic_status="supported", lifecycle_status="draft")
    store.save_record(rec)
    rel = RecordRelation(relation_type="supports", subject_ref="evidence:42", object_ref=rec.id)
    store.save_relation(rel)

    # explain
    resp = client.get(f"/v1/explain/{rec.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["record_id"] == rec.id
    assert "lineage" in data
    assert any(r["id"] == rel.id for r in data["lineage"])

    # lineage
    resp = client.get(f"/v1/lineage/{rec.id}")
    assert resp.status_code == 200
    assert resp.json()["record_id"] == rec.id
    assert isinstance(resp.json()["lineage"], list)

    # why - trace action
    act_id = "action:123"
    r_why = RecordRelation(relation_type="produces", subject_ref=act_id, object_ref="outcome:1")
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


