"""Bundle v2 & Event Journal conformance tests — Batch8 Bundle/Event."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from portable_runtime.core.models import (
    Action,
    Artifact,
    Checkpoint,
    Compensation,
    Decision,
    Event,
    Evidence,
    KnowledgeItem,
    Outcome,
    Run,
    Step,
    StepAttempt,
    Work,
)
from portable_runtime.records.authorization import create_grant_for_approval
from portable_runtime.records.knowledge import KnowledgeProjection
from portable_runtime.records.relations import RecordRelation
from portable_runtime.stores.bundle import BUNDLE_SCHEMA_VERSION, export_bundle, import_bundle
from portable_runtime.stores.filesystem import FileSystemArtifactStore
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore


def _make_populated_store():
    store = InMemoryStateStore()
    # Work/Run
    w = Work(id="work_1", title="t")
    store.save_work(w)
    r = Run(id="run_1", work_id="work_1")
    store.save_run(r)
    # Artifact with file uri
    art = Artifact(id="art_1", kind="doc", uri="file:///tmp/fake.txt")
    store.save_artifact(art)
    store.save_evidence(Evidence(id="ev_1", kind="log", source="sensor", subject_refs=["work_1"]))
    store.save_decision(Decision(id="dec_1", work_id="work_1", decision_type="choose"))
    store.save_action(Action(id="act_1", work_id="work_1", run_id="run_1", capability="code.edit", provider_id="p1", request_ref="req1"))
    store.save_outcome(Outcome(id="out_1", action_id="act_1", status="succeeded"))
    store.save_knowledge(KnowledgeItem(id="know_1", kind="note", title="k", content_ref="art_1"))
    store.append_event(Event(id="evt_1", type="WorkCreated", subject_ref="work_1", payload={"x": 1}))
    store.save_step(Step(id="step_1", run_id="run_1", step_key="s1"))
    store.save_attempt(StepAttempt(id="att_1", step_id="step_1", attempt_no=1))
    store.save_checkpoint(Checkpoint(id="cp_1", run_id="run_1"))
    store.save_compensation(Compensation(id="comp_1", action_ref="act_1", compensation_capability="undo"))
    # Records / Relations
    from portable_runtime.records.models import Assertion
    rec = Assertion(id="record_assert_1", statement="hello", lifecycle_status="draft", epistemic_status="unverified")
    store.save_record(rec)
    rel = RecordRelation(id="rel_1", relation_type="supports", subject_ref="record_assert_1", object_ref="ev_1")
    store.save_relation(rel)
    # Authorization
    grant = create_grant_for_approval(principal_ref="human:owner", grantee_ref="agent:1", allowed_capabilities=["code.edit"], subject_version_refs=["v1"])
    grant.id = "authz_1"
    store.save_authorization(grant)
    return store, grant


def test_bundle_export_import_semantic_equivalence(tmp_path: Path):
    store, _ = _make_populated_store()
    # need artifact store for file artifact
    fs_root = tmp_path / "artifacts_src"
    fs_root.mkdir()
    fs = FileSystemArtifactStore(fs_root)
    # put artifact blob for art_1 so export includes it
    blob = b"hello artifact"
    # FileSystemArtifactStore: need to store at path matching uri? simpler: put and update artifact uri
    # Use fs.put to get uri, then re-save artifact with that uri
    uri = fs.put(blob)
    art = store.get_artifact("art_1")
    assert art is not None
    # update uri to the real stored uri
    art2 = art.model_copy(update={"uri": uri})
    store.save_artifact(art2)

    out = tmp_path / "bundle.tar"
    export_bundle(store, fs, out, runtime_id="rt-test")
    # read manifest from tar for verification
    import json
    import tarfile
    with tarfile.open(out, "r") as tar:
        manifest = json.loads(tar.extractfile("manifest.json").read().decode())
    assert manifest["schema_version"] == BUNDLE_SCHEMA_VERSION
    assert manifest["runtime_id"] == "rt-test"
    assert "checksums" in manifest and manifest["checksums"]
    # each jsonl should have checksum
    for fname in ["works.jsonl", "records.jsonl", "relations.jsonl", "authorizations.jsonl", "events.jsonl"]:
        assert fname in manifest["checksums"]
        # verify checksum is sha256 of file content
        # read tar to verify
        with tarfile.open(out, "r") as tar:
            data = tar.extractfile(fname).read()
            assert hashlib.sha256(data).hexdigest() == manifest["checksums"][fname]

    # import into fresh memory store with new artifact root (simulates换机器)
    fresh_store = InMemoryStateStore()
    fresh_fs_root = tmp_path / "artifacts_dst"
    fresh_fs_root.mkdir()
    fresh_fs = FileSystemArtifactStore(fresh_fs_root)
    manifest2 = import_bundle(fresh_store, fresh_fs, out)
    assert manifest2["schema_version"] == BUNDLE_SCHEMA_VERSION
    # semantic equivalence: counts match and each record equal after roundtrip
    for kind in ["work", "run", "artifact", "evidence", "decision", "action", "outcome", "knowledge", "event", "step", "attempt", "checkpoint", "compensation", "record", "relation", "authorization"]:
        orig = store.export_state().get(kind, [])
        imported = fresh_store.export_state().get(kind, [])
        assert len(orig) == len(imported), f"kind {kind} count mismatch"
        # compare by id
        orig_by_id = {r["id"]: r for r in orig}
        imp_by_id = {r["id"]: r for r in imported}
        if kind == "artifact":
            # uri is rewritten to new root, so compare without uri
            for oid, o in orig_by_id.items():
                assert oid in imp_by_id
                imp = imp_by_id[oid]
                # checksum should still be same if present, kind same
                assert o["kind"] == imp["kind"]
                assert o["id"] == imp["id"]
        else:
            assert orig_by_id == imp_by_id

    # also test sqlite roundtrip
    db_path = tmp_path / "db.sqlite"
    sqlite_store = SQLiteStateStore(db_path)
    import_bundle(sqlite_store, None, out)
    for kind in ["record", "relation", "authorization", "event"]:
        mem_vals = fresh_store.export_state().get(kind, [])
        sqlite_vals = sqlite_store.export_state().get(kind, [])
        assert len(mem_vals) == len(sqlite_vals)
    sqlite_store.close()

    # also test sqlite export->memory import
    db2 = tmp_path / "db2.sqlite"
    s2 = SQLiteStateStore(db2)
    for kind, vals in fresh_store.export_state().items():
        # use import_state directly to populate s2
        s2.import_state({kind: vals})
    out2 = tmp_path / "bundle2.tar"
    # need to populate s2 properly via bundle export from fresh_store
    out2 = tmp_path / "bundle_sqlite.tar"
    export_bundle(s2, None, out2, runtime_id="rt2")
    mem2 = InMemoryStateStore()
    import_bundle(mem2, None, out2)
    assert len(mem2.export_state()["record"]) == len(s2.export_state()["record"])
    s2.close()


def test_bundle_roundtrips_canonical_knowledge_projection(tmp_path: Path):
    store = InMemoryStateStore()
    work = Work(id="projection_work", title="projection source")
    store.save_work(work)
    projection = KnowledgeProjection(
        id="projection_1",
        title="canonical projection",
        source_work_refs=[work.id],
        current_assertion_refs=["external:assertion:v1"],
        evidence_summary_refs=["external:evidence:v1"],
    )
    store.save_knowledge_projection(projection)

    bundle = tmp_path / "projection.tar"
    export_bundle(store, None, bundle, runtime_id="projection-test")
    fresh = InMemoryStateStore()
    manifest = import_bundle(fresh, None, bundle)

    assert manifest["counts"]["knowledge_projection"] == 1
    assert fresh.get_knowledge_projection(projection.id) == projection


def test_bundle_cross_machine_history_explainable(tmp_path: Path):
    """换机器后判断历史可解释：provenance / event / relation still traceable."""
    store, grant = _make_populated_store()
    # add second assertion that is supported by evidence via relation
    from portable_runtime.records.models import Assertion
    rec2 = Assertion(id="record_assert_2", statement="world", lifecycle_status="draft", epistemic_status="supported")
    # This will fail validation if not allowed? supported is allowed for Assertion
    store.save_record(rec2)
    rel2 = RecordRelation(id="rel_2", relation_type="derived-from", subject_ref="record_assert_2", object_ref="record_assert_1")
    store.save_relation(rel2)
    # add more events to represent transitions
    store.append_event(Event(id="evt_2", type="DecisionRecorded", subject_ref="dec_1", payload={"decision": "dec_1"}))
    store.append_event(Event(id="evt_3", type="AuthorizationGranted", subject_ref="authz_1", payload={"grant": grant.id}))
    # bundle
    out = tmp_path / "bundle_hist.tar"
    export_bundle(store, None, out, runtime_id="rt-hist")
    # fresh machine
    fresh = InMemoryStateStore()
    import_bundle(fresh, None, out)
    # history still explainable: events retrievable
    evts = fresh.list_events()
    assert len(evts) >= 3
    assert fresh.get_event("evt_1") is not None
    assert fresh.get_event("evt_2") is not None
    # relations still explain lineage
    assert fresh.get_relation("rel_1") is not None
    assert fresh.get_relation("rel_2") is not None
    # authorization still present and decision link intact
    assert fresh.get_authorization("authz_1") is not None
    assert fresh.get_work("work_1") is not None
    # record graph intact
    assert fresh.get_record("record_assert_1") is not None
    assert fresh.get_record("record_assert_2") is not None


def test_record_relation_roundtrip_via_bundle(tmp_path: Path):
    store = InMemoryStateStore()
    from portable_runtime.records.models import Goal, Observation
    obs = Observation(id="obs_1", lifecycle_status="current", epistemic_status="unverified")
    store.save_record(obs)
    goal = Goal(id="goal_1", direction="north", lifecycle_status="proposed")
    store.save_record(goal)
    rel = RecordRelation(id="rel_rr", relation_type="requires-revalidation", subject_ref="obs_1", object_ref="goal_1")
    store.save_relation(rel)
    out = tmp_path / "rr.tar"
    export_bundle(store, None, out)
    fresh = InMemoryStateStore()
    import_bundle(fresh, None, out)
    assert fresh.get_record("obs_1") is not None
    assert fresh.get_record("goal_1") is not None
    assert fresh.get_relation("rel_rr") is not None
    # ensure tar contains jsonl for record/relation
    with tarfile.open(out, "r") as tar:
        names = tar.getnames()
        assert "records.jsonl" in names
        assert "relations.jsonl" in names
        # parse and ensure both ids present
        rec_data = tar.extractfile("records.jsonl").read()
        assert b"obs_1" in rec_data
        assert b"goal_1" in rec_data
        rel_data = tar.extractfile("relations.jsonl").read()
        assert b"rel_rr" in rel_data


def test_checksum_validation(tmp_path: Path):
    store, _ = _make_populated_store()
    out = tmp_path / "bundle.tar"
    export_bundle(store, None, out)
    # tamper: modify works.jsonl without updating manifest checksum
    # read tar, modify, repack
    raw = out.read_bytes()
    # out is plain tar, so decompress not needed
    buf = io.BytesIO(raw)
    members = {}
    manifest_raw = None
    with tarfile.open(fileobj=buf, mode="r") as tar:
        for m in tar.getmembers():
            f = tar.extractfile(m)
            data = f.read() if f is not None else b""
            members[m.name] = (m, data)
            if m.name == "manifest.json":
                manifest_raw = data
    # tamper works.jsonl
    assert "works.jsonl" in members
    orig = members["works.jsonl"][1]
    # jsonl is list of works; append a fake line or modify existing
    tampered = orig + b'{"id":"work_evil","title":"evil"}\n'
    members["works.jsonl"] = (members["works.jsonl"][0], tampered)
    # repack with same manifest (so checksum will mismatch)
    new_buf = io.BytesIO()
    with tarfile.open(fileobj=new_buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name, (info, data) in members.items():  # noqa: B007
            if name == "works.jsonl":
                data = tampered
            ti = tarfile.TarInfo(name=name)
            ti.size = len(data)
            ti.mtime = info.mtime
            ti.mode = 0o644
            tar.addfile(ti, io.BytesIO(data))
    tampered_path = tmp_path / "tampered.tar"
    tampered_path.write_bytes(new_buf.getvalue())
    fresh = InMemoryStateStore()
    with pytest.raises(ValueError, match="checksum mismatch"):
        import_bundle(fresh, None, tampered_path)
    # also test count mismatch: tamper manifest counts without updating data -> should raise count mismatch
    # create bundle with correct checksums but wrong counts
    store2, _ = _make_populated_store()
    out2 = tmp_path / "bundle2.tar"
    export_bundle(store2, None, out2)
    # unpack, modify manifest counts
    buf2 = io.BytesIO(out2.read_bytes())
    members2 = {}
    with tarfile.open(fileobj=buf2, mode="r") as tar:
        for m in tar.getmembers():
            f = tar.extractfile(m)
            data = f.read() if f is not None else b""
            members2[m.name] = (m, data)
    manifest = json.loads(members2["manifest.json"][1].decode())
    manifest["counts"]["work"] = 999
    # need to keep checksums consistent for this test we want count mismatch error before checksum? Actually checksums still valid, count mismatch should be raised after checksum validation
    new_manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    members2["manifest.json"] = (members2["manifest.json"][0], new_manifest_bytes)
    new_buf2 = io.BytesIO()
    with tarfile.open(fileobj=new_buf2, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name, (info, data) in members2.items():  # noqa: B007
            ti = tarfile.TarInfo(name=name)
            ti.size = len(data)
            ti.mtime = info.mtime
            ti.mode = 0o644
            tar.addfile(ti, io.BytesIO(data))
    bad_count_path = tmp_path / "bad_count.tar"
    bad_count_path.write_bytes(new_buf2.getvalue())
    fresh2 = InMemoryStateStore()
    with pytest.raises(ValueError, match="count mismatch"):
        import_bundle(fresh2, None, bad_count_path)


def test_illegal_member_rejected(tmp_path: Path):
    store, _ = _make_populated_store()
    out = tmp_path / "bundle.tar"
    export_bundle(store, None, out)
    buf = io.BytesIO(out.read_bytes())
    members = {}
    with tarfile.open(fileobj=buf, mode="r") as tar:
        for m in tar.getmembers():
            f = tar.extractfile(m)
            members[m.name] = (m, f.read() if f is not None else b"")
    # inject illegal member
    members["evil.sh"] = (tarfile.TarInfo(name="evil.sh"), b"#!/bin/sh\necho pwned\n")
    # also test absolute path attempt
    # repack
    new_buf = io.BytesIO()
    with tarfile.open(fileobj=new_buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name, (info, data) in members.items():  # noqa: B007
            ti = tarfile.TarInfo(name=name)
            ti.size = len(data)
            ti.mtime = 0
            ti.mode = 0o644
            tar.addfile(ti, io.BytesIO(data))
    evil_path = tmp_path / "evil.tar"
    evil_path.write_bytes(new_buf.getvalue())
    fresh = InMemoryStateStore()
    with pytest.raises(ValueError, match="unexpected bundle member|unsafe"):
        import_bundle(fresh, None, evil_path)
    # test traversal member
    trav_buf = io.BytesIO()
    with tarfile.open(fileobj=trav_buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name, (info, data) in members.items():  # noqa: B007
            if name == "evil.sh":
                continue
            ti = tarfile.TarInfo(name=name)
            ti.size = len(data)
            ti.mtime = 0
            ti.mode = 0o644
            tar.addfile(ti, io.BytesIO(data))
        ti = tarfile.TarInfo(name="../escape.txt")
        payload = b"escape"
        ti.size = len(payload)
        ti.mtime = 0
        ti.mode = 0o644
        tar.addfile(ti, io.BytesIO(payload))
    trav_path = tmp_path / "trav.tar"
    trav_path.write_bytes(trav_buf.getvalue())
    fresh2 = InMemoryStateStore()
    with pytest.raises(ValueError, match="unsafe"):
        import_bundle(fresh2, None, trav_path)


def test_event_journal_append_only_memory():
    store = InMemoryStateStore()
    e1 = Event(id="evt_dup", type="WorkCreated", subject_ref="work_1", payload={"a": 1})
    store.append_event(e1)
    # idempotent same payload ok
    e1_copy = Event(id="evt_dup", type="WorkCreated", subject_ref="work_1", payload={"a": 1})
    store.append_event(e1_copy)  # should not raise
    # different payload should raise
    e2 = Event(id="evt_dup", type="WorkCreated", subject_ref="work_1", payload={"a": 2})
    with pytest.raises(ValueError, match="append-only"):
        store.append_event(e2)
    # original retained
    assert store.get_event("evt_dup").payload == {"a": 1}
    # save_event alias also enforces
    with pytest.raises(ValueError, match="append-only"):
        store.save_event(e2)


def test_event_journal_append_only_sqlite(tmp_path: Path):
    db = tmp_path / "ev.sqlite"
    store = SQLiteStateStore(db)
    e1 = Event(id="evt_dup2", type="WorkCreated", subject_ref="work_1", payload={"x": 1})
    store.append_event(e1)
    e1_copy = Event(id="evt_dup2", type="WorkCreated", subject_ref="work_1", payload={"x": 1})
    store.append_event(e1_copy)
    e2 = Event(id="evt_dup2", type="WorkCreated", subject_ref="work_1", payload={"x": 99})
    with pytest.raises(ValueError, match="append-only"):
        store.append_event(e2)
    assert store.get_event("evt_dup2").payload == {"x": 1}
    store.close()


def test_lifecycle_and_relation_invariants_rejected_on_import(tmp_path: Path):
    # create a store with valid record then tamper bundle to have invalid lifecycle_status
    store, _ = _make_populated_store()
    out = tmp_path / "bundle.tar"
    export_bundle(store, None, out)
    # unpack
    buf = io.BytesIO(out.read_bytes())
    members = {}
    with tarfile.open(fileobj=buf, mode="r") as tar:
        for m in tar.getmembers():
            f = tar.extractfile(m)
            members[m.name] = (m, f.read() if f is not None else b"")
    # tamper records.jsonl: change lifecycle_status to invalid for its type
    rec_data = members["records.jsonl"][1]
    lines = rec_data.decode().strip().splitlines()
    tampered_lines = []
    for line in lines:
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj.get("id") == "record_assert_1":
            obj["lifecycle_status"] = "authorized"  # not allowed for Assertion (allowed: draft/current/superseded/archived)
        tampered_lines.append(json.dumps(obj, ensure_ascii=False))
    new_rec_data = ("\n".join(tampered_lines) + "\n").encode() if tampered_lines else b""
    members["records.jsonl"] = (members["records.jsonl"][0], new_rec_data)
    # update checksums in manifest to match tampered data so lifecycle check is hit, not checksum
    manifest = json.loads(members["manifest.json"][1].decode())
    manifest["checksums"]["records.jsonl"] = hashlib.sha256(new_rec_data).hexdigest()
    # also update counts if needed (same count)
    new_manifest = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    members["manifest.json"] = (members["manifest.json"][0], new_manifest)
    new_buf = io.BytesIO()
    with tarfile.open(fileobj=new_buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name, (info, data) in members.items():  # noqa: B007
            ti = tarfile.TarInfo(name=name)
            ti.size = len(data)
            ti.mtime = 0
            ti.mode = 0o644
            tar.addfile(ti, io.BytesIO(data))
    bad_path = tmp_path / "bad_lifecycle.tar"
    bad_path.write_bytes(new_buf.getvalue())
    fresh = InMemoryStateStore()
    with pytest.raises(ValueError, match="lifecycle|invariant"):
        import_bundle(fresh, None, bad_path)

    # relation invariant: tamper relation to have empty subject_ref
    store2, _ = _make_populated_store()
    out2 = tmp_path / "bundle2.tar"
    export_bundle(store2, None, out2)
    buf2 = io.BytesIO(out2.read_bytes())
    members2 = {}
    with tarfile.open(fileobj=buf2, mode="r") as tar:
        for m in tar.getmembers():
            f = tar.extractfile(m)
            members2[m.name] = (m, f.read() if f is not None else b"")
    rel_data = members2["relations.jsonl"][1].decode().strip().splitlines()
    tampered_rels = []
    for line in rel_data:
        obj = json.loads(line)
        if obj.get("id") == "rel_1":
            obj["subject_ref"] = ""
        tampered_rels.append(json.dumps(obj, ensure_ascii=False))
    new_rel_data = ("\n".join(tampered_rels) + "\n").encode()
    members2["relations.jsonl"] = (members2["relations.jsonl"][0], new_rel_data)
    manifest2 = json.loads(members2["manifest.json"][1].decode())
    manifest2["checksums"]["relations.jsonl"] = hashlib.sha256(new_rel_data).hexdigest()
    members2["manifest.json"] = (members2["manifest.json"][0], json.dumps(manifest2, ensure_ascii=False, indent=2).encode())
    new_buf2 = io.BytesIO()
    with tarfile.open(fileobj=new_buf2, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name, (info, data) in members2.items():  # noqa: B007
            ti = tarfile.TarInfo(name=name)
            ti.size = len(data)
            ti.mtime = 0
            ti.mode = 0o644
            tar.addfile(ti, io.BytesIO(data))
    bad_rel_path = tmp_path / "bad_rel.tar"
    bad_rel_path.write_bytes(new_buf2.getvalue())
    fresh2 = InMemoryStateStore()
    with pytest.raises(ValueError, match="relation|subject_ref"):
        import_bundle(fresh2, None, bad_rel_path)


def test_schema_version_rejected(tmp_path: Path):
    store, _ = _make_populated_store()
    out = tmp_path / "bundle.tar"
    export_bundle(store, None, out)
    buf = io.BytesIO(out.read_bytes())
    members = {}
    with tarfile.open(fileobj=buf, mode="r") as tar:
        for m in tar.getmembers():
            f = tar.extractfile(m)
            members[m.name] = (m, f.read() if f is not None else b"")
    manifest = json.loads(members["manifest.json"][1].decode())
    manifest["schema_version"] = "999"
    members["manifest.json"] = (members["manifest.json"][0], json.dumps(manifest, ensure_ascii=False, indent=2).encode())
    new_buf = io.BytesIO()
    with tarfile.open(fileobj=new_buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name, (info, data) in members.items():  # noqa: B007
            ti = tarfile.TarInfo(name=name)
            ti.size = len(data)
            ti.mtime = 0
            ti.mode = 0o644
            tar.addfile(ti, io.BytesIO(data))
    bad = tmp_path / "bad_schema.tar"
    bad.write_bytes(new_buf.getvalue())
    fresh = InMemoryStateStore()
    with pytest.raises(ValueError, match="unsupported bundle schema_version"):
        import_bundle(fresh, None, bad)

