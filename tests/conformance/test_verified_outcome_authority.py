"""F1-B2 design freeze: bound verification may authorize a confirmed Outcome only."""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from portable_runtime.compat.legacy_records import legacy_outcome_to_record
from portable_runtime.core.models import Action, Outcome, Run, Step, StepAttempt, Work
from portable_runtime.records.models import EvidenceArtifact, OutcomeRecord
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore

_SCOPE = {"resource": "repo/app", "operation": "effect"}
_VERSIONS = ["patch:v1"]


@contextmanager
def _store(backend: str, tmp_path: Path) -> Iterator[InMemoryStateStore | SQLiteStateStore]:
    if backend == "memory":
        yield InMemoryStateStore()
        return
    store = SQLiteStateStore(tmp_path / f"fb2-{backend}.db")
    try:
        yield store
    finally:
        store.close()


def _seed_execution(store: Any, suffix: str = "a") -> tuple[Work, Run, Step, StepAttempt, Action]:
    work = Work(
        id=f"work_fb2_{suffix}",
        title="F1-B2",
        metadata={"verification_scope": dict(_SCOPE), "work_version": 1},
    )
    run = Run(id=f"run_fb2_{suffix}", work_id=work.id, status="running")
    step = Step(
        id=f"step_fb2_{suffix}",
        run_id=run.id,
        step_key="effect",
        status="succeeded",
        current_attempt=1,
    )
    attempt = StepAttempt(
        id=f"attempt_fb2_{suffix}",
        step_id=step.id,
        provider_id="provider-executor",
        request_ref=f"request_fb2_{suffix}",
        status="succeeded",
    )
    action = Action(
        id=f"action_fb2_{suffix}",
        work_id=work.id,
        run_id=run.id,
        capability="code.edit",
        provider_id="provider-executor",
        request_ref=attempt.request_ref or "",
        status="succeeded",
    )
    store.save_work(work)
    store.save_run(run)
    store.save_step(step)
    store.save_attempt(attempt)
    store.save_action(action)
    return work, run, step, attempt, action


def _proof(
    store: Any,
    *,
    work: Work,
    run: Run,
    attempt: StepAttempt,
    action: Action,
    result: str,
    suffix: str = "a",
    scope: dict[str, str] | None = None,
    versions: list[str] | None = None,
    overrides: dict[str, object] | None = None,
) -> EvidenceArtifact:
    metadata: dict[str, object] = {
        "verification_result": {"result": result},
        "proof_class": "objective-verification",
        "action_ref": action.id,
        "request_id": action.request_ref,
        "attempt_ref": attempt.id,
        "work_id": work.id,
        "run_id": run.id,
        "verification_scope": dict(scope or _SCOPE),
        "subject_version_refs": list(versions or _VERSIONS),
        "obligation_refs": ["verify.effect"],
        "verifier_provenance": {
            "provider_id": "provider-verifier",
            "verifier_id": "verifier:objective",
            "method": "closed-verification",
        },
    }
    if overrides:
        metadata.update(overrides)
    proof = EvidenceArtifact(
        id=f"evidence_fb2_{suffix}",
        kind="task-objective-proof",
        source_refs=[action.id],
        metadata=metadata,
        lifecycle_status="current",
    )
    store.save_record(proof)
    return proof


def _authority(store: Any) -> Any:
    module = importlib.import_module("portable_runtime.records.verified_outcome")
    return module.VerifiedOutcomeAuthority(store)


def _confirm(
    authority: Any,
    *,
    work: Work,
    run: Run,
    attempt: StepAttempt,
    action: Action,
    proof: EvidenceArtifact,
) -> OutcomeRecord:
    return authority.confirm(
        action_ref=action.id,
        evidence_refs=[proof.id],
        expected_work_id=work.id,
        expected_run_id=run.id,
        expected_request_id=action.request_ref,
        expected_attempt_ref=attempt.id,
        verification_scope=dict(_SCOPE),
        subject_version_refs=list(_VERSIONS),
    )


