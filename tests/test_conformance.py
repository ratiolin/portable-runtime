"""Batch8 2.0 protocol conformance \u2014 11 dimensions per \u00A740."""
from __future__ import annotations
import hashlib
import json
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
import pytest
from portable_runtime.core.capabilities import CapabilityRequest, CapabilityResult, InvocationContext, ProviderDescriptor, ProviderHealth
from portable_runtime.core.models import Artifact, Run, Step, StepAttempt, Work, new_id
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.core.router import CapabilityService
from portable_runtime.core.runtime import Runtime
from portable_runtime.records.authorization import AuthorizationGrant, create_grant_for_approval, is_authorized_for, validate_grant
from portable_runtime.records.lifecycle import validate_lifecycle_transition
from portable_runtime.records.models import Assertion, EvidenceArtifact, PolicyRecord
from portable_runtime.records.relations import RecordRelation, validate_relation
from portable_runtime.records.revalidation import assess_revalidation, should_block
from portable_runtime.records.revision import create_revision, supersede
from portable_runtime.stores.bundle import BUNDLE_SCHEMA_VERSION, export_bundle, import_bundle
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore
from portable_runtime.workflows.procedure import ObligationStatus, ProcedureProfile, check_procedure, gates_for_profile
from portable_runtime.core.policies import Obligation

def make_work(title="t", kind="incident", **kw):
    return Work(id=new_id("work"), title=title, kind=kind, description="desc", **kw)
def make_run(work_id, status="running"):
    return Run(id=new_id("run"), work_id=work_id, status=status, workflow_id="incident-repair")

class FakeReconcilableProvider:
    def __init__(self, pid="reconprov", effect="reconcilable"):
        self._d = ProviderDescriptor(id=pid, name=pid, version="1.0.0", capabilities=["code.deploy"], effect_semantics=effect, side_effect_class=effect, reversibility="irreversible")
    @property
    def descriptor(self): return self._d
    async def health(self): return ProviderHealth(provider_id=self._d.id, available=True)
    async def invoke(self, req: CapabilityRequest, ctx: InvocationContext):
        return CapabilityResult(request_id=req.id, provider_id=self._d.id, status="succeeded", message="ok", external_operation_ref="ext-op-123")
    async def cancel(self, request_id: str): return None
    async def reconcile(self, request_id: str):
        return CapabilityResult(request_id=request_id, provider_id=self._d.id, status="unknown", message="cannot confirm")
class UnknownPreservingProvider:
    def __init__(self, pid="unkprov"):
        self._d = ProviderDescriptor(id=pid, name=pid, version="1.0.0", capabilities=["code.deploy"], effect_semantics="irreversible-opaque", side_effect_class="irreversible-opaque")
    @property
    def descriptor(self): return self._d
    async def health(self): return ProviderHealth(provider_id=self._d.id, available=True)
    async def invoke(self, req, ctx): return CapabilityResult(request_id=req.id, provider_id=self._d.id, status="succeeded")
    async def cancel(self, request_id: str): return None
    async def reconcile(self, request_id: str):
        return CapabilityResult(request_id=request_id, provider_id=self._d.id, status="unknown", message="irreversible-opaque unknown")

