"""Proof-derived product contracts that must remain fail-closed."""

from __future__ import annotations

import pytest

from portable_runtime.core.models import Run, Work
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
