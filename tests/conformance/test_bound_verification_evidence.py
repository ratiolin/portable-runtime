from __future__ import annotations

import pytest

from portable_runtime.core.models import Action, Run, Step, StepAttempt, Work
from portable_runtime.records.models import EvidenceArtifact
from portable_runtime.records.verification_binding import BoundVerificationEvidenceValidator

_SCOPE = {"resource": "repo/app", "operation": "effect"}
_VERSIONS = ["patch:v1"]


def _graph() -> tuple[Work, Run, Step, StepAttempt, Action]:
    work = Work(id="work_binding", title="binding")
    run = Run(id="run_binding", work_id=work.id, status="running")
    step = Step(id="step_binding", run_id=run.id, step_key="effect", status="succeeded")
    attempt = StepAttempt(
        id="attempt_binding",
        step_id=step.id,
        provider_id="executor",
        request_ref="request_binding",
        status="succeeded",
    )
    action = Action(
        id="action_binding",
        work_id=work.id,
        run_id=run.id,
        capability="code.edit",
        provider_id="executor",
        request_ref="request_binding",
        status="succeeded",
    )
    return work, run, step, attempt, action


def _proof(action: Action, work: Work, run: Run, attempt: StepAttempt, result: str, suffix: str) -> EvidenceArtifact:
    return EvidenceArtifact(
        id=f"proof_binding_{suffix}",
        kind="task-objective-proof",
        source_refs=[action.id],
        metadata={
            "verification_result": {"result": result},
            "proof_class": "objective-verification",
            "action_ref": action.id,
            "request_id": action.request_ref,
            "attempt_ref": attempt.id,
            "work_id": work.id,
            "run_id": run.id,
            "verification_scope": dict(_SCOPE),
            "subject_version_refs": list(_VERSIONS),
            "verifier_provenance": {
                "provider_id": "verifier",
                "method": "closed-verification",
            },
        },
    )


def _validate(proofs: list[EvidenceArtifact], *, mutate_action: Action | None = None):
    work, run, step, attempt, action = _graph()
    action = mutate_action or action
    by_id = {proof.id: proof for proof in proofs}
    return BoundVerificationEvidenceValidator.validate(
        work=work,
        run=run,
        refs=[proof.id for proof in proofs],
        record_lookup=by_id.get,
        expected_scope=dict(_SCOPE),
        expected_subject_version_refs=list(_VERSIONS),
        action=action,
        step=step,
        attempt=attempt,
        expected_request_id="request_binding",
        expected_attempt_ref=attempt.id,
        require_execution_binding=True,
        require_verifier_provenance=True,
    )


@pytest.mark.parametrize("result", ["pass", "fail"])
def test_fb2_p3_validator_accepts_explicit_bound_objective_result(result: str) -> None:
    work, run, _step, attempt, action = _graph()
    proof = _proof(action, work, run, attempt, result, result)
    validated = _validate([proof])
    assert validated.objective_result == result
    assert validated.records == (proof,)


def test_fb2_p3_validator_rejects_execution_graph_mismatch() -> None:
    work, run, _step, attempt, action = _graph()
    proof = _proof(action, work, run, attempt, "pass", "graph")
    wrong_action = action.model_copy(update={"provider_id": "other-executor"})
    with pytest.raises(ValueError, match="provider identity"):
        _validate([proof], mutate_action=wrong_action)


def test_fb2_p3_validator_rejects_proof_bound_to_wrong_action() -> None:
    work, run, _step, attempt, action = _graph()
    proof = _proof(action, work, run, attempt, "pass", "wrong-action")
    proof = proof.model_copy(update={"metadata": {**proof.metadata, "action_ref": "action_other"}})
    with pytest.raises(ValueError, match="exact Action"):
        _validate([proof])


def test_fb2_p3_validator_rejects_scope_or_version_mismatch() -> None:
    work, run, _step, attempt, action = _graph()
    proof = _proof(action, work, run, attempt, "pass", "scope")
    proof = proof.model_copy(
        update={
            "metadata": {
                **proof.metadata,
                "subject_version_refs": ["patch:v0"],
            }
        }
    )
    with pytest.raises(ValueError, match="subject version"):
        _validate([proof])


def test_fb2_p3_validator_rejects_missing_verifier_provenance() -> None:
    work, run, _step, attempt, action = _graph()
    proof = _proof(action, work, run, attempt, "pass", "provenance")
    metadata = dict(proof.metadata)
    metadata.pop("verifier_provenance")
    proof = proof.model_copy(update={"metadata": metadata})
    with pytest.raises(ValueError, match="verifier provenance"):
        _validate([proof])


def test_fb2_p3_validator_has_no_implicit_pass_fail_aggregation_policy() -> None:
    work, run, _step, attempt, action = _graph()
    passed = _proof(action, work, run, attempt, "pass", "pass")
    failed = _proof(action, work, run, attempt, "fail", "fail")
    with pytest.raises(ValueError, match="inconsistent verification closure"):
        _validate([passed, failed])
