"""P0 Strict Conformance Suite per portable-runtime-strict-enforcement-plan §14."""

import datetime
from datetime import UTC

import pytest

from portable_runtime.core.capabilities import CapabilityRequest, CapabilityResult, InvocationContext, ProviderDescriptor, ProviderHealth
from portable_runtime.core.models import Run, Work, new_id
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.core.router import CapabilityService, ConstraintRouter
from portable_runtime.records.authorization import AuthorizationGrant, create_grant_for_approval, is_authorized_for
from portable_runtime.stores.memory import InMemoryStateStore


class CountingProvider:
    def __init__(self, pid: str = "counter", effect: str = "pure"):
        self.pid = pid
        self.invoke_count = 0
        self._d = ProviderDescriptor(id=pid, name=pid, version="1.0.0", capabilities=["test.side_effect", "test.read", "test.deploy"], effect_semantics=effect, side_effect_class=effect, provider_family="famA", credential_domain="credA", evaluation_domain="evalA")
    @property
    def descriptor(self): return self._d
    async def health(self): return ProviderHealth(provider_id=self.pid, available=True)
    async def invoke(self, req: CapabilityRequest, ctx: InvocationContext):
        self.invoke_count += 1
        return CapabilityResult(request_id=req.id, provider_id=self.pid, status="succeeded")
    async def cancel(self, rid: str): return None

def make_store_work_run():
    store = InMemoryStateStore()
    work = Work(id=new_id("work"), title="t", kind="generic-task")
    store.save_work(work)
    run = Run(id=new_id("run"), work_id=work.id, status="running", workflow_id="generic-task")
    store.save_run(run)
    return store, work, run

@pytest.mark.asyncio
async def test_i001_no_valid_authorization_blocks_side_effect():
    grant = create_grant_for_approval(principal_ref="human:owner", grantee_ref="agent:other", allowed_capabilities=["test.side_effect"], subject_version_refs=[], resource_scope=[], ttl_seconds=3600)
    assert is_authorized_for({"capability": "test.side_effect", "actor_ref": "agent:legit", "resource": "repo/app"}, grant) is False
    assert is_authorized_for({"capability": "test.side_effect", "actor_ref": "agent:other", "resource": "repo/app"}, grant) is True

@pytest.mark.asyncio
async def test_i005_scoped_grant_missing_resource_blocks():
    grant = create_grant_for_approval(principal_ref="human:owner", grantee_ref="agent:x", allowed_capabilities=["test.read"], subject_version_refs=[], resource_scope=["repo/myapp"], ttl_seconds=3600)
    # missing resource with scoped grant -> fail-closed
    assert is_authorized_for({"capability": "test.read", "actor_ref": "agent:x"}, grant) is False
    assert is_authorized_for({"capability": "test.read", "actor_ref": "agent:x", "resource": "repo/myapp/file.py"}, grant) is True

@pytest.mark.asyncio
async def test_i007_stale_fencing_generation_blocks():
    store, work, run = make_store_work_run()
    store.acquire_lease(run.id, owner="workerA", ttl_seconds=30)
    run_after = store.get_run(run.id)
    gen = run_after.lease_generation
    store.release_lease(run.id, owner="workerA")
    store.acquire_lease(run.id, owner="workerB", ttl_seconds=30)
    run2 = store.get_run(run.id)
    assert run2.lease_generation != gen
    from portable_runtime.core.boundary import validate_fencing
    stale_req = CapabilityRequest(id=new_id("req"), capability="test.read", work_id=work.id, run_id=run.id, lease_generation=gen, lease_owner="workerA")
    ok, reason = validate_fencing(stale_req, run2)
    assert ok is False
    assert "generation" in reason or "fencing" in reason

@pytest.mark.asyncio
async def test_i003_version_binding_blocks():
    grant = create_grant_for_approval(principal_ref="human:owner", grantee_ref="agent:x", allowed_capabilities=["test.read"], subject_version_refs=["v1"], ttl_seconds=3600)
    assert is_authorized_for({"capability": "test.read", "subject_version_refs": ["v1"]}, grant) is True
    assert is_authorized_for({"capability": "test.read", "subject_version_refs": ["v2"]}, grant) is False

@pytest.mark.asyncio
async def test_i006_effect_ceiling_blocks():
    grant = AuthorizationGrant(principal_ref="human:owner", grantee_ref="agent:x", allowed_capabilities=["test.read", "test.deploy"], effect_ceiling="write-remote", valid_from=datetime.datetime.now(UTC))
    assert is_authorized_for({"capability": "test.deploy", "effect_class": "deploy", "actor_ref": "agent:x"}, grant) is False
    assert is_authorized_for({"capability": "test.read", "effect_class": "read", "actor_ref": "agent:x"}, grant) is True

def test_epistemic_no_auto_inference():
    from portable_runtime.records.open_validation import open_validate
    with pytest.raises((TypeError, ValueError)):
        open_validate("struct1", ["e1"], [])  # type: ignore
    r = open_validate(judgment="supports", assertion_refs=["a1"], evidence_refs=["e1"], provider_id="p1", scope={"domain": "test"})
    assert r.judgment == "supports"
    from portable_runtime.core.knowledge import promote
    from portable_runtime.core.models import KnowledgeItem as KI
    ki = KI(id="k1", kind="doc", title="t", content_ref="ref", status="candidate", evidence_refs=["e1"])
    with pytest.raises(ValueError):
        promote(ki)

def test_procedure_hint_is_not_proof():
    from portable_runtime.workflows.procedure import check_procedure, ProcedureProfile
    w = Work(id=new_id("work"), title="t", description="d", kind="incident", metadata={"authorized": True, "verified": True})
    r = Run(id=new_id("run"), work_id=w.id, status="running", metadata={"result_confirmed": True})
    std = check_procedure(w, r, ProcedureProfile.standard)
    auth = [s for s in std if str(s.obligation) == "authorization"][0]
    assert auth.status in ("open", "blocked", "required")
    ver = [s for s in std if str(s.obligation) == "verification"][0]
    assert ver.status in ("open", "blocked", "required")
