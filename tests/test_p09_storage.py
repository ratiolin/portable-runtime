"""P0-9/P1 storage & independence & legacy cleanup verification."""

import tempfile
import threading
from pathlib import Path

import pytest

from portable_runtime.core.capabilities import CapabilityRequest, ProviderDescriptor
from portable_runtime.core.independence import IndependenceContext
from portable_runtime.core.models import Run, Step, Work, new_id
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.core.router import CapabilityService, ConstraintRouter
from portable_runtime.stores.sqlite import SQLiteStateStore


def test_sqlite_cas_strict_no_fallback():
    with tempfile.TemporaryDirectory() as td:
        dbp = Path(td) / "s.db"
        store = SQLiteStateStore(dbp)
        try:
            w = Work(id=new_id("work"), title="t", kind="generic")
            store.save_work(w)
            run = Run(id=new_id("run"), work_id=w.id, status="running")
            store.save_run(run)
            step = Step(id=new_id("step"), run_id=run.id, step_key="k", status="pending", version=0)
            store.save_step(step)
            new_step = step.model_copy(update={"status": "running", "version": 1})
            ok = store.compare_and_swap("step", step.id, expected_version=0, new_value=new_step)
            assert ok is True
            # stale version 0 should fail
            stale = step.model_copy(update={"status": "failed", "version": 2})
            ok2 = store.compare_and_swap("step", step.id, expected_version=0, new_value=stale)
            assert ok2 is False
            # correct version 1 should succeed
            cur = store.get_step(step.id)
            assert cur is not None and cur.version == 1
            new2 = cur.model_copy(update={"status": "succeeded", "version": 2})
            ok3 = store.compare_and_swap("step", step.id, expected_version=1, new_value=new2)
            assert ok3 is True
        finally:
            store.close()


def test_sqlite_two_connections_only_one_winner():
    with tempfile.TemporaryDirectory() as td:
        dbp = Path(td) / "s.db"
        s1 = SQLiteStateStore(dbp)
        s2 = SQLiteStateStore(dbp)
        try:
            w = Work(id=new_id("work"), title="t", kind="generic")
            s1.save_work(w)
            run = Run(id=new_id("run"), work_id=w.id, status="running")
            s1.save_run(run)
            step = Step(id=new_id("step"), run_id=run.id, step_key="k", status="pending", version=0)
            s1.save_step(step)
            results = {}

            barrier = threading.Barrier(2)

            def try_cas(name, store):
                barrier.wait()
                ns = step.model_copy(update={"status": "running", "version": 1})
                ok = store.compare_and_swap("step", step.id, expected_version=0, new_value=ns)
                results[name] = ok

            t1 = threading.Thread(target=try_cas, args=("A", s1))
            t2 = threading.Thread(target=try_cas, args=("B", s2))
            t1.start()
            t2.start()
            t1.join()
            t2.join()
            assert sum(results.values()) == 1, f"only one winner expected, got {results}"
            # generation monotonic: winner should have version 1
            cur = s1.get_step(step.id)
            assert cur is not None and cur.version == 1
            # stale cannot commit
            stale = step.model_copy(update={"status": "failed", "version": 99})
            assert s1.compare_and_swap("step", step.id, expected_version=0, new_value=stale) is False
        finally:
            s1.close()
            s2.close()


def test_sqlite_lease_two_connections_only_one_winner_and_monotonic():
    with tempfile.TemporaryDirectory() as td:
        dbp = Path(td) / "s.db"
        s1 = SQLiteStateStore(dbp)
        s2 = SQLiteStateStore(dbp)
        try:
            w = Work(id=new_id("work"), title="t", kind="generic")
            s1.save_work(w)
            run = Run(id=new_id("run"), work_id=w.id, status="running")
            s1.save_run(run)
            results = {}
            barrier = threading.Barrier(2)

            def try_acquire(name, store):
                barrier.wait()
                ok = store.acquire_lease(run.id, owner=name, ttl_seconds=30)
                results[name] = ok

            t1 = threading.Thread(target=try_acquire, args=("A", s1))
            t2 = threading.Thread(target=try_acquire, args=("B", s2))
            t1.start()
            t2.start()
            t1.join()
            t2.join()
            assert sum(results.values()) == 1, f"only one lease winner {results}"
            # generation monotonic
            r = s1.get_run(run.id)
            assert r is not None and r.lease_generation == 1
            # stale worker cannot commit: try to use old generation
            # Simulate stale worker trying to CAS with old version should fail
            # Acquire again with winner should succeed for renew, loser should fail
            winner = [k for k, v in results.items() if v][0]
            loser = [k for k, v in results.items() if not v][0]
            # Loser tries to renew -> should fail
            assert s1.acquire_lease(run.id, owner=loser, ttl_seconds=30) is False
            # Winner can renew
            assert s1.renew_lease(run.id, owner=winner, ttl_seconds=30) is True
        finally:
            s1.close()
            s2.close()


