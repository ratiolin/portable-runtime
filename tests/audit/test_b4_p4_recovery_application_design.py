"""B4-P4 design/counterexample audit for RecoveryApplication.

The audit freezes a responsibility seam only.  No test in this file authorizes
RecoveryDisposition consumption, provider execution, fresh attempt creation,
or terminal completion.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json

import pytest

from portable_runtime.core.boundary_stages import BoundaryStagePlan, precommit_execution_records
from portable_runtime.core.qualification import InvocationPermit
from portable_runtime.governance.dispatch import GovernanceDispatchCommitter
from portable_runtime.workflows.recovery_disposition import RecoveryDispositionCommitRequest


def _xfail(reason: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(strict=True, reason=reason)


def _application_identity(disposition_ref: str) -> str:
    payload = {
        "schema": "recovery-application-v1",
        "disposition_ref": disposition_ref,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"recovery_application_{hashlib.sha256(raw.encode()).hexdigest()}"


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


@_xfail("B4-P4 production: RecoveryApplication authority object is not implemented")
def test_p4c_001_application_request_carries_only_exact_disposition_ref() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_application")
    fields = set(module.RecoveryApplicationCommitRequest.__dataclass_fields__)
    assert fields == {"disposition_ref"}
    forbidden = {
        "action",
        "application_kind",
        "dispatch_commit_ref",
        "attempt_ref",
        "provider_id",
        "request_id",
        "idempotency_key",
        "invocation_permit_ref",
    }
    assert fields.isdisjoint(forbidden)


@_xfail("B4-P4 production: exact disposition must reconstruct one deterministic application identity")
def test_p4c_002_same_disposition_replays_one_application_intent() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_application")
    store = module.InMemoryRecoveryApplicationAuditStore.example()
    request = module.RecoveryApplicationCommitRequest(
        disposition_ref="recovery_disposition:p4",
    )
    first = store.commit_recovery_application(request)
    replay = store.commit_recovery_application(request)
    assert replay == first
    assert first.id == _application_identity(request.disposition_ref)


@_xfail("B4-P4 production: application semantics are payload under disposition identity and rebound fails closed")
def test_p4c_003_same_application_identity_cannot_rebind_semantics() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_application")
    store = module.InMemoryRecoveryApplicationAuditStore.example()
    request = module.RecoveryApplicationCommitRequest(
        disposition_ref="recovery_disposition:p4",
    )
    first = store.commit_recovery_application(request)
    store.inject_changed_mapping_for_test(first.disposition_ref)
    with pytest.raises(ValueError, match="rebound|identity|semantics|nondetermin"):
        store.commit_recovery_application(request)


@_xfail("B4-P4 production: retry application must preserve idempotency identity without creating execution authority")
def test_p4c_004_retry_application_preserves_old_idempotency_but_creates_no_attempt_or_permit() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_application")
    prepared = module.RecoveryApplicationAuditFixture.prepare(
        action="retry-idempotent",
        source_attempt_id="attempt:p4:old",
        source_dispatch_ref="dispatch:p4:old",
        source_idempotency_key="idem:p4",
    )
    application = prepared.application
    assert application.application_kind == "retry-request"
    assert application.source_attempt_ref == "attempt:p4:old"
    assert application.source_dispatch_ref == "dispatch:p4:old"
    assert application.idempotency_key == "idem:p4"
    assert getattr(application, "attempt_ref", None) is None
    assert getattr(application, "invocation_permit_ref", None) is None
    assert getattr(application, "new_dispatch_commit_ref", None) is None


@_xfail("B4-P4 production: automated retry consumption must create fresh execution identity and never revive old dispatch")
def test_p4c_005_retry_consumption_requires_fresh_attempt_and_fresh_dispatch() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_application")
    result = module.RecoveryApplicationAuditFixture.consume_retry(
        application_ref="recovery_application:p4",
        source_attempt_ref="attempt:p4:old",
        source_dispatch_ref="dispatch:p4:old",
        idempotency_key="idem:p4",
    )
    assert result.request.id != "request:p4:old"
    assert result.attempt.id != "attempt:p4:old"
    assert result.attempt.idempotency_key == "idem:p4"
    assert result.dispatch_commit_ref != "dispatch:p4:old"
    assert result.attempt.metadata["recovery_application_ref"] == "recovery_application:p4"
    assert result.attempt.metadata["prior_attempt_ref"] == "attempt:p4:old"


@_xfail("B4-P4 production: fresh retry must re-enter qualification/admission instead of minting execution authority inside P4")
def test_p4c_006_retry_consumer_reenters_existing_execution_boundary() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_application")
    trace = module.RecoveryApplicationAuditFixture.retry_stage_trace()
    assert trace.index("recovery-application") < trace.index("qualification")
    assert trace.index("qualification") < trace.index("invocation-permit")
    assert trace.index("invocation-permit") < trace.index("fresh-attempt")
    assert trace.index("fresh-attempt") < trace.index("dispatch-commit")
    assert trace.index("dispatch-commit") < trace.index("provider-invoke")


@_xfail("B4-P4 production: reconcile-again application is responsibility intent, not a provider call")
def test_p4c_007_reconcile_application_has_no_reality_exit() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_application")
    prepared = module.RecoveryApplicationAuditFixture.prepare(action="reconcile-again")
    assert prepared.application.application_kind == "reconciliation-request"
    source = inspect.getsource(module)
    assert "provider.reconcile" not in source
    assert "RealityBoundary.reconcile" not in source


@_xfail("B4-P4 production: non-execution dispositions cannot become provider or terminal authority")
@pytest.mark.parametrize(
    ("action", "application_kind"),
    [
        ("hold-unresolved", "hold"),
        ("require-manual-resolution", "manual-resolution-handoff"),
        ("accept-objective-resolution", "objective-resolution-acceptance"),
    ],
)
def test_p4c_008_non_execution_application_never_executes_or_completes(
    action: str,
    application_kind: str,
) -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_application")
    prepared = module.RecoveryApplicationAuditFixture.prepare(action=action)
    assert prepared.application.application_kind == application_kind
    assert prepared.provider_calls == 0
    assert prepared.new_attempts == 0
    assert prepared.terminal_commits == 0


@_xfail("B4-P4 production: RecoveryApplicationRecorded must be store-owned authority")
def test_p4c_009_direct_application_event_append_is_denied() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_application")
    store = module.InMemoryRecoveryApplicationAuditStore.example()
    with pytest.raises(ValueError, match="RecoveryApplication|commit_recovery_application"):
        store.append_forged_recovery_application_event(
            disposition_ref="recovery_disposition:p4",
            application_kind="retry-request",
        )


def test_p4_audit_serialized_application_authority_remains_out_of_scope() -> None:
    """P4 must not silently close the independent P5 portability question."""

    bundle_source = inspect.getsource(importlib.import_module("portable_runtime.stores.bundle"))
    memory_source = inspect.getsource(importlib.import_module("portable_runtime.stores.memory"))
    sqlite_source = inspect.getsource(importlib.import_module("portable_runtime.stores.sqlite"))
    assert "RecoveryApplicationRecorded" not in bundle_source
    assert "RecoveryApplicationRecorded" not in memory_source
    assert "RecoveryApplicationRecorded" not in sqlite_source
