"""B4-P3 design audit: freeze RecoveryDisposition responsibility before production."""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json

import pytest

from portable_runtime.core.models import Step, StepAttempt
from portable_runtime.governance.dispatch import dispatch_recovery_mode
from portable_runtime.records.verified_outcome_commit import prepare_verified_outcome_commit
from portable_runtime.workflows.recovery_observation import RecoveryObservation


def _xfail(reason: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(strict=True, reason=reason)


def _basis_identity(
    *,
    dispatch_commit_ref: str,
    observation_refs: tuple[str, ...],
    outcome_refs: tuple[str, ...] = (),
    recovery_classification: str,
    policy_ref: str,
) -> str:
    payload = {
        "dispatch_commit_ref": dispatch_commit_ref,
        "observation_refs": sorted(observation_refs),
        "outcome_refs": sorted(outcome_refs),
        "recovery_classification": recovery_classification,
        "policy_ref": policy_ref,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"recovery_disposition_{hashlib.sha256(raw.encode()).hexdigest()}"


def test_p3_audit_dispatch_recovery_mode_is_classification_not_disposition() -> None:
    attempt = StepAttempt(
        id="attempt:p3:classification",
        step_id="step:p3:classification",
        attempt_no=1,
        provider_id="provider:p3",
        request_ref="request:p3",
        metadata={"dispatch_commit_ref": "dispatch:p3"},
    )
    assert dispatch_recovery_mode(
        Step(
            id=attempt.step_id,
            run_id="run:p3",
            step_key="effect",
            effect_semantics="idempotent",
        ),
        attempt,
    ) == "idempotent-retry"
    assert dispatch_recovery_mode(
        Step(
            id=attempt.step_id,
            run_id="run:p3",
            step_key="effect",
            effect_semantics="reconcilable",
        ),
        attempt,
    ) == "reconcile"
    assert dispatch_recovery_mode(
        Step(
            id=attempt.step_id,
            run_id="run:p3",
            step_key="effect",
            effect_semantics="irreversible-opaque",
        ),
        attempt,
    ) == "unknown"

    source = inspect.getsource(importlib.import_module("portable_runtime.governance.dispatch"))
    assert "RecoveryDisposition" not in source


def test_p3_audit_recovery_observation_carries_no_decision_or_application_authority() -> None:
    fields = set(RecoveryObservation.__dataclass_fields__)
    assert "reported_status" in fields
    assert "dispatch_commit_ref" in fields
    assert "action_ref" in fields
    assert "disposition" not in fields
    assert "policy_ref" not in fields
    assert "application_ref" not in fields
    assert "terminal_authorized" not in fields
    assert "provider_authorized" not in fields


def test_p3_audit_recovery_observation_module_does_not_construct_follow_on_authority() -> None:
    source = inspect.getsource(
        importlib.import_module("portable_runtime.workflows.recovery_observation")
    )
    assert "RecoveryDisposition" not in source
    assert "RecoveryApplication" not in source
    assert "VerifiedOutcomeAuthority" not in source
    assert "CompletionAuthority" not in source
    assert "provider.invoke" not in source
    assert "provider.reconcile" not in source


def test_p3_audit_verified_outcome_authority_does_not_become_recovery_policy() -> None:
    source = inspect.getsource(prepare_verified_outcome_commit)
    assert "RecoveryDisposition" not in source
    assert "dispatch_recovery_mode" not in source
    assert "retry-idempotent" not in source
    assert "reconcile-again" not in source


def test_p3_audit_governance_q_is_not_an_implicit_recovery_decision_input() -> None:
    recovery_source = inspect.getsource(
        importlib.import_module("portable_runtime.workflows.recovery_observation")
    )
    dispatch_source = inspect.getsource(importlib.import_module("portable_runtime.governance.dispatch"))
    for source in (recovery_source, dispatch_source):
        assert "ReviewObligation" not in source
        assert "GovernanceDecision" not in source
        assert "GovernedApplication" not in source


def test_p3_audit_candidate_identity_is_exact_basis_not_latest_state() -> None:
    first = _basis_identity(
        dispatch_commit_ref="dispatch:p3",
        observation_refs=("obs:1", "obs:2"),
        outcome_refs=("outcome:1",),
        recovery_classification="reconcile",
        policy_ref="policy:p3:v1",
    )
    same_reordered = _basis_identity(
        dispatch_commit_ref="dispatch:p3",
        observation_refs=("obs:2", "obs:1"),
        outcome_refs=("outcome:1",),
        recovery_classification="reconcile",
        policy_ref="policy:p3:v1",
    )
    new_observation = _basis_identity(
        dispatch_commit_ref="dispatch:p3",
        observation_refs=("obs:1", "obs:2", "obs:3"),
        outcome_refs=("outcome:1",),
        recovery_classification="reconcile",
        policy_ref="policy:p3:v1",
    )
    new_outcome = _basis_identity(
        dispatch_commit_ref="dispatch:p3",
        observation_refs=("obs:1", "obs:2"),
        outcome_refs=("outcome:2",),
        recovery_classification="reconcile",
        policy_ref="policy:p3:v1",
    )

    assert first == same_reordered
    assert new_observation != first
    assert new_outcome != first


@_xfail("B4-P3 production: exact-basis RecoveryDisposition replay is not implemented")
def test_p3_future_same_exact_basis_replays_same_durable_disposition() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_disposition")
    first = module.decide_recovery(
        dispatch_commit_ref="dispatch:p3",
        observation_refs=("obs:1", "obs:2"),
        outcome_refs=("outcome:1",),
        recovery_classification="reconcile",
        policy_ref="policy:p3:v1",
    )
    replay = module.decide_recovery(
        dispatch_commit_ref="dispatch:p3",
        observation_refs=("obs:2", "obs:1"),
        outcome_refs=("outcome:1",),
        recovery_classification="reconcile",
        policy_ref="policy:p3:v1",
    )
    assert replay.id == first.id


@_xfail("B4-P3 production: new observation basis must create a new decision instance")
def test_p3_future_new_observation_basis_is_not_latest_wins_supersession() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_disposition")
    first = module.decide_recovery(
        dispatch_commit_ref="dispatch:p3",
        observation_refs=("obs:1",),
        recovery_classification="reconcile",
        policy_ref="policy:p3:v1",
    )
    second = module.decide_recovery(
        dispatch_commit_ref="dispatch:p3",
        observation_refs=("obs:1", "obs:2"),
        recovery_classification="reconcile",
        policy_ref="policy:p3:v1",
    )
    assert second.id != first.id
    assert not first.superseded
    assert not second.supersedes_ref


@_xfail("B4-P3 production: durable same-basis replay must not drift with current policy")
def test_p3_future_existing_exact_basis_replay_ignores_newer_policy_execution() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_disposition")
    first = module.decide_recovery(
        dispatch_commit_ref="dispatch:p3",
        observation_refs=("obs:1",),
        recovery_classification="unknown",
        policy_ref="policy:p3:v1",
    )
    replay = module.replay_recovery_disposition(first.id, current_policy_ref="policy:p3:v2")
    assert replay.id == first.id
    assert replay.policy_ref == "policy:p3:v1"


@_xfail("B4-P3 production: RecoveryDisposition remains non-self-executing")
def test_p3_future_disposition_does_not_authorize_application_or_provider_calls() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_disposition")
    disposition = module.RecoveryDisposition(
        id="recovery-disposition:p3",
        dispatch_commit_ref="dispatch:p3",
        basis_refs=("obs:1",),
        action="retry-idempotent",
        policy_ref="policy:p3:v1",
    )
    assert disposition.application_ref is None
    assert disposition.invocation_permit_ref is None
    assert disposition.terminal_authorized is False
