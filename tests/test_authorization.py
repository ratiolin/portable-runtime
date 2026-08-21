"""Batch4 V1.4 Authorization + Policy Obligations + Procedure — basic tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from portable_runtime.core.models import Run, Work, new_id
from portable_runtime.core.policies import (
    Obligation,
    PolicyContext,
    PolicyDecision,
    PolicyEngine,
)
from portable_runtime.records.authorization import (
    AuthorizationGrant,
    create_grant_for_approval,
    is_authorized_for_legacy as is_authorized_for,
    validate_grant,
)
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.workflows.procedure import (
    ObligationStatus,
    ProcedureProfile,
    check_procedure,
)
from tests._strict_fixtures import seed_action_governance

# ---------- AuthorizationGrant ----------

def test_authorization_grant_basic_and_version_invariant():
    now = datetime.now(UTC)
    grant = create_grant_for_approval(
        principal_ref="human:owner",
        grantee_ref="agent:repair",
        allowed_capabilities=["code.edit"],
        subject_version_refs=["patch:v1"],
        ttl_seconds=3600,
    )
    # authorized for same version
    action_v1 = {"capability": "code.edit", "subject_version_refs": ["patch:v1"]}
    assert is_authorized_for(action_v1, grant) is True
    # patch v1 approved must NOT carry to patch v2
    action_v2 = {"capability": "code.edit", "subject_version_refs": ["patch:v2"]}
    assert is_authorized_for(action_v2, grant) is False
    # no version on action -> allowed (generic)
    action_nov = {"capability": "code.edit"}
    assert is_authorized_for(action_nov, grant) is True


def test_expired_grant_not_reusable():
    now = datetime.now(UTC)
    grant = AuthorizationGrant(
        principal_ref="human:owner",
        grantee_ref="agent:repair",
        allowed_capabilities=["code.edit"],
        subject_version_refs=["patch:v1"],
        valid_from=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
        resource_scope=[],
    )
    errors = validate_grant(grant, now=now)
    assert any("expired" in e for e in errors)
    action = {"capability": "code.edit", "subject_version_refs": ["patch:v1"]}
    assert is_authorized_for(action, grant, now=now) is False


def test_revoked_and_capability_and_scope():
    now = datetime.now(UTC)
    grant = create_grant_for_approval(
        principal_ref="human:owner",
        grantee_ref="agent:repair",
        allowed_capabilities=["code.edit", "verify.*"],
        subject_version_refs=["rev1"],
        resource_scope=["repo/myapp"],
        ttl_seconds=3600,
    )
    # wildcard capability — with typed resource matching, must provide resource within scope
    assert is_authorized_for({"capability": "verify.http", "resource": "repo/myapp/check"}, grant) is True
    assert is_authorized_for({"capability": "deploy.prod", "resource": "repo/myapp/check"}, grant) is False
    # also without resource should fail closed (I-005) — verify that
    assert is_authorized_for({"capability": "verify.http"}, grant) is False
    # scope matching
    assert is_authorized_for({"capability": "code.edit", "resource": "repo/myapp/src/foo.py"}, grant) is True
    assert is_authorized_for({"capability": "code.edit", "resource": "repo/other/file"}, grant) is False
    # revoked
    grant.revoked_at = datetime.now(UTC)
    assert is_authorized_for({"capability": "code.edit", "subject_version_refs": ["rev1"]}, grant) is False
    assert validate_grant(grant)


def test_unauthorized_action_cannot_pass_execution_gate():
    """Simulates execution gate that checks AuthorizationGrant before side effect."""
    grant = create_grant_for_approval(
        principal_ref="human:owner",
        grantee_ref="agent:allowed",
        allowed_capabilities=["code.edit"],
        subject_version_refs=["v1"],
        ttl_seconds=3600,
    )

    def execution_gate(action: dict, grants: list[AuthorizationGrant]) -> bool:
        # gate passes only if any grant authorizes
        from portable_runtime.records.authorization import is_authorized_for_any_legacy as is_authorized_for_any
        return is_authorized_for_any(action, grants)

    # correct grantee version passes
    assert execution_gate({"capability": "code.edit", "subject_version_refs": ["v1"]}, [grant]) is True
    # wrong capability blocked
    assert execution_gate({"capability": "deploy.prod", "subject_version_refs": ["v1"]}, [grant]) is False
    # empty grants blocked
    assert execution_gate({"capability": "code.edit", "subject_version_refs": ["v1"]}, []) is False
    # expired not pass
    expired = AuthorizationGrant(
        principal_ref="human:owner",
        grantee_ref="agent:allowed",
        allowed_capabilities=["code.edit"],
        subject_version_refs=["v1"],
        valid_from=datetime.now(UTC) - timedelta(hours=2),
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    assert execution_gate({"capability": "code.edit", "subject_version_refs": ["v1"]}, [expired]) is False


# ---------- PolicyEngine obligation algebra ----------

@pytest.mark.asyncio
async def test_policy_obligation_algebra_deny_over_defer_over_require():
    # deny must win over require
    class DenyPolicy:
        id = "deny"
        async def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
            return PolicyDecision(disposition="deny", status="deny", reason="hard deny", policy_refs=["deny"], obligations=[Obligation(kind="scope_limit", waivable=False)])

    class RequirePolicy:
        id = "req"
        async def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
            return PolicyDecision(disposition="require", status="require-approval", reason="needs approval", policy_refs=["req"], obligations=[Obligation(kind="approval")])

    engine = PolicyEngine(policies=[RequirePolicy(), DenyPolicy()])
    dec = await engine.evaluate(PolicyContext(payload={}))
    assert dec.disposition == "deny"
    assert dec.status == "deny"

    # defer > require
    class DeferPolicy:
        id = "defer"
        async def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
            return PolicyDecision(disposition="defer", status="require-approval", reason="defer", policy_refs=["defer"])

    engine2 = PolicyEngine(policies=[RequirePolicy(), DeferPolicy()])
    dec2 = await engine2.evaluate(PolicyContext(payload={}))
    assert dec2.disposition == "defer"

    # requirements union when no deny/defer
    class Req2Policy:
        id = "req2"
        async def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
            return PolicyDecision(disposition="require", status="require-verification", reason="need verify", policy_refs=["req2"], obligations=[Obligation(kind="human_review")])

    engine3 = PolicyEngine(policies=[RequirePolicy(), Req2Policy()])
    dec3 = await engine3.evaluate(PolicyContext(payload={}))
    assert dec3.disposition == "require"
    kinds = {o.kind for o in dec3.obligations}
    assert "approval" in kinds and "human_review" in kinds


@pytest.mark.asyncio
async def test_policy_conflict_blocked():
    class Scope2:
        id = "scope2"
        async def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
            return PolicyDecision(disposition="require", status="require-approval", reason_refs=["scope2"], policy_refs=["scope2"], obligations=[Obligation(kind="scope_limit", params={"max_targets": 2})])

    class Scope5:
        id = "scope5"
        async def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
            return PolicyDecision(disposition="require", status="require-approval", reason_refs=["scope5"], policy_refs=["scope5"], obligations=[Obligation(kind="scope_limit", params={"max_targets": 5})])

    engine = PolicyEngine(policies=[Scope2(), Scope5()])
    dec = await engine.evaluate(PolicyContext(payload={}))
    # conflict -> blocked (deny with conflict marker)
    assert dec.disposition == "deny"
    assert "policy-conflict" in (dec.reason or "") or "policy-conflict" in dec.reason_refs
    assert dec.metadata.get("blocked") is True or dec.metadata.get("conflict") is True


def test_waivable_hard_boundary():
    # waivable false cannot be waived
    ob = Obligation(kind="rollback_required", waivable=False)
    # waived without authority should fail
    with pytest.raises(ValueError):
        ObligationStatus(obligation=ob, status="waived", waiver_authority_ref=None)
    # waived with authority but waivable false should also fail
    with pytest.raises(ValueError):
        ObligationStatus(obligation=ob, status="waived", waiver_authority_ref="mgr:alice")
    # waivable true can be waived
    ob2 = Obligation(kind="approval", waivable=True)
    s = ObligationStatus(obligation=ob2, status="waived", waiver_authority_ref="mgr:alice")
    assert s.status == "waived"


# ---------- Procedure profiles ----------

def test_procedure_minimal_standard_enhanced():
    work = Work(id=new_id("work"), title="fix bug", description="repair", kind="incident", metadata={"purpose": "fix", "execution_boundary": "prod"})
    run = Run(id=new_id("run"), work_id=work.id, status="running", metadata={"result_confirmed": True})

    minimal = check_procedure(work, run, ProcedureProfile.minimal)
    assert len(minimal) == 4
    # minimal gates should be satisfied/open ; purpose and boundary satisfied in this setup
    by_gate = {str(s.obligation): s.status for s in minimal}
    assert by_gate["purpose-identified"] == "satisfied"
    assert by_gate["execution-boundary"] == "satisfied"

    standard = check_procedure(work, run, ProcedureProfile.standard)
    assert len(standard) > len(minimal)
    # standard adds authorization which is missing -> open => procedure blocked if strict
    std_map = {str(s.obligation): s for s in standard}
    assert std_map["authorization"].status in ("open", "required", "blocked")

    # with authorization present, satisfied
    work2 = Work(id=new_id("work"), title="fix bug", description="repair", kind="incident", metadata={"purpose": "fix", "execution_boundary": "x", "authorization_grant_id": "g1", "evidence_refs": ["e1"], "verified": True, "recovery_path": "rollback", "reviewed": True, "candidate": True})
    run2 = Run(id=new_id("run"), work_id=work2.id, status="succeeded", metadata={"result_confirmed": True})
    # provide typed proofs to satisfy strict gates
    from portable_runtime.records.authorization import AuthorizationGrant as _AG
    from datetime import UTC as _UTC, datetime as _DT
    _dummy_grant = _AG(principal_ref="human:owner", grantee_ref="agent:test", allowed_capabilities=["*"], subject_version_refs=[], valid_from=_DT.now(_UTC))
    from portable_runtime.records.models import BaseRecord as _BR
    _ev = _BR(record_type="EvidenceArtifact", lifecycle_status="current", data={"uri": "file://e1"})
    from portable_runtime.records.relations import RecordRelation as _RR
    _rel = _RR(relation_type="supports", subject_ref=_ev.id, object_ref=work2.id)
    from portable_runtime.records.open_validation import ClosedVerificationResult as _CVR
    _cv = _CVR(result="pass")
    from portable_runtime.core.models import Checkpoint as _CP
    _cp = _CP(run_id=run2.id, step_id=None)
    standard2 = check_procedure(work2, run2, ProcedureProfile.standard, grants=[_dummy_grant], evidence_artifacts=[_ev], relations=[_rel], verification_results=[_cv], checkpoints=[_cp], decisions=[{"id": "d1"}])
    # authorization should be satisfied now
    assert [s for s in standard2 if str(s.obligation) == "authorization"][0].status == "satisfied"

    enhanced = check_procedure(work2, run2, ProcedureProfile.enhanced)
    assert len(enhanced) > len(standard2)
    # enhanced requires independent verification etc. - missing => open
    enh_map = {str(s.obligation): s.status for s in enhanced}
    assert enh_map["independent-verification"] in ("open", "required")


def test_waived_requires_authority():
    work = Work(id=new_id("work"), title="t", kind="incident", metadata={})
    run = Run(id=new_id("run"), work_id=work.id, status="running", metadata={})
    # missing waiver authority -> should raise at ObligationStatus level, but check_procedure with waiver map should succeed
    waivers = {"authorization": "mgr:alice"}
    res = check_procedure(work, run, ProcedureProfile.standard, waivers=waivers)
    waived = [s for s in res if str(s.obligation) == "authorization"][0]
    assert waived.status == "waived"
    assert waived.waiver_authority_ref == "mgr:alice"

    # without authority, validation enforces error when manually constructing waived
    with pytest.raises(ValueError):
        ObligationStatus(obligation="authorization", status="waived")


@pytest.mark.asyncio
async def test_human_approve_generates_decision_and_grant():
    """human.approve via workflow hook creates Decision + AuthorizationGrant."""
    from portable_runtime.core.capabilities import (
        CapabilityRequest,
        CapabilityResult,
        InvocationContext,
        ProviderDescriptor,
        ProviderHealth,
    )
    from portable_runtime.core.registry import ProviderRegistry
    from portable_runtime.core.router import CapabilityService
    from portable_runtime.workflows.context import WorkflowContext
    from portable_runtime.workflows.incident_repair.workflow import IncidentRepairWorkflow

    class SucceedProvider:
        def __init__(self, pid, caps):
            self._d = ProviderDescriptor(id=pid, name=pid, version="1.0.0", capabilities=caps, priority=10)
        @property
        def descriptor(self): return self._d
        async def health(self): return ProviderHealth(provider_id=self._d.id, available=True)
        async def invoke(self, req: CapabilityRequest, ctx: InvocationContext):
            return CapabilityResult(request_id=req.id, provider_id=self._d.id, status="succeeded", message="ok")

    store = InMemoryStateStore()
    work = Work(id=new_id("work"), title="incident fix", kind="incident", metadata={"requires_approval": True, "patch_hint": "patch:v1", "approver": "human:alice"})
    store.save_work(work)
    run = Run(id=new_id("run"), work_id=work.id, status="running")
    store.save_run(run)
    seed_action_governance(work, run, store)
    registry = ProviderRegistry()
    for pid, caps in [("p_logs", ["observe.logs"]), ("p_cont", ["observe.container"]), ("p_reason", ["reason.generate"]), ("p_edit", ["code.edit"]), ("p_http", ["verify.http"]), ("p_git", ["verify.git_diff"]), ("p_human", ["human.approve"])]:
        registry.register(SucceedProvider(pid, caps))
    caps_service = CapabilityService(registry, store=store)
    ctx = WorkflowContext(work=work, run=run, store=store, capabilities=caps_service, registry=registry)
    wf = IncidentRepairWorkflow()
    result = await wf.run(ctx, work, run)
    # With all providers succeeding, approval succeeded -> workflow should succeed and have grant
    assert result == "succeeded"
    # Check store has Decision and AuthorizationGrant stashed
    # Decision saved via save_decision
    state = store.export_state()
    # also check internal authorization bucket
    auth_bucket = getattr(store, "_records", {}).get("authorization", {})
    assert len(auth_bucket) >= 1
    grant = list(auth_bucket.values())[0]
    assert "patch:v1" in grant.subject_version_refs
    # expired v2 should not authorize
    from portable_runtime.records.authorization import is_authorized_for
    assert is_authorized_for({"capability": "code.edit", "subject_version_refs": ["patch:v2"]}, grant) is False