def _confirmed(store: Any) -> list[OutcomeRecord]:
    return [
        record
        for record in store.list_records("Outcome")
        if isinstance(record, OutcomeRecord) and record.lifecycle_status == "confirmed"
    ]


def test_fb2_design_legacy_outcome_adapter_is_recorded_only() -> None:
    legacy = Outcome(
        id="legacy_outcome_fb2",
        action_id="action:external",
        status="succeeded",
    )
    canonical = legacy_outcome_to_record(legacy)
    assert canonical.lifecycle_status == "recorded"
    assert canonical.metadata["status"] == "succeeded"


def test_fb2_design_confirmed_lifecycle_does_not_encode_success() -> None:
    failed_objective = OutcomeRecord(
        id="outcome_fb2_failed_objective",
        action_ref="action:external",
        lifecycle_status="confirmed",
        metadata={"objective_result": "fail"},
    )
    assert failed_objective.lifecycle_status == "confirmed"
    assert failed_objective.metadata["objective_result"] == "fail"


def test_fb2_entry_persisted_bound_proof_does_not_self_authorize(tmp_path: Path) -> None:
    with _store("memory", tmp_path) as store:
        work, run, _step, attempt, action = _seed_execution(store)
        _proof(store, work=work, run=run, attempt=attempt, action=action, result="pass")
        assert _confirmed(store) == []


def test_fb2_003_provider_attached_verification_is_not_authority_input(tmp_path: Path) -> None:
    from portable_runtime.core.boundary_stages import ExecutionRecordIds, commit_execution_projection
    from portable_runtime.core.capabilities import CapabilityRequest, CapabilityResult
    from portable_runtime.records.open_validation import ClosedVerificationResult

    with _store("memory", tmp_path) as store:
        work, run, step, attempt, action = _seed_execution(store)
        request = CapabilityRequest(
            id=action.request_ref,
            capability=action.capability,
            work_id=work.id,
            run_id=run.id,
        )
        result = CapabilityResult(
            request_id=request.id,
            provider_id=action.provider_id,
            status="succeeded",
            verification_result=ClosedVerificationResult(result="pass"),
        )
        records = ExecutionRecordIds(step.id, attempt.id, action.id)
        commit_execution_projection(store, request, result, provider_id=action.provider_id, records=records)
        assert _confirmed(store) == []


def test_fb2_010_recorded_outcome_is_not_confirmed_authority(tmp_path: Path) -> None:
    with _store("memory", tmp_path) as store:
        _work, _run, _step, _attempt, action = _seed_execution(store)
        recorded = OutcomeRecord(
            id="outcome_fb2_recorded",
            action_ref=action.id,
            lifecycle_status="recorded",
            metadata={"objective_result": "pass"},
        )
        store.save_record(recorded)
        assert _confirmed(store) == []


_XFAIL = pytest.mark.xfail(
    strict=True,
    reason="F1-B2 production authority intentionally absent at design-freeze rollback point",
)


