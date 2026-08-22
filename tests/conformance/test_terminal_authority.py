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
            "acceptance_criteria": list(work.acceptance_criteria),
            "obligation_refs": CompletionAuthority.required_obligation_refs(work),
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
def test_terminal_proof_must_cover_declared_obligations(backend: str, tmp_path) -> None:
    store = InMemoryStateStore() if backend == "memory" else SQLiteStateStore(tmp_path / "terminal-obligations.db")
    try:
        work = Work(
            id="work_terminal_obligations",
            title="obligations",
            acceptance_criteria=["tests pass"],
            metadata={"verification_obligations": [{"id": "independent-tests"}]},
        )
        run = Run(id="run_terminal_obligations", work_id=work.id, status="running")
        store.save_work(work)
        store.save_run(run)
        proof = _proof(work, run)
        proof.metadata.pop("obligation_refs", None)
        store.save_record(proof)
        with pytest.raises(ValueError, match="obligations"):
            CompletionAuthority(store).authorize(work=work, run=run, verification_refs=[proof.id])
        covered = proof.model_copy(
            update={
                "id": "proof_terminal_obligations_covered",
                "metadata": {
                    **proof.metadata,
                    "obligation_refs": CompletionAuthority.required_obligation_refs(work),
                }
            }
        )
        store.save_record(covered)
        assert CompletionAuthority(store).authorize(work=work, run=run, verification_refs=[covered.id]).status == "succeeded"
    finally:
        if backend == "sqlite":
            store.close()


def test_required_obligation_refs_reads_work_policy_and_constraint_declarations() -> None:
    work = Work(
        id="work_obligation_declarations",
        title="declarations",
        acceptance_criteria=["tests pass", "  "],
        metadata={
            "verification_obligations": "delivery-proof",
            "required_obligations": ["independent-review", {"id": "scope-bound"}],
            "policy_obligations": [{"ref": "policy-proof"}],
            "obligations": [{"key": "audit-trail"}],
            "verification_policy": {
                "verification_obligations": [{"name": "objective-proof"}],
                "required_obligations": ["criteria-proof"],
                "obligations": [{"description": "evidence-proof"}],
            },
        },
        constraints={
            "verification_obligations": ["constraint-proof"],
            "verification_policy": {"obligations": ["constraint-policy-proof"]},
        },
    )
    assert CompletionAuthority.required_obligation_refs(work) == [
        "tests pass",
        "delivery-proof",
        "independent-review",
        "scope-bound",
        "policy-proof",
        "audit-trail",
        "objective-proof",
        "criteria-proof",
        "evidence-proof",
        "constraint-proof",
        "constraint-policy-proof",
    ]


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("incident", ["verify.http", "verify.git_diff"]),
        ("maintenance-scan", ["observe.container", "verify.promql"]),
    ],
)
def test_builtin_workflow_defaults_declare_all_required_proof_obligations(kind: str, expected: list[str]) -> None:
    work = Work(id=f"work_{kind}", title="builtin obligations", kind=kind)
    assert CompletionAuthority.required_obligation_refs(work) == expected


def test_explicitly_weakened_builtin_policy_without_obligations_fails_closed() -> None:
    work = Work(
        id="work_weak_policy",
        title="weak policy",
        kind="incident",
        metadata={"verification_policy": {"mode": "any-of"}},
    )
    refs = CompletionAuthority.required_obligation_refs(work)
    assert refs == ["incident:explicit-verification-obligations-required"]


@pytest.mark.parametrize("kind", ["incident", "maintenance-scan"])
def test_builtin_workflow_missing_one_proof_cannot_reach_terminal(kind: str) -> None:
    store = InMemoryStateStore()
    work = Work(id=f"work_missing_{kind}", title="missing proof", kind=kind)
    run = Run(id=f"run_missing_{kind}", work_id=work.id, status="running")
    store.save_work(work)
    store.save_run(run)
    required = CompletionAuthority.required_obligation_refs(work)
    first = EvidenceArtifact(
        id=f"proof_missing_{kind}",
        kind="closed-verification",
        lifecycle_status="current",
        metadata={
            "verification_result": {"result": "pass"},
            "work_id": work.id,
            "run_id": run.id,
            "verification_scope": {},
            "work_version": 1,
            "acceptance_criteria": [],
            "obligation_refs": [required[0]],
        },
    )
    store.save_record(first)
    with pytest.raises(ValueError, match="required verification obligations"):
        CompletionAuthority(store).authorize(work=work, run=run, verification_refs=[first.id])


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_store_terminal_primitive_requires_symmetric_pair_metadata(backend: str, tmp_path) -> None:
    store = InMemoryStateStore() if backend == "memory" else SQLiteStateStore(tmp_path / "terminal-primitive.db")
    try:
        work = Work(id="work_terminal_primitive", title="primitive")
        run = Run(id="run_terminal_primitive", work_id=work.id, status="running")
        store.save_work(work)
        store.save_run(run)
        proof = _proof(work, run)
        store.save_record(proof)
        with pytest.raises(ValueError, match="completed Work and succeeded Run"):
            store.commit_terminal(work, run, [proof.id])
        terminal_work = work.model_copy(update={"status": "completed"})
        terminal_run = run.model_copy(update={"status": "succeeded"})
        with pytest.raises(ValueError, match="symmetric proof refs"):
            store.commit_terminal(terminal_work, terminal_run, [proof.id])

        terminal_work = terminal_work.model_copy(update={"metadata": {"_completion_proof_refs": [proof.id]}})
        terminal_run = terminal_run.model_copy(update={"metadata": {"_completion_proof_refs": [proof.id]}})
        assert store.commit_terminal(terminal_work, terminal_run, [proof.id]).status == "succeeded"
    finally:
        if backend == "sqlite":
            store.close()


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_import_state_rejects_completed_work_with_tampered_pair_metadata(backend: str, tmp_path) -> None:
    store = InMemoryStateStore() if backend == "memory" else SQLiteStateStore(tmp_path / "terminal-pair-metadata.db")
    try:
        work = Work(id="work_terminal_pair_metadata", title="pair")
        run = Run(id="run_terminal_pair_metadata", work_id=work.id, status="succeeded")
        proof = _proof(work, run)
        refs = [proof.id]
        work = work.model_copy(
            update={
                "status": "completed",
                "metadata": {
                    "_completion_proof_refs": refs,
                    "completion_verification_scope": {},
                    "completion_work_version": 1,
                    "completion_acceptance_criteria": [],
                },
            }
        )
        run = run.model_copy(
            update={
                "metadata": {
                    "_completion_proof_refs": [],
                    "completion_verification_scope": {"tampered": True},
                    "completion_work_version": 1,
                    "completion_acceptance_criteria": [],
                }
            }
        )
        with pytest.raises(ValueError, match="completion metadata|terminal proof"):
            store.import_state(
                {
                    "work": [work.model_dump(mode="json")],
                    "run": [run.model_dump(mode="json")],
                    "record": [proof.model_dump(mode="json")],
                }
            )
    finally:
        if backend == "sqlite":
            store.close()