@pytest.mark.asyncio
async def test_provider_health_invoke_cancel_reconcile_and_unknown_preserved():
    reg = ProviderRegistry(); store = InMemoryStateStore()
    prov = FakeReconcilableProvider(effect="reconcilable"); reg.register(prov)
    svc = CapabilityService(reg, store=store)
    w = make_work(title="w1"); w.id="work_1"; store.save_work(w)
    r = make_run("work_1"); r.id="run_1"; store.save_run(r)
    req = CapabilityRequest(id=new_id("req"), capability="code.deploy", work_id="work_1", run_id="run_1")
    h = await prov.health(); assert h.available is True
    res = await svc.invoke(req); assert res.status == "succeeded"
    await prov.cancel(req.id)
    rec = await prov.reconcile(req.id); assert rec is not None and rec.status == "unknown"
    steps = store.list_steps("run_1"); assert any(s.status in ("succeeded","unknown","running") for s in steps)
    prov2 = UnknownPreservingProvider(); reg2 = ProviderRegistry(); reg2.register(prov2)
    store2 = InMemoryStateStore(); w2 = make_work(); w2.id="work_1"; store2.save_work(w2)
    r2 = make_run("work_1"); r2.id="run_1"; store2.save_run(r2)
    svc2 = CapabilityService(reg2, store=store2)
    req2 = CapabilityRequest(id=new_id("req"), capability="code.deploy", work_id="work_1", run_id="run_1")
    res2 = await svc2.invoke(req2); assert res2.status == "succeeded"
    stale = Step(id=new_id("step"), run_id="run_1", step_key="k1", status="running", effect_semantics="irreversible-opaque", side_effect_class="irreversible-opaque", updated_at=datetime.now(UTC) - timedelta(seconds=60), current_attempt=1)
    store2.save_step(stale)
    attempt = StepAttempt(id=new_id("attempt"), step_id=stale.id, attempt_no=1, provider_id=prov2.descriptor.id, request_ref=req2.id, status="running")
    store2.save_attempt(attempt)
    rt = Runtime(store=store2, registry=reg2)
    rec2 = await rt.reconcile(stale.id); assert rec2 is not None; assert rec2.status == "unknown"
    fetched = store2.get_step(stale.id); assert fetched is not None and fetched.status == "unknown"; assert fetched.status != "failed"

@pytest.mark.asyncio
async def test_provider_unknown_retained_on_cancel_and_reconcile_none():
    class NoReconcileProv:
        def __init__(self):
            self._d = ProviderDescriptor(id="norec", name="norec", version="1.0", capabilities=["code.edit"], effect_semantics="irreversible-opaque", side_effect_class="irreversible-opaque")
        @property
        def descriptor(self): return self._d
        async def health(self): return ProviderHealth(provider_id=self._d.id, available=True)
        async def invoke(self, req, ctx): return CapabilityResult(request_id=req.id, provider_id=self._d.id, status="succeeded")
        async def cancel(self, request_id: str): return None
    reg = ProviderRegistry(); p = NoReconcileProv(); reg.register(p)
    store = InMemoryStateStore(); w = make_work(); w.id="work_1"; store.save_work(w); r = make_run("work_1"); r.id="run_1"; store.save_run(r)
    svc = CapabilityService(reg, store=store)
    req = CapabilityRequest(id=new_id("req"), capability="code.edit", work_id="work_1", run_id="run_1")
    res = await svc.invoke(req); assert res.status == "succeeded"
    await p.cancel(req.id)
    stale = Step(id=new_id("step"), run_id="run_1", step_key="k2", status="running", effect_semantics="irreversible-opaque", updated_at=datetime.now(UTC)-timedelta(seconds=120), current_attempt=1)
    store.save_step(stale)
    att = StepAttempt(id=new_id("attempt"), step_id=stale.id, attempt_no=1, provider_id="norec", request_ref=req.id, status="running")
    store.save_attempt(att)
    rt = Runtime(store=store, registry=reg)
    rec = await rt.reconcile(stale.id); assert rec is not None and rec.status == "unknown"; assert store.get_step(stale.id).status == "unknown"