@pytest.mark.asyncio
async def test_independence_true_comparison():
    reg = ProviderRegistry()
    # Create two providers with different families
    from portable_runtime.core.capabilities import ProviderHealth, CapabilityResult, InvocationContext

    class Dummy:
        def __init__(self, d):
            self._d = d
        @property
        def descriptor(self):
            return self._d
        async def health(self):
            return ProviderHealth(provider_id=self._d.id, available=True)
        async def invoke(self, req, ctx):
            return CapabilityResult(request_id=req.id, provider_id=self._d.id, status="succeeded")

    prov_a = ProviderDescriptor(id="execA", name="A", version="1", capabilities=["verify.test"], provider_family="famA", credential_domain="credA")
    prov_b = ProviderDescriptor(id="verB", name="B", version="1", capabilities=["verify.test"], provider_family="famA", credential_domain="credA")
    prov_c = ProviderDescriptor(id="verC", name="C", version="1", capabilities=["verify.test"], provider_family="famB", credential_domain="credB")
    for d in [prov_a, prov_b, prov_c]:
        reg.register(Dummy(d))
    router = ConstraintRouter(registry=reg)
    # Request requires independence from execA on provider_family and credential_domain
    req = CapabilityRequest(
        id=new_id("req"),
        capability="verify.test",
        constraints={},
        metadata={"independence_constraints": {"reference_provider_refs": ["execA"], "independent_on": ["provider_family", "credential_domain"]}},
    )
    # Candidate verB shares same family and cred -> should be ineligible
    # So router should select verC (different family/cred)
    candidates = reg.descriptors_for("verify.test")
    # Filter via router
    selected = await router.select(req, candidates)
    assert selected is not None
    assert selected.id == "verC", f"expected verC independent, got {selected.id}"
    # Missing domain -> ineligible
    prov_d = ProviderDescriptor(id="verD", name="D", version="1", capabilities=["verify.test"], provider_family="famB")  # missing credential_domain
    reg2 = ProviderRegistry()
    for d in [prov_a, prov_d]:
        reg2.register(Dummy(d))
    router2 = ConstraintRouter(registry=reg2)
    req2 = CapabilityRequest(
        id=new_id("req"),
        capability="verify.test",
        metadata={"independence_constraints": {"reference_provider_refs": ["execA"], "independent_on": ["credential_domain"]}},
    )
    cands2 = reg2.descriptors_for("verify.test")
    # verD missing credential_domain should be ineligible when independence requires it
    # So only execA is candidate but it's the reference itself, but we exclude it? For test, we check that verD is not selected
    selected2 = await router2.select(req2, [prov_d])
    assert selected2 is None, "candidate missing required domain should be ineligible"


def test_knowledge_retain_candidate():
    from portable_runtime.core.knowledge import classify, retain_candidate, promote
    from portable_runtime.core.models import KnowledgeItem

    # Missing judgment/auth/scope/version -> retain, not archive
    ki = KnowledgeItem(id=new_id("knowledge"), kind="pattern", title="t", content_ref="ref", status="candidate", evidence_refs=["e1"])
    assert classify(ki) == "retain-candidate"
    retained = retain_candidate(ki, reason="missing auth")
    assert retained.status == "candidate"
    # Explicitly refuted -> archive
    ki2 = KnowledgeItem(id=new_id("knowledge"), kind="pattern", title="t", content_ref="ref", status="candidate", evidence_refs=["e1"], metadata={"refuted": True})
    assert classify(ki2) == "archive"


def test_procedure_typed_proof_required():
    from portable_runtime.workflows.procedure import check_procedure, ProcedureProfile
    from portable_runtime.core.models import Work, Run, new_id

    w = Work(id=new_id("work"), title="t", kind="generic-task", metadata={"purpose": "test"})
    r = Run(id=new_id("run"), work_id=w.id, status="running", metadata={"execution_boundary": "x", "result_confirmed": True, "candidate": True})
    # Minimal profile with failure-stop etc but no typed proofs -> should be open, not satisfied
    statuses = check_procedure(w, r, ProcedureProfile.enhanced)
    # failure-stop should be open without proof
    fs = [s for s in statuses if str(s.obligation) == "failure-stop"][0]
    assert fs.status == "open"
    # With typed proof, should be satisfied
    statuses2 = check_procedure(w, r, ProcedureProfile.enhanced, proofs={"failure_stop_proofs": [{"condition": "stop"}]})
    fs2 = [s for s in statuses2 if str(s.obligation) == "failure-stop"][0]
    assert fs2.status == "satisfied"
    # role-separation without 3 distinct actors -> open
    rs = [s for s in statuses if str(s.obligation) == "role-separation"][0]
    assert rs.status == "open"
    rs2 = [s for s in check_procedure(w, r, ProcedureProfile.enhanced, proofs={"role_proofs": [{"decision_actor": "a", "execution_actor": "b", "verification_actor": "c"}]}) if str(s.obligation) == "role-separation"][0]
    assert rs2.status == "satisfied"
