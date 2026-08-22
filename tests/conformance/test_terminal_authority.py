"""Adversarial terminal-completion invariants for both state-store backends."""

from __future__ import annotations

import pytest

from portable_runtime.core.models import Run, Work
from portable_runtime.records.models import EvidenceArtifact
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore
from portable_runtime.workflows.completion import CompletionAuthority


def _proof(work: Work, run: Run) -> EvidenceArtifact:
    return EvidenceArtifact(
        id="proof_terminal",
        kind="closed-verification",
        lifecycle_status="current",
        metadata={
            "verification_result": {"result": "pass"},
            "work_id": work.id,
            "run_id": run.id,
            "verification_scope": {},
            "work_version": 1,
            "acceptance_criteria": [],
        },
    )


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_terminal_status_cannot_be_written_without_completion_authority(backend: str, tmp_path) -> None:
    store = InMemoryStateStore() if backend == "memory" else SQLiteStateStore(tmp_path / "terminal.db")
    try:
        work = Work(id="work_terminal_guard", title="guard")
        store.save_work(work)
        run = Run(id="run_terminal_guard", work_id=work.id)
        store.save_run(run)
        with pytest.raises(ValueError, match="CompletionAuthority"):
            store.save_run(run.model_copy(update={"status": "succeeded"}))
        with pytest.raises(ValueError, match="CompletionAuthority"):
            store.save_work(work.model_copy(update={"status": "completed"}))
    finally:
        if backend == "sqlite":
            store.close()


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_completion_pairs_work_and_run_and_retry_is_idempotent(backend: str, tmp_path) -> None:
    store = InMemoryStateStore() if backend == "memory" else SQLiteStateStore(tmp_path / "terminal-idempotent.db")
    try:
        work = Work(id="work_terminal_pair", title="pair")
        run = Run(id="run_terminal_pair", work_id=work.id, status="running")
        store.save_work(work)
        store.save_run(run)
        proof = _proof(work, run)
        store.save_record(proof)
        first = CompletionAuthority(store).authorize(work=work, run=run, verification_refs=[proof.id])
        assert first.status == "succeeded"
        assert store.get_work(work.id).status == "completed"
        second = CompletionAuthority(store).authorize(work=work, run=run, verification_refs=[proof.id])
        assert second.id == first.id
        assert second.metadata["_completion_proof_refs"] == [proof.id]
    finally:
        if backend == "sqlite":
            store.close()


def test_completion_failure_rolls_back_paired_terminal_write() -> None:
    class FailingRunStore(InMemoryStateStore):
        def save_run(self, value: Run) -> None:
            if value.status == "succeeded":
                raise RuntimeError("simulated crash before run commit")
            super().save_run(value)

    store = FailingRunStore()
    work = Work(id="work_terminal_rollback", title="rollback")
    run = Run(id="run_terminal_rollback", work_id=work.id, status="running")
    store.save_work(work)
    store.save_run(run)
    proof = _proof(work, run)
    store.save_record(proof)
    with pytest.raises(RuntimeError, match="simulated crash"):
        CompletionAuthority(store).authorize(work=work, run=run, verification_refs=[proof.id])
    assert store.get_work(work.id).status == "open"
    assert store.get_run(run.id).status == "running"
