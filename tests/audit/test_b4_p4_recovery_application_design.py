"""B4-P4 design/counterexample audit for RecoveryApplication.

P4a now authorizes only one durable non-executing application intent derived
from one exact RecoveryDisposition. P4b retry materialization and orchestration
consumption remain outside this production slice.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
from dataclasses import replace

import pytest

from portable_runtime.core.boundary_stages import BoundaryStagePlan, precommit_execution_records
from portable_runtime.core.models import Action, Event, StepAttempt
from portable_runtime.core.qualification import InvocationPermit
from portable_runtime.governance.dispatch import GovernanceDispatchCommitter
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.workflows.recovery_disposition import RecoveryDispositionCommitRequest
from tests.conformance.test_recovery_disposition_counterexamples import (
    _Policy,
    _observe,
    _seed_subject,
)


def _xfail(reason: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(strict=True, reason=reason)


def _application_identity(disposition_ref: str) -> str:
    payload = {
        "schema": "recovery-application-v1",
        "disposition_ref": disposition_ref,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"recovery_application_{hashlib.sha256(raw.encode()).hexdigest()}"


def _seed_disposition(
    action: str,
    *,
    effect_semantics: str = "reconcilable",
    suffix: str,
) -> tuple[InMemoryStateStore, dict[str, object], object]:
    store = InMemoryStateStore()
    graph = _seed_subject(store, suffix)
    step = store.get_step(str(graph["step"].id))
    assert step is not None
    step = step.model_copy(
        update={
            "effect_semantics": effect_semantics,
            "side_effect_class": effect_semantics,
        }
    )
    store.save_step(step)
    graph["step"] = step
    observation = _observe(store, graph, instance_ref=f"obs:{suffix}")
    disposition = store.commit_recovery_disposition(
        RecoveryDispositionCommitRequest(
            dispatch_commit_ref=str(graph["dispatch_ref"]),
            observation_refs=(observation.id,),
            outcome_refs=(),
            policy_ref="policy:recovery:p4-audit",
        ),
        policy=_Policy(action),
    )
    return store, graph, disposition


def test_p4_audit_p3_request_remains_decision_only() -> None:
    fields = set(RecoveryDispositionCommitRequest.__dataclass_fields__)
    assert fields == {
        "dispatch_commit_ref",
        "observation_refs",
        "outcome_refs",
        "policy_ref",
    }
    source = inspect.getsource(
        importlib.import_module("portable_runtime.workflows.recovery_disposition")
    )
    assert "RecoveryApplication" not in source
    assert "provider.invoke" not in source
    assert "provider.reconcile" not in source


def test_p4_audit_runtime_does_not_consume_recovery_dispositions() -> None:
    source = inspect.getsource(importlib.import_module("portable_runtime.core.runtime"))
    assert "RecoveryDispositionRecorded" not in source
    assert "commit_recovery_disposition" not in source
    assert "RecoveryApplication" not in source


def test_p4_audit_execution_reenters_qualification_before_fresh_precommit() -> None:
    plan = BoundaryStagePlan()
    assert plan.names.index("qualification") < plan.names.index("precommit")
    assert plan.names.index("governance-use") < plan.names.index("precommit")
    assert plan.names.index("authorization") < plan.names.index("precommit")
    assert plan.names.index("precommit") < plan.names.index("invocation")

    boundary_source = inspect.getsource(
        importlib.import_module("portable_runtime.core.boundary").RealityBoundary.execute
    )
    permit_position = boundary_source.index("InvocationPermit.issue(")
    precommit_position = boundary_source.index("precommit_execution_records(")
    dispatch_position = boundary_source.index("GovernanceDispatchCommitter(store).commit(")
    invoke_position = boundary_source.index("provider.invoke(")
    assert permit_position < precommit_position < dispatch_position < invoke_position


def test_p4_audit_existing_precommit_allocates_fresh_attempt_identity() -> None:
    source = inspect.getsource(precommit_execution_records)
    assert 'id=new_id("attempt")' in source
    assert "max((a.attempt_no for a in attempts), default=0) + 1" in source
    assert "InvocationPermit" not in source
    assert "GovernanceDispatchCommitter" not in source
    assert "provider.invoke" not in source


def test_p4_audit_permit_and_dispatch_remain_separate_execution_authorities() -> None:
    permit_source = inspect.getsource(InvocationPermit)
    dispatch_source = inspect.getsource(GovernanceDispatchCommitter)
    assert "StepAttempt(" not in permit_source
    assert "provider.invoke" not in permit_source
    assert "provider.invoke" not in dispatch_source
    assert "RecoveryApplication" not in permit_source
    assert "RecoveryApplication" not in dispatch_source


def test_p4_audit_candidate_application_identity_is_one_per_disposition() -> None:
    first = _application_identity("recovery_disposition:p4")
    replay = _application_identity("recovery_disposition:p4")
    different = _application_identity("recovery_disposition:p4:new-basis")
    assert replay == first
    assert different != first


def test_p4_audit_retry_request_specification_is_not_yet_durable() -> None:
    """The current P3 graph cannot authoritatively reconstruct a retry body."""

    action_fields = set(Action.model_fields)
    attempt_fields = set(StepAttempt.model_fields)
    request_body_fields = {
        "instruction",
        "parameters",
        "constraints",
        "actor_ref",
        "resource_ref",
        "subject_version_refs",
        "qualification_refs",
    }
    assert action_fields.isdisjoint(request_body_fields)
    assert attempt_fields.isdisjoint(request_body_fields)

    permit_source = inspect.getsource(InvocationPermit)
    dispatch_source = inspect.getsource(GovernanceDispatchCommitter.commit)
    assert "request_snapshot" in permit_source
    assert '"request_snapshot"' not in dispatch_source
    assert '"invocation_permit_digest"' in dispatch_source


def test_p4c_001_application_request_carries_only_exact_disposition_ref() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_application")
    fields = set(module.RecoveryApplicationCommitRequest.__dataclass_fields__)
    assert fields == {"disposition_ref"}


def test_p4c_002_same_disposition_replays_one_application_intent() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_application")
    store, _graph, disposition = _seed_disposition(
        "hold-unresolved",
        suffix="p4-replay",
    )
    request = module.RecoveryApplicationCommitRequest(disposition_ref=disposition.id)
    first = store.commit_recovery_application(request)
    replay = store.commit_recovery_application(request)
    assert replay == first
    assert first.id == _application_identity(disposition.id)


def test_p4c_003_same_application_identity_exposes_semantic_rebound() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_application")
    store, _graph, disposition = _seed_disposition(
        "hold-unresolved",
        suffix="p4-rebound",
    )
    request = module.RecoveryApplicationCommitRequest(disposition_ref=disposition.id)
    prepared = module.prepare_recovery_application_commit(store, request)
    rebound = replace(prepared.application, application_kind="retry-request")
    assert rebound.id == prepared.application.id
    assert not module.same_recovery_application_semantics(
        prepared.application,
        rebound,
    )


def test_p4c_004_retry_application_is_intent_not_fresh_execution() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_application")
    store, graph, disposition = _seed_disposition(
        "retry-idempotent",
        effect_semantics="idempotent",
        suffix="p4-retry",
    )
    prepared = module.prepare_recovery_application_commit(
        store,
        module.RecoveryApplicationCommitRequest(disposition_ref=disposition.id),
    )
    application = prepared.application
    assert application.application_kind == "retry-request"
    assert application.source_dispatch_ref == graph["dispatch_ref"]
    assert application.source_attempt_ref == graph["attempt"].id
    assert application.source_step_ref == graph["step"].id
    assert application.source_action_ref == graph["action"].id
    assert application.idempotency_key == graph["attempt"].idempotency_key
    assert getattr(application, "attempt_ref", None) is None
    assert getattr(application, "invocation_permit_ref", None) is None
    assert getattr(application, "new_dispatch_commit_ref", None) is None


def test_p4c_005_application_module_has_no_reality_exit_or_terminal_authority() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_application")
    source = inspect.getsource(module)
    forbidden = (
        "provider.invoke",
        "provider.reconcile",
        "RealityBoundary.execute",
        "RealityBoundary.reconcile",
        "InvocationPermit.issue",
        "precommit_execution_records",
        "GovernanceDispatchCommitter",
        "commit_terminal",
        "CompletionAuthority",
    )
    for token in forbidden:
        assert token not in source


@pytest.mark.parametrize(
    ("action", "application_kind"),
    [
        ("hold-unresolved", "hold"),
        ("reconcile-again", "reconciliation-request"),
        ("retry-idempotent", "retry-request"),
        ("require-manual-resolution", "manual-resolution-handoff"),
        ("accept-objective-resolution", "objective-resolution-acceptance"),
    ],
)
def test_p4c_006_application_kind_is_derived_from_durable_disposition(
    action: str,
    application_kind: str,
) -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_application")
    semantics = "idempotent" if action == "retry-idempotent" else "reconcilable"
    store, _graph, disposition = _seed_disposition(
        action,
        effect_semantics=semantics,
        suffix=f"p4-kind-{action}",
    )
    prepared = module.prepare_recovery_application_commit(
        store,
        module.RecoveryApplicationCommitRequest(disposition_ref=disposition.id),
    )
    assert prepared.application.application_kind == application_kind


def test_p4c_007_direct_application_event_append_is_denied() -> None:
    importlib.import_module("portable_runtime.workflows.recovery_application")
    store = InMemoryStateStore()
    with pytest.raises(ValueError, match="RecoveryApplication|commit_recovery_application"):
        store.append_event(
            Event(
                id="recovery_application_forged",
                type="RecoveryApplicationRecorded",
                subject_ref="recovery_disposition:forged",
                payload={
                    "schema": "recovery-application-v1",
                    "disposition_ref": "recovery_disposition:forged",
                    "application_kind": "retry-request",
                },
            )
        )


@_xfail("B4-P4b prerequisite: retry materialization must fail closed without authoritative invocation specification")
def test_p4c_008_retry_materialization_refuses_missing_durable_request_spec() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_application")
    store, _graph, disposition = _seed_disposition(
        "retry-idempotent",
        effect_semantics="idempotent",
        suffix="p4-missing-request-spec",
    )
    application = store.commit_recovery_application(
        module.RecoveryApplicationCommitRequest(disposition_ref=disposition.id)
    )
    with pytest.raises(ValueError, match="invocation specification|request snapshot|retry materialization"):
        module.prepare_recovery_retry_request(store, application.id)


def test_p4_audit_local_application_authority_does_not_close_p5_or_p4b() -> None:
    """Local P4a authority is not portability or Runtime consumption authority."""

    bundle_source = inspect.getsource(importlib.import_module("portable_runtime.stores.bundle"))
    memory_source = inspect.getsource(importlib.import_module("portable_runtime.stores.memory"))
    sqlite_source = inspect.getsource(importlib.import_module("portable_runtime.stores.sqlite"))
    runtime_source = inspect.getsource(importlib.import_module("portable_runtime.core.runtime"))
    assert "RecoveryApplicationRecorded" not in bundle_source
    assert "commit_recovery_application" in memory_source
    assert "commit_recovery_application" in sqlite_source
    assert "P5 RecoveryApplication authority import is unsupported" in memory_source
    assert "P5 RecoveryApplication authority import is unsupported" in sqlite_source
    assert "commit_recovery_application" not in runtime_source
    assert "RecoveryApplication" not in runtime_source
