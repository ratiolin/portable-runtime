"""P2 protocol conformance: durable events, strict graph imports and API boundary."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

from portable_runtime.api.http import _require_local_control, create_app
from portable_runtime.core.models import Event, Run, Work
from portable_runtime.core.runtime import Runtime
from portable_runtime.records.authorization import create_grant_for_approval
from portable_runtime.records.models import Assertion
from portable_runtime.records.relations import RecordRelation
from portable_runtime.protocol.validation import validate_state_graph
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore


def _valid_state() -> dict[str, list[dict[str, object]]]:
    work = Work(id="work_p2", title="p2")
    run = Run(id="run_p2", work_id=work.id)
    assertion = Assertion(id="record_p2", statement="claim", lifecycle_status="draft", epistemic_status="unverified")
    relation = RecordRelation(id="relation_p2", relation_type="supports", subject_ref=assertion.id, object_ref=work.id)
    grant = create_grant_for_approval(
        principal_ref="human:owner",
        grantee_ref="agent:p2",
        allowed_capabilities=["text.echo"],
        subject_version_refs=["work_p2:v1"],
        source_decision_ref=None,
    )
    grant.id = "authz_p2"
    return {
        "work": [work.model_dump(mode="json")],
        "run": [run.model_dump(mode="json")],
        "record": [assertion.model_dump(mode="json")],
        "relation": [relation.model_dump(mode="json")],
        "authorization": [grant.model_dump(mode="json")],
    }


def test_state_import_rejects_dangling_graph_without_partial_write() -> None:
    store = InMemoryStateStore()
    store.save_work(Work(id="existing", title="kept"))
    bad = {"relation": [RecordRelation(relation_type="supports", subject_ref="missing", object_ref="existing").model_dump(mode="json")]}
    with pytest.raises(ValueError, match="dangling"):
        store.import_state(bad)
    assert store.get_work("existing") is not None
    assert store.list_relations() == []


def test_state_import_rejects_invalid_lineage_and_duplicate_active_superseder() -> None:
    store = InMemoryStateStore()
    old = Assertion(id="old_p2", statement="old", lifecycle_status="current", epistemic_status="unverified")
    first = Assertion(id="new1_p2", statement="new1", lifecycle_status="current", epistemic_status="unverified")
    second = Assertion(id="new2_p2", statement="new2", lifecycle_status="current", epistemic_status="unverified")
    invalid_revision = {
        "id": "revision_bad",
        "record_type": "Revision",
        "lifecycle_status": "applied",
        "version": 1,
        "metadata": {"from_version": 2, "to_version": 1},
        "subject_ref": old.id,
        "revises_ref": old.id,
        "produces_ref": first.id,
        "supersedes_ref": old.id,
    }
    bad = {
        "record": [old.model_dump(mode="json"), first.model_dump(mode="json"), second.model_dump(mode="json"), invalid_revision],
        "relation": [
            RecordRelation(relation_type="supersedes", subject_ref=first.id, object_ref=old.id).model_dump(mode="json"),
            RecordRelation(relation_type="supersedes", subject_ref=second.id, object_ref=old.id).model_dump(mode="json"),
        ],
    }
    with pytest.raises(ValueError, match="version lineage|duplicate active superseder"):
        store.import_state(bad)
    assert store.get_record(old.id) is None


def test_state_graph_validator_checks_core_edges_projection_refs_and_authorization_versions() -> None:
    state = _valid_state()
    state["work"][0].update({"parent_work_id": "missing_parent", "artifact_refs": ["missing_artifact"]})
    state["run"][0]["current_step"] = "missing_step"
    state["artifact"] = [{"id": "artifact_p2", "created_by_run_id": "missing_run"}]
    state["evidence"] = [{"id": "evidence_p2", "subject_refs": ["work_p2"], "artifact_refs": ["missing_artifact"]}]
    state["decision"] = [{"id": "decision_p2", "work_id": "work_p2", "rationale_artifact_refs": ["missing_artifact"]}]
    state["action"] = [{"id": "action_p2", "work_id": "work_p2", "run_id": "run_p2"}]
    state["outcome"] = [{"id": "outcome_p2", "action_id": "action_p2", "artifact_refs": ["missing_artifact"]}]
    state["step"] = [{"id": "step_p2", "run_id": "run_p2"}]
    state["attempt"] = [{"id": "attempt_p2", "step_id": "step_p2"}]
    state["checkpoint"] = [{"id": "checkpoint_p2", "run_id": "run_p2", "step_id": "step_p2", "payload_ref": "missing_payload"}]
    state["compensation"] = [{"id": "compensation_p2", "action_ref": "action_p2", "result_ref": "missing_result"}]
    state["event"] = [{"id": "event_p2", "subject_ref": "request_external", "payload": {}}]
    state["knowledge_projection"] = [{
        "id": "projection_p2",
        "source_work_refs": ["work_p2"],
        "current_assertion_refs": ["external:assertion:v1"],
        "evidence_summary_refs": ["missing_evidence"],
    }]
    state["authorization"].append({
        "id": "authz_missing_subject_version",
        "principal_ref": "human:owner",
        "grantee_ref": "agent:p2",
        "allowed_capabilities": ["text.echo"],
        "subject_version_refs": [],
    })

    errors = validate_state_graph(state, strict=False)

    assert any("missing_parent" in error for error in errors)
    assert any("missing subject version" in error for error in errors)
    assert any("missing_payload" in error for error in errors)


def test_state_graph_validator_reports_invalid_relation_shape_and_revision_lifecycle() -> None:
    state = _valid_state()
    state["relation"].append({
        "id": "bad_relation_p2",
        "relation_type": "not-a-relation",
        "subject_ref": "record_p2",
        "object_ref": "missing_object",
    })
    state["record"].append({
        "id": "bad_revision_p2",
        "record_type": "Revision",
        "lifecycle_status": "applied",
        "version": 1,
        "metadata": {"previous_lifecycle_status": "proposed", "from_version": "2", "to_version": "1"},
        "revises_ref": "record_p2",
        "produces_ref": "record_p2",
        "supersedes_ref": "record_p2",
    })

    errors = validate_state_graph(state, strict=False)

    assert any("invalid relation" in error for error in errors)
    assert any("invalid version lineage" in error for error in errors)


def test_sqlite_import_is_atomic_on_graph_failure(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "p2.db")
    store.save_work(Work(id="kept_sqlite", title="kept"))
    bad = {"run": [Run(id="orphan_run", work_id="missing_work").model_dump(mode="json")]}
    with pytest.raises(ValueError, match="dangling"):
        store.import_state(bad)
    assert store.get_work("kept_sqlite") is not None
    assert store.get_run("orphan_run") is None
    store.close()


def test_critical_runtime_transitions_are_journaled() -> None:
    runtime = Runtime(store=InMemoryStateStore())
    work = runtime.create_work(title="lease")
    run = runtime.start_run(work.id)
    assert runtime.acquire_lease(run.id, "owner-a") is True
    assert runtime.acquire_lease(run.id, "owner-b") is False
    event_types = {event.type for event in runtime.store.list_events()}  # type: ignore[attr-defined]
    assert "LeaseAcquired" in event_types
    assert "FencingRejected" in event_types


def test_http_mutating_control_routes_are_local_only() -> None:
    from starlette.requests import Request

    remote = Request({"type": "http", "method": "POST", "path": "/v1/state/import", "headers": [], "client": ("198.51.100.7", 443), "query_string": b"", "scheme": "http", "server": ("example", 80), "root_path": "", "http_version": "1.1"})
    with pytest.raises(HTTPException, match="local-only"):
        _require_local_control(remote)


@pytest.mark.asyncio
async def test_http_remote_client_cannot_import_state() -> None:
    runtime = Runtime(store=InMemoryStateStore())
    app = create_app(runtime)
    transport = httpx.ASGITransport(app=app, client=("198.51.100.7", 443))
    async with httpx.AsyncClient(transport=transport, base_url="http://example") as client:
        response = await client.post("/v1/state/import", json=_valid_state())
    assert response.status_code == 403