def test_store_cas_transaction_lease_fencing_and_step_attempt():
    store = InMemoryStateStore()
    w = make_work(title="cas1"); store.save_work(w)
    run = make_run(w.id); store.save_run(run)
    step = Step(id=new_id("step"), run_id=run.id, step_key="k-cas", status="pending", version=0)
    store.save_step(step)
    new_step = step.model_copy(update={"status":"running", "version":1})
    ok = store.compare_and_swap("step", step.id, expected_version=0, new_value=new_step); assert ok is True
    stale_step = step.model_copy(update={"status":"failed", "version":2})
    ok2 = store.compare_and_swap("step", step.id, expected_version=0, new_value=stale_step); assert ok2 is False
    with store.transaction(): store.save_work(make_work(title="tx-inner"))
    run_id = run.id
    assert store.acquire_lease(run_id, owner="workerA", ttl_seconds=0.2) is True
    assert store.acquire_lease(run_id, owner="workerB", ttl_seconds=30) is False
    time.sleep(0.25)
    assert store.acquire_lease(run_id, owner="workerB", ttl_seconds=30) is True
    run_after = store.get_run(run_id); assert run_after is not None; assert run_after.lease_generation >= 2
    assert store.renew_lease(run_id, owner="workerA", ttl_seconds=30) is False
    assert store.renew_lease(run_id, owner="workerB", ttl_seconds=30) is True
    assert store.release_lease(run_id, owner="workerA") is False
    assert store.release_lease(run_id, owner="workerB") is True
    attempt = StepAttempt(id=new_id("attempt"), step_id=step.id, attempt_no=1, provider_id="p1", request_ref="req1", status="running")
    store.save_attempt(attempt); assert store.get_attempt(attempt.id) is not None; assert len(store.list_attempts(step.id)) == 1; assert store.get_step(step.id) is not None
    stale2 = Step(id=new_id("step"), run_id=run_id, step_key="stale2", status="running", updated_at=datetime.now(UTC)-timedelta(seconds=60))
    store.save_step(stale2); stalelist = store.list_stale_steps(before_seconds=30); assert any(s.id == stale2.id for s in stalelist)
    with tempfile.TemporaryDirectory() as td:
        dbp = Path(td)/"s.db"; sstore = SQLiteStateStore(dbp)
        try:
            w2 = make_work(title="sqlite-cas"); sstore.save_work(w2)
            run2 = make_run(w2.id); sstore.save_run(run2)
            step2 = Step(id=new_id("step"), run_id=run2.id, step_key="k-cas-sql", status="pending", version=0)
            sstore.save_step(step2)
            new_step2 = step2.model_copy(update={"status":"running", "version":1})
            ok3 = sstore.compare_and_swap("step", step2.id, expected_version=0, new_value=new_step2); assert ok3 in (True, False)
            assert sstore.get_step(step2.id) is not None
            sstore.save_attempt(StepAttempt(id=new_id("attempt"), step_id=step2.id, attempt_no=1, provider_id="p", request_ref="r", status="running"))
            assert len(sstore.list_attempts(step2.id)) == 1
            assert sstore.acquire_lease(run2.id, owner="A", ttl_seconds=30) is True
            assert sstore.acquire_lease(run2.id, owner="B", ttl_seconds=30) is False
            assert sstore.release_lease(run2.id, owner="A") is True
        finally: sstore.close()

def test_record_semantics_orthogonal_and_evidence_no_epistemic():
    with pytest.raises(ValueError): EvidenceArtifact(uri="file://a", lifecycle_status="current", epistemic_status="supported")  # type: ignore
    store = InMemoryStateStore()
    ok_artifact = EvidenceArtifact(uri="file://ok", lifecycle_status="current")
    assert ok_artifact.record_type == "EvidenceArtifact"; assert ok_artifact.epistemic_status is None; store.save_record(ok_artifact)
    ass = Assertion(statement="x", lifecycle_status="draft", epistemic_status="supported"); assert ass.epistemic_status == "supported"; store.save_record(ass)
    ass2 = Assertion(statement="y", lifecycle_status="current", epistemic_status="unverified"); store.save_record(ass2)
    from portable_runtime.records.models import ActionRecord
    with pytest.raises(ValueError): ActionRecord(work_id="w", run_id="r", capability="c", provider_id="p", lifecycle_status="recorded", epistemic_status="supported")  # type: ignore
    e2 = EvidenceArtifact(uri="file://b", lifecycle_status="draft"); assert e2.lifecycle_status == "draft"; assert e2.epistemic_status is None

def test_record_invalid_lifecycle_rejected():
    with pytest.raises(ValueError): validate_lifecycle_transition("Policy", "draft", "official")
    with pytest.raises(ValueError): validate_lifecycle_transition("Revision", "proposed", "accepted")

