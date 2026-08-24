"""Proof-derived product contracts that must remain fail-closed."""

from __future__ import annotations

import pytest

from portable_runtime.core.capabilities import CapabilityRequest
from portable_runtime.core.models import Run, Work
from portable_runtime.core.qualification import AssessmentContext, QualificationResolutionError
from portable_runtime.observation.raw_transition import build_raw_withdrawal_transition
from portable_runtime.records.models import Assertion
from portable_runtime.records.relations import RecordRelation
from portable_runtime.records.revalidation import assess_revalidation
from portable_runtime.stores.memory import InMemoryStateStore


def test_rsc001_raw_withdrawal_stays_runtime_native() -> None:
    before = Assertion(
        id="assert_rsc001",
        statement="qualification basis",
        lifecycle_status="current",
        epistemic_status="supported",
        version=1,
    )
    after = before.model_copy(update={"epistemic_status": "revalidation-required", "version": 2})
    artifact = build_raw_withdrawal_transition(before, after, event_ref="event_rsc001")
    payload = artifact.model_dump(mode="json")
    serialized = repr(payload)
    for forbidden in (
        "historicalTrace",
        "qualificationBefore",
        "qualificationAfter",
        "acceptedDischargeEvidenceAfter",
        "B0",
    ):
        assert forbidden not in serialized
    assert payload["before_raw_snapshot"]["epistemic_status"] == "supported"
    assert payload["after_raw_snapshot"]["epistemic_status"] == "revalidation-required"


@pytest.mark.parametrize(
    "ref_key",
    [
        "authorization_refs",
        "authorization_grant_refs",
        "evidence_refs",
        "evidence_artifact_refs",
        "verification_refs",
        "verification_result_refs",
        "relation_refs",
        "record_relation_refs",
        "checkpoint_refs",
        "decision_refs",
        "obligation_refs",
        "policy_obligation_refs",
        "procedure_proof_refs",
        "qualification_refs",
    ],
)
def test_rsc002_all_public_qualification_ref_buckets_treat_assertions_as_positive_material(
    ref_key: str,
) -> None:
    """Negative/challenge Assertions need a future explicit role, not a silent bucket exception."""

    store = InMemoryStateStore()
    assertion = Assertion(
        id=f"assert_rsc002_{ref_key}",
        statement="contested material must not authorize current use",
        lifecycle_status="current",
        epistemic_status="contested",
        version=1,
    )
    store.save_record(assertion)
    request = CapabilityRequest(
        id=f"request_rsc002_{ref_key}",
        capability="test.read",
        metadata={ref_key: [assertion.id]},
    )

    with pytest.raises(QualificationResolutionError, match="must be current and currently supported"):
        AssessmentContext.resolve(store, request)


def test_rsc006_runtime_impact_remains_direct_not_transitive() -> None:
    relations = [
        RecordRelation(
            id="rel_direct",
            relation_type="validated-under",
            subject_ref="assert_direct",
            object_ref="model_changed",
        ),
        RecordRelation(
            id="rel_indirect",
            relation_type="validated-under",
            subject_ref="assert_indirect",
            object_ref="assert_direct",
        ),
    ]
    assessments = assess_revalidation("model_changed", "model", relations)
    assert [item.affected_ref for item in assessments] == ["assert_direct"]


def test_rsc005_provider_success_cannot_write_terminal_state() -> None:
    store = InMemoryStateStore()
    work = Work(id="work_rsc005", title="terminal separation")
    run = Run(id="run_rsc005", work_id=work.id, status="running")
    store.save_work(work)
    store.save_run(run)
    with pytest.raises(ValueError, match="CompletionAuthority"):
        store.save_run(run.model_copy(update={"status": "succeeded"}))