class TestFB2ProductionCounterexamples:
    pytestmark = _XFAIL

    @pytest.mark.parametrize("backend", ["memory", "sqlite"])
    def test_fb2_001_bound_persisted_pass_proof_confirms_one_outcome(
        self,
        backend: str,
        tmp_path: Path,
    ) -> None:
        with _store(backend, tmp_path) as store:
            work, run, _step, attempt, action = _seed_execution(store)
            proof = _proof(store, work=work, run=run, attempt=attempt, action=action, result="pass")
            outcome = _confirm(
                _authority(store),
                work=work,
                run=run,
                attempt=attempt,
                action=action,
                proof=proof,
            )
            assert outcome.lifecycle_status == "confirmed"
            assert outcome.metadata["objective_result"] == "pass"
            assert outcome.action_ref == action.id
            assert outcome.evidence_refs == [proof.id]
            assert [item.id for item in _confirmed(store)] == [outcome.id]

    @pytest.mark.parametrize("backend", ["memory", "sqlite"])
    def test_fb2_002_bound_persisted_fail_proof_confirms_not_satisfied_outcome(
        self,
        backend: str,
        tmp_path: Path,
    ) -> None:
        with _store(backend, tmp_path) as store:
            work, run, _step, attempt, action = _seed_execution(store)
            proof = _proof(store, work=work, run=run, attempt=attempt, action=action, result="fail")
            outcome = _confirm(
                _authority(store),
                work=work,
                run=run,
                attempt=attempt,
                action=action,
                proof=proof,
            )
            assert outcome.lifecycle_status == "confirmed"
            assert outcome.metadata["objective_result"] == "fail"
            assert outcome.metadata["objective_result"] != "pass"

    @pytest.mark.parametrize(
        "overrides",
        [
            {"action_ref": "action_wrong"},
            {"request_id": "request_wrong"},
            {"work_id": "work_wrong"},
            {"run_id": "run_wrong"},
        ],
    )
    def test_fb2_004_wrong_identity_binding_fails_closed(
        self,
        overrides: dict[str, object],
        tmp_path: Path,
    ) -> None:
        with _store("memory", tmp_path) as store:
            work, run, _step, attempt, action = _seed_execution(store)
            proof = _proof(
                store,
                work=work,
                run=run,
                attempt=attempt,
                action=action,
                result="pass",
                overrides=overrides,
            )
            with pytest.raises(ValueError):
                _confirm(
                    _authority(store),
                    work=work,
                    run=run,
                    attempt=attempt,
                    action=action,
                    proof=proof,
                )
            assert _confirmed(store) == []

    @pytest.mark.parametrize(
        ("scope", "versions"),
        [
            ({"resource": "repo/other", "operation": "effect"}, _VERSIONS),
            (_SCOPE, ["patch:v0"]),
        ],
    )
    def test_fb2_005_wrong_scope_or_version_fails_closed(
        self,
        scope: dict[str, str],
        versions: list[str],
        tmp_path: Path,
    ) -> None:
        with _store("memory", tmp_path) as store:
            work, run, _step, attempt, action = _seed_execution(store)
            proof = _proof(
                store,
                work=work,
                run=run,
                attempt=attempt,
                action=action,
                result="pass",
                scope=scope,
                versions=versions,
            )
            with pytest.raises(ValueError):
                _confirm(
                    _authority(store),
                    work=work,
                    run=run,
                    attempt=attempt,
                    action=action,
                    proof=proof,
                )
            assert _confirmed(store) == []

    def test_fb2_006_missing_non_typed_or_unknown_proof_fails_closed(self, tmp_path: Path) -> None:
        with _store("memory", tmp_path) as store:
            work, run, _step, attempt, action = _seed_execution(store)
            authority = _authority(store)
            with pytest.raises(ValueError):
                authority.confirm(
                    action_ref=action.id,
                    evidence_refs=["missing-proof"],
                    expected_work_id=work.id,
                    expected_run_id=run.id,
                    expected_request_id=action.request_ref,
                    expected_attempt_ref=attempt.id,
                    verification_scope=dict(_SCOPE),
                    subject_version_refs=list(_VERSIONS),
                )
            assert _confirmed(store) == []

    @pytest.mark.parametrize("backend", ["memory", "sqlite"])
    def test_fb2_007_same_verification_closure_replay_is_idempotent(
        self,
        backend: str,
        tmp_path: Path,
    ) -> None:
        with _store(backend, tmp_path) as store:
            work, run, _step, attempt, action = _seed_execution(store)
            proof = _proof(store, work=work, run=run, attempt=attempt, action=action, result="pass")
            authority = _authority(store)
            first = _confirm(
                authority,
                work=work,
                run=run,
                attempt=attempt,
                action=action,
                proof=proof,
            )
            second = _confirm(
                authority,
                work=work,
                run=run,
                attempt=attempt,
                action=action,
                proof=proof,
            )
            assert second.id == first.id
            assert [item.id for item in _confirmed(store)] == [first.id]

    def test_fb2_008_proof_from_another_action_or_run_cannot_be_reused(self, tmp_path: Path) -> None:
        with _store("memory", tmp_path) as store:
            work_a, run_a, _step_a, attempt_a, action_a = _seed_execution(store, "a")
            _work_b, _run_b, _step_b, _attempt_b, action_b = _seed_execution(store, "b")
            proof = _proof(
                store,
                work=work_a,
                run=run_a,
                attempt=attempt_a,
                action=action_a,
                result="pass",
            )
            with pytest.raises(ValueError):
                _authority(store).confirm(
                    action_ref=action_b.id,
                    evidence_refs=[proof.id],
                    expected_work_id=action_b.work_id,
                    expected_run_id=action_b.run_id,
                    expected_request_id=action_b.request_ref,
                    expected_attempt_ref="attempt_fb2_b",
                    verification_scope=dict(_SCOPE),
                    subject_version_refs=list(_VERSIONS),
                )
            assert _confirmed(store) == []

    def test_fb2_009_outcome_and_authority_event_commit_is_atomic(self) -> None:
        class FailingAuthorityEventStore(InMemoryStateStore):
            def append_event(self, value: Any) -> None:
                if getattr(value, "type", "") == "OutcomeConfirmed":
                    raise RuntimeError("simulated authority-event journal failure")
                super().append_event(value)

        store = FailingAuthorityEventStore()
        work, run, _step, attempt, action = _seed_execution(store)
        proof = _proof(store, work=work, run=run, attempt=attempt, action=action, result="pass")
        with pytest.raises(RuntimeError):
            _confirm(
                _authority(store),
                work=work,
                run=run,
                attempt=attempt,
                action=action,
                proof=proof,
            )
        assert _confirmed(store) == []
        assert not any(event.type == "ObjectiveVerificationAccepted" for event in store.list_events())

    def test_fb2_011_confirmed_outcome_does_not_discharge_governance(self, tmp_path: Path) -> None:
        with _store("memory", tmp_path) as store:
            work, run, _step, attempt, action = _seed_execution(store)
            proof = _proof(store, work=work, run=run, attempt=attempt, action=action, result="pass")
            _confirm(
                _authority(store),
                work=work,
                run=run,
                attempt=attempt,
                action=action,
                proof=proof,
            )
            assert not any("governance" in event.type.lower() for event in store.list_events())

    def test_fb2_012_confirmed_outcome_does_not_authorize_terminal_completion(self, tmp_path: Path) -> None:
        with _store("memory", tmp_path) as store:
            work, run, _step, attempt, action = _seed_execution(store)
            proof = _proof(store, work=work, run=run, attempt=attempt, action=action, result="pass")
            _confirm(
                _authority(store),
                work=work,
                run=run,
                attempt=attempt,
                action=action,
                proof=proof,
            )
            assert store.get_work(work.id).status != "completed"  # type: ignore[union-attr]
            assert store.get_run(run.id).status != "succeeded"  # type: ignore[union-attr]

    def test_fb2_a01_direct_confirmed_outcome_write_is_not_an_authority_escape_hatch(
        self,
        tmp_path: Path,
    ) -> None:
        with _store("memory", tmp_path) as store:
            work, run, _step, attempt, action = _seed_execution(store)
            proof = _proof(store, work=work, run=run, attempt=attempt, action=action, result="pass")
            forged = OutcomeRecord(
                id="outcome_fb2_forged_confirmed",
                action_ref=action.id,
                evidence_refs=[proof.id],
                lifecycle_status="confirmed",
                metadata={
                    "objective_result": "pass",
                    "work_id": work.id,
                    "run_id": run.id,
                    "request_id": action.request_ref,
                    "attempt_ref": attempt.id,
                    "verification_scope": dict(_SCOPE),
                    "subject_version_refs": list(_VERSIONS),
                    "obligation_refs": ["verify.effect"],
                    "verifier_provenance": proof.metadata["verifier_provenance"],
                },
            )
            with pytest.raises(
                ValueError,
                match="VerifiedOutcomeAuthority|verified-outcome|confirmed Outcome",
            ):
                store.save_record(forged)
            assert _confirmed(store) == []