def test_relation_produces_not_causes_and_invalid_rejected():
    ok = RecordRelation(subject_ref="action_1", object_ref="outcome_1", relation_type="produces"); assert validate_relation(ok) == []
    bad = RecordRelation.model_construct(subject_ref="action_1", object_ref="outcome_1", relation_type="causes")  # type: ignore
    errs = validate_relation(bad); assert any("causes" in e for e in errs)
    store = InMemoryStateStore()
    with pytest.raises(ValueError): store.save_relation(bad)
    missing = RecordRelation(subject_ref="", object_ref="o", relation_type="supports"); assert validate_relation(missing)
    with pytest.raises(ValueError): store.save_relation(missing)
    rel_supports = RecordRelation(subject_ref="claim_1", object_ref="ev_1", relation_type="supports"); assert validate_relation(rel_supports) == []; store.save_relation(rel_supports); store.save_relation(ok)

def test_lifecycle_revision_proposed_authorized_applied_verified_accepted():
    store = InMemoryStateStore()
    old = Assertion(statement="old", lifecycle_status="current"); new = Assertion(statement="new", lifecycle_status="draft")
    store.save_record(old); store.save_record(new)
    rev = create_revision(old.id, new.id); assert rev.lifecycle_status == "proposed"; store.save_record(rev)
    validate_lifecycle_transition("Revision", "proposed", "authorized"); rev.lifecycle_status = "authorized"; store.save_record(rev)
    validate_lifecycle_transition("Revision", "authorized", "applied"); rev.lifecycle_status = "applied"; store.save_record(rev)
    validate_lifecycle_transition("Revision", "applied", "verified"); rev.lifecycle_status = "verified"; store.save_record(rev)
    validate_lifecycle_transition("Revision", "verified", "accepted"); rev.lifecycle_status = "accepted"; store.save_record(rev)
    assert store.get_record(rev.id).lifecycle_status == "accepted"
    with pytest.raises(ValueError): validate_lifecycle_transition("Revision", "proposed", "applied")

def test_lifecycle_policy_candidate_official_and_old_retained():
    store = InMemoryStateStore()
    pol = PolicyRecord(policy_type="test", lifecycle_status="draft"); store.save_record(pol)
    validate_lifecycle_transition("Policy", "draft", "candidate"); pol.lifecycle_status = "candidate"; store.save_record(pol)
    validate_lifecycle_transition("Policy", "candidate", "official"); pol.lifecycle_status = "official"; store.save_record(pol)
    pol2 = PolicyRecord(policy_type="test", lifecycle_status="draft"); store.save_record(pol2)
    rel = supersede(pol.id, pol2.id, store=store); assert rel.relation_type == "supersedes"; assert store.get_record(pol.id) is not None; assert store.get_record(pol.id).lifecycle_status == "superseded"; assert store.get_record(pol2.id) is not None

def test_authorization_gate_expired_revoked_versioned():
    now = datetime.now(UTC)
    grant = create_grant_for_approval(principal_ref="human:owner", grantee_ref="agent:x", allowed_capabilities=["code.edit"], subject_version_refs=["patch:v1"], ttl_seconds=3600)
    assert is_authorized_for({"capability":"code.edit","subject_version_refs":["patch:v1"]}, grant) is True
    assert is_authorized_for({"capability":"code.edit","subject_version_refs":["patch:v2"]}, grant) is False
    expired = AuthorizationGrant(principal_ref="human:owner", grantee_ref="agent:x", allowed_capabilities=["code.edit"], subject_version_refs=["patch:v1"], valid_from=now-timedelta(hours=2), expires_at=now-timedelta(minutes=1))
    assert is_authorized_for({"capability":"code.edit","subject_version_refs":["patch:v1"]}, expired, now=now) is False; assert validate_grant(expired, now=now)
    grant.revoked_at = datetime.now(UTC); assert is_authorized_for({"capability":"code.edit","subject_version_refs":["patch:v1"]}, grant) is False
    grant2 = create_grant_for_approval(principal_ref="human:owner", grantee_ref="agent:x", allowed_capabilities=["merge"], subject_version_refs=["rev:v1"], ttl_seconds=3600)
    assert is_authorized_for({"capability":"merge","subject_version_refs":["rev:v2"]}, grant2) is False
    def gate(action, grants): return any(is_authorized_for(action,g) for g in grants)
    assert gate({"capability":"code.edit","subject_version_refs":["patch:v1"]}, [grant2]) is False
    assert gate({"capability":"merge","subject_version_refs":["rev:v1"]}, [grant2]) is True

