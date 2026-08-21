"""P1 semantic-plane conformance: canonical projections, reopen, derivation and revalidation."""

from __future__ import annotations

import pytest

from portable_runtime.core.models import Evidence, Run, Work
from portable_runtime.records.knowledge import KnowledgeProjection
from portable_runtime.records.models import Assertion, Derivation
from portable_runtime.records.reopen import ReopenAssessment, create_reopen_work
from portable_runtime.records.revalidation import (
    assess_revalidation,
    detect_dependency_impacts,
    derive_revalidation_disposition,
)
from portable_runtime.records.relations import RecordRelation
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.workflows.context import WorkflowContext
from portable_runtime.workflows.daily_scan.workflow import KnowledgeConsolidationWorkflow


def test_deep_reopen_carries_handoff_and_never_reuses_original_workflow() -> None:
    original = Work(
        id="work_original",
        title="original problem",
        kind="incident",
        acceptance_criteria=["restore service"],
        metadata={"assumptions": ["old frame"], "unknown_scopes": ["cause"]},
    )
    assessment = ReopenAssessment(
        record_ref=original.id,
        revision_scope="problem-definition",
        reason="the problem frame was wrong",
    )

    reopened = create_reopen_work(assessment, original)

    assert reopened.kind == "reframing"
    assert reopened.metadata["auto_rerun_original_work"] is False
    assert reopened.metadata["reopen_package"]["original_work_ref"] == original.id
    assert reopened.metadata["handoff_envelope"]["assumption_refs"] == ["old frame"]
    assert original.kind == "incident"


def test_dependency_impact_detection_is_separate_from_revalidation_disposition() -> None:
    relation = RecordRelation(
        subject_ref="assertion_1",
        object_ref="evaluator:v2",
        relation_type="validated-under",
    )

    impacts = detect_dependency_impacts("evaluator:v2", "evaluator", [relation])
    assert len(impacts) == 1
    assert impacts[0].impact_type == "warn"
    disposition = derive_revalidation_disposition(impacts[0], change_type="evaluator")
    assert disposition.action == "block-next-use"
    assert impacts[0].impact_type == "warn"
    assessed = assess_revalidation("evaluator:v2", "evaluator", [relation])
    assert assessed[0].dependency_impact is not None
    assert assessed[0].revalidation_disposition is not None
    assert assessed[0].revalidation_disposition.action == "block-next-use"


@pytest.mark.asyncio
async def test_knowledge_consolidation_writes_only_canonical_projection_and_journal() -> None:
    store = InMemoryStateStore()
    work = Work(id="work_projection", title="consolidate", kind="knowledge-consolidation")
    run = Run(id="run_projection", work_id=work.id, status="running")
    store.save_work(work)
    store.save_run(run)
    evidence = Evidence(id="evidence_projection", kind="check", source="test", subject_refs=[work.id])
    store.save_evidence(evidence)
    projection = KnowledgeProjection(
        id="projection_candidate",
        title="candidate",
        source_work_refs=[work.id],
        current_assertion_refs=["external:assertion:v1"],
        evidence_summary_refs=[evidence.id],
        epistemic_judgment_refs=["external:judgment:v1"],
        authorization_refs=["external:authorization:v1"],
        validity_scope={"domain": "test"},
        environment_bindings={"runtime": "v1"},
    )
    store.save_knowledge_projection(projection)
    context = WorkflowContext(work=work, run=run, store=store, capabilities=None, registry=None)

    result = await KnowledgeConsolidationWorkflow().run(context, work, run)

    assert result == "succeeded"
    assert store.get_knowledge_projection(projection.id).lifecycle_status == "official"
    assert store.export_state()["knowledge"] == []
    assert any(event.type == "KnowledgeProjected" for event in store.list_events())


def test_derivation_is_a_canonical_record_with_explicit_premises_and_conclusion() -> None:
    store = InMemoryStateStore()
    assertion = Assertion(statement="derived", lifecycle_status="draft")
    store.save_record(assertion)
    derivation = Derivation(
        premise_refs=["external:premise:v1"],
        evidence_refs=["external:evidence:v1"],
        rule_or_method_refs=["method:strict-v1"],
        conclusion_ref=assertion.id,
        lifecycle_status="current",
    )
    store.save_record(derivation)

    fetched = store.get_record(derivation.id)
    assert fetched is not None
    assert fetched.record_type == "Derivation"
    assert fetched.conclusion_ref == assertion.id
