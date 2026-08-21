from __future__ import annotations

from types import SimpleNamespace

import pytest

from portable_runtime.core.models import Decision, Run, Work
from portable_runtime.core.qualification import AssessmentContext
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore


@pytest.mark.parametrize("store_kind", ["memory", "sqlite"])
@pytest.mark.parametrize("reference_kind", ["decision", "decisionrecord"])
def test_qualification_resolves_legacy_decision_records(
    store_kind: str, reference_kind: str, tmp_path
) -> None:
    """Decision refs resolve from both public store implementations."""

    store = (
        InMemoryStateStore()
        if store_kind == "memory"
        else SQLiteStateStore(tmp_path / "runtime.db")
    )
    try:
        work = Work(id="work-decision-lookup", title="decision lookup", kind="generic-task")
        run = Run(id="run-decision-lookup", work_id=work.id, status="running")
        decision = Decision(
            id="decision-lookup",
            work_id=work.id,
            decision_type="human-approval",
            selected_option="approve",
            authorized_by=["human:owner"],
        )
        store.save_work(work)
        store.save_run(run)
        store.save_decision(decision)

        assert store.get_decision(decision.id) == decision
        request = SimpleNamespace(
            work_id=work.id,
            run_id=run.id,
            subject_version_refs=[],
            metadata={
                "decision_refs": [{"id": decision.id, "kind": reference_kind}],
                "procedure_proof_refs": [{"id": decision.id, "kind": reference_kind}],
            },
        )
        assessment = AssessmentContext.resolve(store, request)

        assert [value.id for value in assessment.proofs["decisions"]] == [decision.id]
        assert [value.id for value in assessment.procedure_proofs()["decisions"]] == [decision.id]
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()