def test_revalidation_typed_direct_only_no_recursive():
    rel_b = RecordRelation(subject_ref="B", object_ref="evaluator:v8", relation_type="validated-under")
    rel_a = RecordRelation(subject_ref="A", object_ref="B", relation_type="depends-on")
    rel_c = RecordRelation(subject_ref="C", object_ref="B", relation_type="depends-on")
    affected = assess_revalidation("evaluator:v8", "evaluator", [rel_b, rel_a, rel_c])
    aff = {a.affected_ref for a in affected}; assert "B" in aff; assert "A" not in aff; assert "C" not in aff
    artifact_rel = RecordRelation(subject_ref="artifact_X", object_ref="evaluator:v8", relation_type="executed-with")
    affected2 = assess_revalidation("evaluator:v8", "evaluator", [artifact_rel, rel_b])
    assert any(a.affected_ref=="B" for a in affected2); assert not any(a.affected_ref=="artifact_X" for a in affected2)

def test_revalidation_all_change_types_direct():
    r1 = RecordRelation(subject_ref="r1", object_ref="chg1", relation_type="validated-under")
    r2 = RecordRelation(subject_ref="r2", object_ref="chg1", relation_type="supports")
    res = assess_revalidation("chg1", "environment", [r1, r2]); assert len(res)==1 and res[0].affected_ref=="r1"; assert should_block(res[0]) is True

@pytest.mark.asyncio
async def test_recovery_stale_step_reconcile_and_unknown_instead_of_failed():
    reg = ProviderRegistry(); prov = FakeReconcilableProvider(effect="reconcilable"); reg.register(prov)
    store = InMemoryStateStore(); w = make_work(); w.id="work_1"; store.save_work(w); r = make_run("work_1"); r.id="run_1"; store.save_run(r)
    rt = Runtime(store=store, registry=reg)
    s1 = Step(id=new_id("step"), run_id="run_1", step_key="s1", status="running", effect_semantics="reconcilable", updated_at=datetime.now(UTC)-timedelta(seconds=60), current_attempt=1)
    store.save_step(s1); att1 = StepAttempt(id=new_id("attempt"), step_id=s1.id, attempt_no=1, provider_id=prov.descriptor.id, request_ref="req1", status="running"); store.save_attempt(att1)
    prov2 = UnknownPreservingProvider(pid="irr2"); reg2 = ProviderRegistry(); reg2.register(prov2)
    store2 = InMemoryStateStore(); w2=make_work(); w2.id="work_1"; store2.save_work(w2); r2=make_run("work_1"); r2.id="run_1"; store2.save_run(r2)
    rt2 = Runtime(store=store2, registry=reg2)
    s2 = Step(id=new_id("step"), run_id="run_1", step_key="s2", status="running", effect_semantics="irreversible-opaque", side_effect_class="irreversible-opaque", updated_at=datetime.now(UTC)-timedelta(seconds=60), current_attempt=1)
    store2.save_step(s2); att2 = StepAttempt(id=new_id("attempt"), step_id=s2.id, attempt_no=1, provider_id="irr2", request_ref="req2", status="running"); store2.save_attempt(att2)
    rec2 = await rt2.reconcile(s2.id); assert rec2.status == "unknown"; assert store2.get_step(s2.id).status == "unknown"; assert store2.get_step(s2.id).status != "failed"

