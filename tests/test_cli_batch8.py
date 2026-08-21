"""Batch8 CLI integration tests — explain/why/evidence/lineage/affected-by/reopen/revalidation/authorization/recovery/knowledge negative."""
from __future__ import annotations

import contextlib
import io
import json
import pathlib

from portable_runtime.api.cli import run_cli
from portable_runtime.core.models import KnowledgeItem
from portable_runtime.core.runtime import Runtime
from portable_runtime.records.models import Assertion
from portable_runtime.records.relations import RecordRelation
from portable_runtime.stores.sqlite import SQLiteStateStore


def _capture(args: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            rc = run_cli(args)
        except SystemExit as exc:
            rc = int(exc.code) if exc.code is not None else 1
    return rc, buf.getvalue()


def _seed(tmp_path: pathlib.Path) -> pathlib.Path:
    db = tmp_path / "cli_batch8.db"
    return db


def test_cli_knowledge_negative_filter(tmp_path):
    db = _seed(tmp_path)
    # seed via store
    store = SQLiteStateStore(db)
    runtime = Runtime(store=store)
    k_pos = KnowledgeItem(kind="doc", title="positive knowledge", content_ref="ref_pos", status="official", metadata={})
    k_neg = KnowledgeItem(kind="doc", title="negative knowledge", content_ref="ref_neg", status="candidate", metadata={"counterexample_refs": ["counter1"]})
    k_neg2 = KnowledgeItem(kind="doc", title="another negative", content_ref="ref_neg2", status="candidate", metadata={"counterexample_refs": ["c2", "c3"]})
    store.save_knowledge(k_pos)
    store.save_knowledge(k_neg)
    store.save_knowledge(k_neg2)
    store.close()

    # list all
    rc, out = _capture(["--state", str(db), "knowledge", "list"])
    assert rc == 0
    data = json.loads(out)
    assert isinstance(data, list)
    assert len(data) == 3

    # list negative only
    rc, out = _capture(["--state", str(db), "knowledge", "list", "--negative"])
    assert rc == 0
    data_neg = json.loads(out)
    assert isinstance(data_neg, list)
    assert len(data_neg) == 2, f"expected 2 negative, got {data_neg}"
    titles = {item["title"] for item in data_neg}
    assert "negative knowledge" in titles
    assert "another negative" in titles
    assert "positive knowledge" not in titles

    # distinguish: positive not in negative result, but in normal
    all_titles = {item["title"] for item in data}
    assert "positive knowledge" in all_titles


def test_cli_explain_and_lineage(tmp_path):
    db = _seed(tmp_path)
    store = SQLiteStateStore(db)
    runtime = Runtime(store=store)
    rec = Assertion(statement="explainable", epistemic_status="supported", lifecycle_status="draft")
    store.save_record(rec)
    rel = RecordRelation(relation_type="supports", subject_ref="evidence:99", object_ref=rec.id)
    store.save_relation(rel)
    store.close()

    rc, out = _capture(["--state", str(db), "explain", rec.id])
    assert rc == 0, out
    data = json.loads(out)
    assert "record" in data
    assert "lineage" in data
    assert any(r["id"] == rel.id for r in data["lineage"])
    # ensure json parseable
    assert data["record"]["id"] == rec.id

    rc, out = _capture(["--state", str(db), "lineage", rec.id])
    assert rc == 0
    data = json.loads(out)
    assert data["record_id"] == rec.id
    assert isinstance(data["lineage"], list)

    # explain not found should return 1
    rc, out = _capture(["--state", str(db), "explain", "nonexistent-xyz"])
    assert rc == 1
    assert "record not found" in out


def test_cli_why(tmp_path):
    db = _seed(tmp_path)
    store = SQLiteStateStore(db)
    runtime = Runtime(store=store)
    rel1 = RecordRelation(relation_type="produces", subject_ref="action:777", object_ref="outcome:777")
    rel2 = RecordRelation(relation_type="authorizes", subject_ref="decision:777", object_ref="action:777")
    store.save_relation(rel1)
    store.save_relation(rel2)
    store.close()

    rc, out = _capture(["--state", str(db), "why", "action:777"])
    assert rc == 0
    data = json.loads(out)
    assert data["action_id"] == "action:777"
    assert isinstance(data["relations"], list)
    assert len(data["relations"]) >= 2


def test_cli_evidence(tmp_path):
    db = _seed(tmp_path)
    store = SQLiteStateStore(db)
    runtime = Runtime(store=store)
    # assertion with supporting evidence relation
    assertion = Assertion(statement="needs support", epistemic_status="supported", lifecycle_status="draft")
    store.save_record(assertion)
    rel = RecordRelation(relation_type="supports", subject_ref="evidence:a", object_ref=assertion.id)
    store.save_relation(rel)
    store.close()

    rc, out = _capture(["--state", str(db), "evidence", assertion.id])
    assert rc == 0, out
    data = json.loads(out)
    assert data["assertion_id"] == assertion.id
    assert "supported" in data
    assert data["supported"] is True
    assert isinstance(data["supporting_relations"], list)

    # unsupported assertion
    unsupported = Assertion(statement="unsupported", epistemic_status="unverified", lifecycle_status="draft")
    store = SQLiteStateStore(db)
    store.save_record(unsupported)
    store.close()
    rc, out = _capture(["--state", str(db), "evidence", unsupported.id])
    assert rc == 0
    data = json.loads(out)
    assert data["supported"] is False


def test_cli_affected_by(tmp_path):
    db = _seed(tmp_path)
    store = SQLiteStateStore(db)
    runtime = Runtime(store=store)
    rel = RecordRelation(relation_type="validated-under", subject_ref="assertion:affected", object_ref="evaluator:v8")
    store.save_relation(rel)
    store.close()

    rc, out = _capture(["--state", str(db), "affected-by", "evaluator:v8", "--change-type", "evaluator"])
    assert rc == 0, out
    data = json.loads(out)
    assert isinstance(data, list)
    assert any(item["affected_ref"] == "assertion:affected" for item in data)

    # via revalidation affected-by subcommand
    rc, out = _capture(["--state", str(db), "revalidation", "affected-by", "evaluator:v8", "--change-type", "evaluator"])
    assert rc == 0
    data2 = json.loads(out)
    assert isinstance(data2, list)


def test_cli_reopen(tmp_path):
    db = _seed(tmp_path)
    # need a work to reopen
    store = SQLiteStateStore(db)
    runtime = Runtime(store=store)
    work = runtime.create_work(title="to reopen", description="original")
    store.close()
    # reopen via cli
    rc, out = _capture(["--state", str(db), "reopen", work.id, "--scope", "other", "--reason", "test reopen"])
    assert rc == 0, out
    data = json.loads(out)
    assert "assessment" in data
    assert "work" in data
    assert data["assessment"]["record_ref"] == work.id

    # reopen nonexistent should fail
    rc, out = _capture(["--state", str(db), "reopen", "nonexistent-id"])
    assert rc == 1
    assert "record not found" in out


def test_cli_unresolved(tmp_path):
    db = _seed(tmp_path)
    store = SQLiteStateStore(db)
    runtime = Runtime(store=store)
    # contested assertion -> unresolved
    contested = Assertion(statement="contested claim", epistemic_status="contested", lifecycle_status="draft")
    store.save_record(contested)
    # blocked work as well
    work = runtime.create_work(title="blocked work")
    from portable_runtime.core.models import utcnow
    blocked = work.model_copy(update={"status": "blocked", "updated_at": utcnow()})
    store.save_work(blocked)
    store.close()

    rc, out = _capture(["--state", str(db), "unresolved"])
    assert rc == 0
    data = json.loads(out)
    assert "records" in data
    assert "works" in data
    # should contain contested record or blocked work
    assert len(data["records"]) >= 1 or len(data["works"]) >= 1


def test_cli_revalidation_pending(tmp_path):
    db = _seed(tmp_path)
    store = SQLiteStateStore(db)
    runtime = Runtime(store=store)
    pending_rec = Assertion(statement="needs revalidation", epistemic_status="revalidation-required", lifecycle_status="draft")
    ok_rec = Assertion(statement="ok", epistemic_status="supported", lifecycle_status="draft")
    store.save_record(pending_rec)
    store.save_record(ok_rec)
    store.close()

    rc, out = _capture(["--state", str(db), "revalidation", "pending"])
    assert rc == 0
    data = json.loads(out)
    assert isinstance(data, list)
    ids = [r["id"] for r in data]
    assert pending_rec.id in ids
    assert ok_rec.id not in ids


def test_cli_authorization(tmp_path):
    db = _seed(tmp_path)
    # authorization list may be empty; still should be json list
    rc, out = _capture(["--state", str(db), "authorization", "list"])
    assert rc == 0
    data = json.loads(out)
    assert isinstance(data, list)

    # authorization show nonexistent should indicate not found
    rc, out = _capture(["--state", str(db), "authorization", "show", "nonexistent-auth"])
    # CLI prints "authorization not found" and returns 1
    assert rc in (0, 1)
    # if rc ==0, out is json error; if rc==1, out contains not found
    if rc == 1:
        assert "authorization not found" in out or "not found" in out.lower()


def test_cli_recovery(tmp_path):
    db = _seed(tmp_path)
    rc, out = _capture(["--state", str(db), "recovery", "status"])
    assert rc == 0
    data = json.loads(out)
    assert "stale_steps" in data
    assert "count" in data
    assert isinstance(data["stale_steps"], list)
    # ensure json parseable and contains expected fields
    assert isinstance(data["count"], int)


def test_cli_knowledge_show(tmp_path):
    db = _seed(tmp_path)
    store = SQLiteStateStore(db)
    runtime = Runtime(store=store)
    k = KnowledgeItem(kind="doc", title="single", content_ref="ref_single", status="candidate")
    store.save_knowledge(k)
    store.close()
    rc, out = _capture(["--state", str(db), "knowledge", "show", k.id])
    assert rc == 0
    data = json.loads(out)
    assert data["id"] == k.id

    rc, out = _capture(["--state", str(db), "knowledge", "show", "nonexistent"])
    assert rc == 1