def test_terminal_proof_accepts_legacy_covered_obligations_string() -> None:
    store = InMemoryStateStore()
    work = Work(id="work_terminal_covered_string", title="covered", acceptance_criteria=["criterion"])
    run = Run(id="run_terminal_covered_string", work_id=work.id, status="running")
    store.save_work(work)
    store.save_run(run)
    proof_metadata = _proof(work, run).metadata.copy()
    proof_metadata.pop("obligation_refs", None)
    proof = _proof(work, run).model_copy(
        update={
            "metadata": {**proof_metadata, "covered_obligations": "criterion"}
        }
    )
    store.save_record(proof)
    assert CompletionAuthority(store).authorize(work=work, run=run, verification_refs=[proof.id]).status == "succeeded"


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


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_terminal_proof_cannot_be_overwritten_or_invalidated_by_semantic_write(backend: str, tmp_path) -> None:
    store = InMemoryStateStore() if backend == "memory" else SQLiteStateStore(tmp_path / "terminal-proof-integrity.db")
    try:
        work = Work(id="work_terminal_proof_integrity", title="proof integrity")
        run = Run(id="run_terminal_proof_integrity", work_id=work.id, status="running")
        store.save_work(work)
        store.save_run(run)
        proof = _proof(work, run)
        store.save_record(proof)
        CompletionAuthority(store).authorize(work=work, run=run, verification_refs=[proof.id])

        same_version = proof.model_copy(
            update={"metadata": {**proof.metadata, "verification_result": {"result": "fail"}}}
        )
        with pytest.raises(ValueError, match="version"):
            store.save_record(same_version)

        advanced_invalid = same_version.model_copy(
            update={"version": proof.version + 1}
        )
        with pytest.raises(ValueError, match="terminal|proof|state graph"):
            store.save_record(advanced_invalid)

        persisted = store.get_record(proof.id)
        assert persisted is not None
        assert persisted.metadata["verification_result"]["result"] == "pass"
        assert store.get_work(work.id).status == "completed"
        assert store.get_run(run.id).status == "succeeded"
    finally:
        if backend == "sqlite":
            store.close()


def test_completion_failure_rolls_back_paired_terminal_write() -> None:
    class FailingRunStore(InMemoryStateStore):
        def _save(self, kind: str, value: object) -> None:
            if getattr(value, "status", None) == "succeeded":
                raise RuntimeError("simulated crash before run commit")
            super()._save(kind, value)  # type: ignore[arg-type]

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


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_import_state_rejects_terminal_pair_without_scope_bound_proof(backend: str, tmp_path) -> None:
    store = InMemoryStateStore() if backend == "memory" else SQLiteStateStore(tmp_path / "terminal-import.db")
    try:
        baseline = Work(id="work_import_baseline", title="baseline")
        store.save_work(baseline)
        work = Work(id="work_import_terminal", title="terminal", acceptance_criteria=["tests pass"])
        run = Run(id="run_import_terminal", work_id=work.id, status="succeeded")
        # The result is passing but intentionally lacks the exact scope,
        # version and criteria bindings required for terminal completion.
        proof = EvidenceArtifact(
            id="proof_import_terminal",
            kind="closed-verification",
            metadata={
                "verification_result": {"result": "pass"},
                "work_id": work.id,
                "run_id": run.id,
            },
        )
        run = run.model_copy(update={"metadata": {"_completion_proof_refs": [proof.id]}})
        with pytest.raises(ValueError, match="terminal proof|scope|criteria"):
            store.import_state(
                {
                    "work": [work.model_dump(mode="json")],
                    "run": [run.model_dump(mode="json")],
                    "record": [proof.model_dump(mode="json")],
                }
            )
        assert store.get_work(baseline.id) is not None
        assert store.get_work(work.id) is None
    finally:
        if backend == "sqlite":
            store.close()