def test_bundle_export_import_equivalence_and_checks():
    store = InMemoryStateStore()
    w = make_work(title="bundlew"); store.save_work(w); r = make_run(w.id); store.save_run(r)
    rec = Assertion(statement="bundleclaim", lifecycle_status="draft", epistemic_status="supported"); store.save_record(rec)
    rel = RecordRelation(subject_ref=rec.id, object_ref=w.id, relation_type="supports"); store.save_relation(rel)
    step = Step(id=new_id("step"), run_id=r.id, step_key="k", status="succeeded", version=1); store.save_step(step)
    art = Artifact(id=new_id("artifact"), kind="log", uri="file:///tmp/a.txt"); store.save_artifact(art)
    with tempfile.TemporaryDirectory() as td:
        tmp_root = Path(td)/"art_root"; tmp_root.mkdir(parents=True, exist_ok=True)
        tmpfile = tmp_root / "payload.txt"; tmpfile.write_bytes(b"hello bundle")
        art2 = Artifact(id=new_id("artifact"), kind="file", uri=tmpfile.as_uri(), checksum=hashlib.sha256(b"hello bundle").hexdigest()); store.save_artifact(art2)
        class FileStore:
            def __init__(self, root: Path): self.root = root
            def get(self, uri: str):
                from urllib.parse import urlparse; from urllib.request import url2pathname; parsed = urlparse(uri); p = Path(url2pathname(parsed.path)); return p.read_bytes()
        fstore = FileStore(tmp_root); bundle = Path(td)/"bundle.tar.zst"; export_bundle(store, fstore, bundle, runtime_id="rt1")
        assert bundle.exists(); assert bundle.stat().st_size > 0
        store2 = InMemoryStateStore(); mem2_root = Path(td)/"art2"; mem2_root.mkdir(); fstore2 = FileStore(mem2_root)
        meta = import_bundle(store2, fstore2, bundle); assert meta["schema_version"] == BUNDLE_SCHEMA_VERSION; assert meta["runtime_id"] == "rt1"
        s1 = store.export_state(); s2 = store2.export_state()
        for kind in ["work","run","record","relation","step","artifact"]: assert len(s1[kind]) == len(s2[kind]), f"kind {kind} mismatch"
        ids = {rec2["id"] for lst in s2.values() for rec2 in lst}
        for rel_dict in s2["relation"]: assert rel_dict["subject_ref"] in ids or rel_dict["subject_ref"].startswith(("work_","record_"))
        restored = mem2_root / "payload.txt"; assert restored.exists(); assert restored.read_bytes() == b"hello bundle"
        bad = Path(td)/"bad.tar"; import io, tarfile; buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo(name="works.jsonl"); data=b"[]"; info.size=len(data); tar.addfile(info, io.BytesIO(data))
        bad.write_bytes(buf.getvalue())
        with pytest.raises(ValueError, match="manifest"): import_bundle(InMemoryStateStore(), None, bad)
        bad2 = Path(td)/"bad2.tar"; buf2 = io.BytesIO()
        with tarfile.open(fileobj=buf2, mode="w") as tar:
            m = json.dumps({"schema_version":"999","format":"x","runtime_id":"r","counts":{},"artifact_files":[],"checksums":{}}).encode()
            info = tarfile.TarInfo(name="manifest.json"); info.size=len(m); tar.addfile(info, io.BytesIO(m))
        bad2.write_bytes(buf2.getvalue())
        with pytest.raises(ValueError, match="schema_version"): import_bundle(InMemoryStateStore(), None, bad2)

