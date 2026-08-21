"""P1 semantic-plane conformance: canonical projections, reopen, derivation and revalidation."""

from __future__ import annotations

import pytest

from portable_runtime.core.capabilities import CapabilityRequest
from portable_runtime.core.models import Evidence, Run, Work
from portable_runtime.core.qualification import InvocationPermit
from portable_runtime.records.knowledge import KnowledgeProjection
from portable_runtime.records.models import Assertion, BaseRecord, Derivation, EvidenceArtifact
from portable_runtime.records.reopen import ReopenAssessment, create_reopen_work
from portable_runtime.records.revalidation import (
    assess_revalidation,
    detect_dependency_impacts,
    derive_revalidation_disposition,
)
from portable_runtime.records.relations import RecordRelation
from portable_runtime.core.qualification import QualificationRef, QualificationResolutionError
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore
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


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["memory", "sqlite"])
async def test_canonical_consolidation_is_non_reentrant_and_evidence_ids_are_authoritative(
    backend: str, tmp_path: object
) -> None:
    store = InMemoryStateStore() if backend == "memory" else SQLiteStateStore(tmp_path / "compat.db")  # type: ignore[operator]
    try:
        work = Work(id="work_non_reentrant", title="consolidate", kind="knowledge-consolidation")
        run = Run(id="run_non_reentrant", work_id=work.id, status="running")
        store.save_work(work)
        store.save_run(run)
        evidence = EvidenceArtifact(
            id="record_canonical_evidence",
            kind="check",
            source_refs=[work.id],
            lifecycle_status="current",
        )
        store.save_record(evidence)
        projection = KnowledgeProjection(
            id="projection_non_reentrant",
            title="candidate",
            source_work_refs=[work.id],
            current_assertion_refs=["assertion:canonical:v1"],
            evidence_summary_refs=[evidence.id],
            epistemic_judgment_refs=["judgment:canonical:v1"],
            authorization_refs=["authorization:canonical:v1"],
            validity_scope={"domain": "test"},
            environment_bindings={"runtime": "v1"},
        )
        store.save_knowledge_projection(projection)

        # Public compatibility reads expose a legacy view, but canonical
        # ingestion must use the raw namespace and therefore see no legacy
        # duplicate for this canonical projection.
        assert len(store.list_knowledge("candidate")) == 1
        assert store.list_raw_legacy_knowledge("candidate") == []
        assert store.list_raw_legacy_evidence() == []
        assert any(item.id.startswith("legacy_") for item in store.list_evidence())

        context = WorkflowContext(work=work, run=run, store=store, capabilities=None, registry=None)
        assert await KnowledgeConsolidationWorkflow().run(context, work, run) == "succeeded"
        assert [item.id for item in store.list_knowledge_projections()] == [projection.id]
        assert store.get_knowledge_projection(projection.id).lifecycle_status == "official"

        # Fixed-point property: compatibility reads followed by another
        # canonical consolidation cannot create a second semantic projection.
        projection_ids = [item.id for item in store.list_knowledge_projections()]
        assert await KnowledgeConsolidationWorkflow().run(context, work, run) == "succeeded"
        assert [item.id for item in store.list_knowledge_projections()] == projection_ids
    finally:
        if backend == "sqlite":
            store.close()  # type: ignore[attr-defined]


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


def test_derivation_cannot_acquire_epistemic_status() -> None:
    with pytest.raises(ValueError, match="must not carry epistemic_status"):
        Derivation(epistemic_status="supported")


def test_canonical_record_writes_reject_undeclared_top_level_fields() -> None:
    store = InMemoryStateStore()
    record = BaseRecord(record_type="Assertion", lifecycle_status="draft", future_field="legacy-only")  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="undeclared fields"):
        store.save_record(record)


def test_invocation_permit_binds_an_immutable_authority_sensitive_snapshot() -> None:
    request = CapabilityRequest(
        id="request_snapshot",
        capability="deploy.prod",
        instruction="apply",
        parameters={"patch": "v1"},
        constraints={"resource": "repo/app"},
        actor_ref="agent:one",
        resource_ref="repo/app",
        subject_version_refs=["patch:v1"],
        effect_class="deploy",
        idempotency_key="idem-snapshot",
    )
    permit = InvocationPermit.issue(
        request,
        provider_id="provider-a",
        qualification_digest="qualification-v1",
        lease_generation=7,
    )
    request.parameters["patch"] = "v2"
    materialized = permit.materialize_request()

    assert materialized.parameters["patch"] == "v1"
    assert permit.snapshot_payload()["authority"] == {
        "actor": "agent:one",
        "capability": "deploy.prod",
        "constraints": {"resource": "repo/app"},
        "effect_class": "deploy",
        "idempotency_key": "idem-snapshot",
        "lease_generation": 7,
        "provider": "provider-a",
        "qualification_digest": "qualification-v1",
        "request_id": "request_snapshot",
        "resource": "repo/app",
        "subject_version_refs": ["patch:v1"],
    }


def test_qualification_refs_accept_legacy_aliases_but_reject_inline_shapes() -> None:
    assert QualificationRef.parse("record:one", default_kind="evidence").ref_id == "record:one"
    assert QualificationRef.parse({"ref_id": "record:two"}).ref_id == "record:two"
    assert QualificationRef.parse({"ref": "record:three"}).ref_id == "record:three"
    assert QualificationRef.parse({"record_id": "record:four"}).ref_id == "record:four"
    with pytest.raises(QualificationResolutionError):
        QualificationRef.parse({"record_id": ""})
    with pytest.raises(QualificationResolutionError):
        QualificationRef.parse(["record:bad"])
    with pytest.raises(ValueError, match="reference id"):
        QualificationRef(id=" ")
    with pytest.raises(ValueError, match="reference kind"):
        QualificationRef(id="record:five", kind=" ")
