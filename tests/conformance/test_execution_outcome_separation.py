"""F1-B1: provider execution reports are not authoritative objective outcomes."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

from portable_runtime.core.boundary_stages import ExecutionRecordIds, commit_execution_projection
from portable_runtime.core.capabilities import CapabilityRequest, CapabilityResult
from portable_runtime.core.models import Action, Run, Step, StepAttempt, Work
from portable_runtime.records.open_validation import ClosedVerificationResult
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore
from portable_runtime.workflows.completion import CompletionAuthority


@contextmanager
def _store(backend: str, tmp_path: Path) -> Iterator[InMemoryStateStore | SQLiteStateStore]:
    if backend == "memory":
        yield InMemoryStateStore()
        return
    store = SQLiteStateStore(tmp_path / "fb1.db")
    try:
        yield store
    finally:
        store.close()


def _prepared(store: InMemoryStateStore | SQLiteStateStore) -> tuple[CapabilityRequest, ExecutionRecordIds]:
    work = Work(id="work_fb1", title="F1-B1")
    run = Run(id="run_fb1", work_id=work.id, status="running")
    step = Step(id="step_fb1", run_id=run.id, step_key="execute", status="running")
    attempt = StepAttempt(
        id="attempt_fb1",
        step_id=step.id,
        provider_id="provider-fb1",
        request_ref="request-fb1",
        status="running",
    )
    action = Action(
        id="action_fb1",
        work_id=work.id,
        run_id=run.id,
        capability="code.edit",
        provider_id="provider-fb1",
        request_ref="request-fb1",
        status="running",
    )
    store.save_work(work)
    store.save_run(run)
    store.save_step(step)
    store.save_attempt(attempt)
    store.save_action(action)
    request = CapabilityRequest(
        id="request-fb1",
        capability="code.edit",
        work_id=work.id,
        run_id=run.id,
    )
    return request, ExecutionRecordIds(step.id, attempt.id, action.id)


def _outcomes(store: InMemoryStateStore | SQLiteStateStore) -> list[dict[str, object]]:
    return store.export_state()["outcome"]


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_fb1_001_provider_succeeded_without_verification_creates_no_authoritative_outcome(
    backend: str, tmp_path: Path
) -> None:
    with _store(backend, tmp_path) as store:
        request, records = _prepared(store)
        result = CapabilityResult(
            request_id=request.id,
            provider_id="provider-fb1",
            status="succeeded",
        )

        projection = commit_execution_projection(
            store, request, result, provider_id="provider-fb1", records=records
        )

        assert projection.error is None
        assert projection.projected_status == "succeeded"
        assert store.get_step(records.step_id or "").status == "succeeded"  # type: ignore[union-attr]
        assert store.get_attempt(records.attempt_id or "").status == "succeeded"  # type: ignore[union-attr]
        assert _outcomes(store) == []
        assert projection.outcome_id is None


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_fb1_002_execution_success_with_verification_fail_has_no_successful_objective_outcome(
    backend: str, tmp_path: Path
) -> None:
    with _store(backend, tmp_path) as store:
        request, records = _prepared(store)
        result = CapabilityResult(
            request_id=request.id,
            provider_id="provider-fb1",
            status="succeeded",
            verification_result=ClosedVerificationResult(result="fail"),
        )

        projection = commit_execution_projection(
            store, request, result, provider_id="provider-fb1", records=records
        )

        assert projection.projected_status == "succeeded"
        assert store.get_attempt(records.attempt_id or "").status == "succeeded"  # type: ignore[union-attr]
        assert _outcomes(store) == []


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_fb1_003_verification_pass_does_not_make_execution_projection_an_outcome_authority(
    backend: str, tmp_path: Path
) -> None:
    with _store(backend, tmp_path) as store:
        request, records = _prepared(store)
        result = CapabilityResult(
            request_id=request.id,
            provider_id="provider-fb1",
            status="succeeded",
            verification_result=ClosedVerificationResult(result="pass"),
        )

        projection = commit_execution_projection(
            store, request, result, provider_id="provider-fb1", records=records
        )

        assert projection.projected_status == "succeeded"
        assert _outcomes(store) == []
        assert projection.outcome_id is None


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_fb1_004_provider_failed_creates_no_successful_objective_outcome(
    backend: str, tmp_path: Path
) -> None:
    with _store(backend, tmp_path) as store:
        request, records = _prepared(store)
        result = CapabilityResult(
            request_id=request.id,
            provider_id="provider-fb1",
            status="failed",
            error={"type": "provider", "message": "failed"},
        )

        projection = commit_execution_projection(
            store, request, result, provider_id="provider-fb1", records=records
        )

        assert projection.projected_status == "failed"
        assert _outcomes(store) == []


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_fb1_005_provider_unknown_creates_no_successful_objective_outcome(
    backend: str, tmp_path: Path
) -> None:
    with _store(backend, tmp_path) as store:
        request, records = _prepared(store)
        result = CapabilityResult(
            request_id=request.id,
            provider_id="provider-fb1",
            status="unknown",
        )

        projection = commit_execution_projection(
            store, request, result, provider_id="provider-fb1", records=records
        )

        assert projection.projected_status == "unknown"
        assert _outcomes(store) == []


def test_fb1_006_execution_projection_failure_rolls_back_execution_records() -> None:
    class FailingProjectionStore(InMemoryStateStore):
        fail_projection = False

        def save_action(self, value: Action) -> None:
            if self.fail_projection and value.status != "running":
                raise RuntimeError("simulated execution projection failure")
            super().save_action(value)

    store = FailingProjectionStore()
    request, records = _prepared(store)
    store.fail_projection = True
    result = CapabilityResult(
        request_id=request.id,
        provider_id="provider-fb1",
        status="succeeded",
    )

    projection = commit_execution_projection(
        store, request, result, provider_id="provider-fb1", records=records
    )

    assert isinstance(projection.error, RuntimeError)
    assert store.get_step(records.step_id or "").status == "running"  # type: ignore[union-attr]
    assert store.get_attempt(records.attempt_id or "").status == "running"  # type: ignore[union-attr]
    assert _outcomes(store) == []


def test_fb1_007_non_governed_execution_uses_same_execution_outcome_separation() -> None:
    store = InMemoryStateStore()
    request, records = _prepared(store)
    result = CapabilityResult(
        request_id=request.id,
        provider_id="provider-fb1",
        status="succeeded",
    )

    projection = commit_execution_projection(
        store, request, result, provider_id="provider-fb1", records=records
    )

    assert projection.projected_status == "succeeded"
    assert _outcomes(store) == []


def test_fb1_008_completion_authority_rejects_provider_success_without_bound_verification() -> None:
    store = InMemoryStateStore()
    work = Work(id="work_fb1_terminal", title="terminal guard")
    run = Run(id="run_fb1_terminal", work_id=work.id, status="running")
    store.save_work(work)
    store.save_run(run)

    with pytest.raises(ValueError):
        CompletionAuthority(store).authorize(work=work, run=run, verification_refs=[])

    assert store.get_work(work.id).status == "open"  # type: ignore[union-attr]
    assert store.get_run(run.id).status == "running"  # type: ignore[union-attr]