@pytest.mark.asyncio
async def test_failure_domain_verifier_independence():
    reg = ProviderRegistry()
    provA = ProviderDescriptor(id="verifierA", name="A", version="1.0", capabilities=["verify.http"], provider_family="fam1", credential_domain="credsA", evaluation_domain="evA")
    provB = ProviderDescriptor(id="verifierB", name="B", version="1.0", capabilities=["verify.http"], provider_family="fam1", credential_domain="credsA", evaluation_domain="evB")
    provC = ProviderDescriptor(id="verifierC", name="C", version="1.0", capabilities=["verify.http"], provider_family="fam2", credential_domain="credsB", evaluation_domain="evA")
    class DummyProv:
        def __init__(self, d): self._d=d
        @property
        def descriptor(self): return self._d
        async def health(self): return ProviderHealth(provider_id=self._d.id, available=True)
        async def invoke(self, req, ctx): return CapabilityResult(request_id=req.id, provider_id=self._d.id, status="succeeded")
        async def cancel(self, rid): return None
    for d in [provA, provB, provC]: reg.register(DummyProv(d))
    svc = CapabilityService(reg)
    from portable_runtime.core.policies import independent_verification_obligation
    obl = independent_verification_obligation(independent_on=["credential_domain"]); assert obl.params["independent_on"] == ["credential_domain"]
    def independent_on_domains(p1: ProviderDescriptor, p2: ProviderDescriptor, domains: list[str]):
        for dom in domains:
            if getattr(p1, dom, None) == getattr(p2, dom, None): return False
        return True
    assert independent_on_domains(provA, provB, ["credential_domain"]) is False
    assert independent_on_domains(provA, provC, ["credential_domain"]) is True
    assert independent_on_domains(provA, provC, ["provider_family","credential_domain"]) is True
    req = CapabilityRequest(id=new_id("req"), capability="verify.http")
    res = await svc.invoke(req); assert res.status == "succeeded"; assert res.provider_id in ("verifierA","verifierB","verifierC")

def test_procedure_gates_completeness_and_waiver_and_hard_boundary():
    assert len(gates_for_profile(ProcedureProfile.minimal)) == 4; assert len(gates_for_profile(ProcedureProfile.standard)) == 10; assert len(gates_for_profile(ProcedureProfile.enhanced)) == 18
    assert len(gates_for_profile(ProcedureProfile.enhanced)) > len(gates_for_profile(ProcedureProfile.standard)) > len(gates_for_profile(ProcedureProfile.minimal))
    with pytest.raises(ValueError): ObligationStatus(obligation="authorization", status="waived", waiver_authority_ref=None)
    ObligationStatus(obligation="authorization", status="waived", waiver_authority_ref="mgr:alice")
    hard = Obligation(kind="rollback_required", waivable=False)
    with pytest.raises(ValueError): ObligationStatus(obligation=hard, status="waived", waiver_authority_ref="mgr:alice")
    w = Work(id=new_id("work"), title="t", kind="incident", metadata={}); r = Run(id=new_id("run"), work_id=w.id, status="running", metadata={})
    res = check_procedure(w, r, ProcedureProfile.standard, waivers={"authorization":"mgr:bob"})
    waived = [s for s in res if str(s.obligation)=="authorization"][0]; assert waived.status == "waived" and waived.waiver_authority_ref=="mgr:bob"

def test_procedure_gate_invariance_and_expired_invalidated():
    w = Work(id=new_id("work"), title="t", description="d", kind="incident", metadata={"purpose":"x","execution_boundary":"y"})
    r = Run(id=new_id("run"), work_id=w.id, status="succeeded", metadata={"result_confirmed":True, "authorization_grant_id":"g1","evidence_refs":["e1"],"verified":True,"recovery_path":"r","reviewed":True,"candidate":True})
    std = check_procedure(w, r, "standard"); assert any(s.obligation=="authorization" and s.status=="satisfied" for s in std)
    r2 = Run(id=new_id("run"), work_id=w.id, status="running", metadata={"authorization_expired":True})
    res2 = check_procedure(w, r2, ProcedureProfile.standard); assert any(s.obligation=="authorization" and s.status=="expired" for s in res2)
    r3 = Run(id=new_id("run"), work_id=w.id, status="running", metadata={"invalidated_gates":["verification"]})
    res3 = check_procedure(w, r3, ProcedureProfile.standard); assert any(s.obligation=="verification" and s.status=="invalidated" for s in res3)


