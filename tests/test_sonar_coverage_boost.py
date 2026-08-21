"""Boost new code coverage for Sonar — covers low-coverage modules."""

import pytest
from pathlib import Path
from portable_runtime.core.reliability import CircuitBreaker, ReliabilityControls
from portable_runtime.records.knowledge import KnowledgeProjection, consolidate
from portable_runtime.records.open_validation import open_validate, closed_verify_http
from portable_runtime.records.experiment import ExperimentPlan, create_experiment_work
from portable_runtime.records.reopen import ReopenAssessment, create_reopen_work
from portable_runtime.core.models import Work
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.records.provenance import lineage, provenance_chain, is_supported

def test_reliability_controls():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)
    assert cb.allow()
    cb.record_failure(); cb.record_failure()
    assert not cb.allow()
    import time; time.sleep(0.02)
    assert cb.allow()
    cb.record_success()
    assert cb.state == "closed"
    rc = ReliabilityControls(max_action_rate=2, side_effect_budget=1)
    assert rc.can_execute()
    rc.record_action(side_effect=True)
    assert not rc.can_execute(side_effect=True)
    assert rc.check_rate_compatibility(1,1,1,4)

def test_knowledge_projection():
    p1 = KnowledgeProjection(title="t1", counterexample_refs=["c1"])
    assert p1.lifecycle_status == "candidate"
    p2 = consolidate([p1], ["a1"], ["c2"])
    assert "c1" in p2.counterexample_refs and "c2" in p2.counterexample_refs
    from portable_runtime.records.knowledge import is_negative_knowledge
    assert is_negative_knowledge(p2)

def test_open_validation():
    r = open_validate(judgment="supports", assertion_refs=["struct1"], evidence_refs=["e1"], provider_id="test-provider", scope={"domain": "test"})
    assert r.result == "supports"
    r2 = open_validate(judgment="weakens", assertion_refs=["struct1"], evidence_refs=["e1"], provider_id="test-provider", counterevidence_refs=["counter"], scope={"domain": "test"})
    assert r2.result == "weakens"
    r3 = closed_verify_http(200, [200])
    assert r3.result == "pass"
    r4 = closed_verify_http(404, [200])
    assert r4.result == "fail"

def test_experiment_and_reopen():
    plan = ExperimentPlan(hypothesis_refs=["h1"], discriminates_between=["h1","h2"], expected_outcomes=["o1"], risk_profile={"cost":"low"})
    w = create_experiment_work(plan, title="exp")
    assert w.kind == "experiment"
    from portable_runtime.records.experiment import is_low_cost_discriminative
    assert is_low_cost_discriminative(plan)
    work = Work(title="orig", kind="incident")
    assess = ReopenAssessment(record_ref=work.id, revision_scope="other", reason="test")
    new_w = create_reopen_work(assess, work, store=InMemoryStateStore())
    assert new_w.parent_work_id == work.id

def test_provenance_helpers():
    from portable_runtime.records.relations import RecordRelation
    rel = RecordRelation(relation_type="supports", subject_ref="a", object_ref="b")
    assert rel.is_stable()
    assert lineage("a", [rel]) == [rel]
    assert provenance_chain("a", [rel], {}) == ["a", "b"]
    assert is_supported("b", [rel])
    from portable_runtime.records.reopen import should_reopen
    a = ReopenAssessment(record_ref="r1", revision_scope="execution", reason="x")
    assert should_reopen(a)

def test_provenance_more():
    from portable_runtime.records.provenance import requires_revalidation_refs
    from portable_runtime.records.relations import RecordRelation
    rel = RecordRelation(relation_type="requires-revalidation", subject_ref="s1", object_ref="change1")
    assert requires_revalidation_refs("change1", [rel]) == ["s1"]
