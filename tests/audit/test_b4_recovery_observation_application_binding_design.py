"""B4 RecoveryObservation ↔ RecoveryApplication binding audit.

Audit only. This file authorizes no RecoveryObservation schema production,
reconciliation provider call, Runtime consumption, repeatability contract,
configured-provider binding, retry, fresh invocation authority, or P5 import.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect

import pytest

from portable_runtime.core.models import Event
from portable_runtime.core.runtime import Runtime
from portable_runtime.workflows.recovery_application import RecoveryApplication
from portable_runtime.workflows.recovery_observation import (
    RecoveryObservation,
    RecoveryObservationCommitRequest,
    recovery_observation_from_event,
)


def _xfail(reason: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(strict=True, reason=reason)


def _legacy_observation_event() -> Event:
    return Event(
        id="recovery_observation_legacy",
        type="RecoveryObservationRecorded",
        subject_ref="dispatch:legacy",
        payload={
            "schema": "recovery-observation-v1",
            "semantic_level": "recovery-observation",
            "authoritative_outcome": False,
            "observation_instance_ref": "legacy-instance",
            "dispatch_commit_ref": "dispatch:legacy",
            "action_ref": "action:legacy",
            "attempt_ref": "attempt:legacy",
            "step_ref": "step:legacy",
            "request_ref": "request:legacy",
            "provider_id": "provider:legacy",
            "idempotency_key": None,
            "observation_source": "provider-reconcile",
            "reported_status": "reported-unknown",
            "provenance_refs": ["recovery_application_looks_like_a_ref"],
        },
    )


def test_ab_audit_current_observation_request_has_no_application_binding() -> None:
    fields = set(RecoveryObservationCommitRequest.__dataclass_fields__)
    assert fields == {
        "observation_instance_ref",
        "dispatch_commit_ref",
        "observation_source",
        "reported_status",
        "provenance_refs",
    }
    assert "recovery_application_ref" not in fields


def test_ab_audit_current_observation_has_no_application_binding() -> None:
    fields = set(RecoveryObservation.__dataclass_fields__)
    assert "recovery_application_ref" not in fields
    assert "provenance_refs" in fields


def test_ab_audit_application_carries_exact_source_graph_refs() -> None:
    fields = set(RecoveryApplication.__dataclass_fields__)
    assert {
        "disposition_ref",
        "application_kind",
        "source_dispatch_ref",
        "source_attempt_ref",
        "source_step_ref",
        "source_action_ref",
        "source_request_ref",
        "source_provider_id",
    } <= fields


def test_ab_audit_current_observation_identity_is_instance_ref_based() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_observation")
    source = inspect.getsource(module.prepare_recovery_observation_commit)
    assert '"observation_instance_ref": instance_ref' in source
    assert "recovery_application_ref" not in source


def test_ab_audit_legacy_provider_reconcile_observation_still_decodes_unbound() -> None:
    observation = recovery_observation_from_event(_legacy_observation_event())
    assert observation.observation_source == "provider-reconcile"
    assert observation.provenance_refs == ("recovery_application_looks_like_a_ref",)
    assert not hasattr(observation, "recovery_application_ref")
    assert observation.authoritative_outcome is False


def test_ab_audit_runtime_legacy_reconcile_allocates_new_observation_instance() -> None:
    source = inspect.getsource(Runtime.reconcile)
    assert 'new_id(\n                                "recovery_observation_instance"' in source
    assert "recovery_application_ref" not in source


def test_ab_audit_historical_source_string_is_not_application_authority() -> None:
    event = _legacy_observation_event()
    observation = recovery_observation_from_event(event)
    assert observation.observation_source == "provider-reconcile"
    assert "recovery_application_looks_like_a_ref" in observation.provenance_refs
    assert not hasattr(observation, "recovery_application_ref")


def test_ab_audit_no_application_observation_production_module_exists() -> None:
    assert (
        importlib.util.find_spec(
            "portable_runtime.workflows.recovery_application_observation"
        )
        is None
    )


@_xfail("B4 AB-001: opaque provenance strings cannot establish application authority")
def test_ab_001_opaque_provenance_is_not_application_authority() -> None:
    module = importlib.import_module(
        "portable_runtime.workflows.recovery_application_observation"
    )
    legacy = recovery_observation_from_event(_legacy_observation_event())
    assert module.is_application_completion(legacy) is False


@_xfail("B4 AB-002: application-bound request surface cannot accept caller dispatch/instance identity")
def test_ab_002_bound_request_surface_is_application_plus_result_only() -> None:
    module = importlib.import_module(
        "portable_runtime.workflows.recovery_application_observation"
    )
    fields = set(module.RecoveryApplicationObservationCommitRequest.__dataclass_fields__)
    assert fields == {
        "recovery_application_ref",
        "observation_source",
        "reported_status",
        "provenance_refs",
    }
    assert "dispatch_commit_ref" not in fields
    assert "observation_instance_ref" not in fields


@_xfail("B4 AB-003: exact durable RecoveryApplication is required")
def test_ab_003_missing_or_forged_application_fails_closed() -> None:
    module = importlib.import_module(
        "portable_runtime.workflows.recovery_application_observation"
    )
    with pytest.raises(ValueError, match="RecoveryApplication|application|durable"):
        module.prepare_recovery_application_observation_commit(
            store=None,
            request=module.RecoveryApplicationObservationCommitRequest(
                recovery_application_ref="recovery_application:forged",
                observation_source="provider-reconcile",
                reported_status="reported-unknown",
                provenance_refs=(),
            ),
        )


@_xfail("B4 AB-004: only reconciliation-request RecoveryApplication may bind completion observation")
def test_ab_004_wrong_application_kind_fails_closed() -> None:
    module = importlib.import_module(
        "portable_runtime.workflows.recovery_application_observation"
    )
    fixture = module.ApplicationObservationAuditFixture.example(
        application_kind="retry-request"
    )
    with pytest.raises(ValueError, match="reconciliation-request|kind|application"):
        fixture.prepare_bound_observation()


@_xfail("B4 AB-005: application source graph must be reconstructed and match exact dispatch/Attempt/Step/Action")
def test_ab_005_mismatched_application_dispatch_graph_fails_closed() -> None:
    module = importlib.import_module(
        "portable_runtime.workflows.recovery_application_observation"
    )
    fixture = module.ApplicationObservationAuditFixture.example()
    fixture.rebind_source_dispatch("dispatch:other")
    with pytest.raises(ValueError, match="dispatch|Attempt|Action|binding|rebound"):
        fixture.prepare_bound_observation()


@_xfail("B4 AB-006: legacy unbound RecoveryObservation stays valid but is never application completion")
def test_ab_006_legacy_unbound_observation_is_not_completion() -> None:
    module = importlib.import_module(
        "portable_runtime.workflows.recovery_application_observation"
    )
    legacy = recovery_observation_from_event(_legacy_observation_event())
    assert module.is_application_completion(legacy) is False
    assert module.bound_application_ref(legacy) is None


@_xfail("B4 AB-007: one exact application derives one stable completion observation identity")
def test_ab_007_application_derives_stable_observation_identity() -> None:
    module = importlib.import_module(
        "portable_runtime.workflows.recovery_application_observation"
    )
    first = module.application_observation_identity("recovery_application:A")
    second = module.application_observation_identity("recovery_application:A")
    other = module.application_observation_identity("recovery_application:B")
    assert first == second
    assert first != other


@_xfail("B4 AB-008: same application + same semantics replays one durable bound observation")
def test_ab_008_same_application_same_semantics_replays() -> None:
    module = importlib.import_module(
        "portable_runtime.workflows.recovery_application_observation"
    )
    fixture = module.ApplicationObservationAuditFixture.example()
    first = fixture.commit_bound_observation(status="reported-succeeded")
    replay = fixture.commit_bound_observation(status="reported-succeeded")
    assert replay == first
    assert fixture.bound_observation_count(first.recovery_application_ref) == 1


@_xfail("B4 AB-009: same application + changed reported semantics is identity rebound")
def test_ab_009_same_application_changed_report_is_rebound() -> None:
    module = importlib.import_module(
        "portable_runtime.workflows.recovery_application_observation"
    )
    fixture = module.ApplicationObservationAuditFixture.example()
    fixture.commit_bound_observation(status="reported-succeeded")
    with pytest.raises(ValueError, match="rebound|conflict|identity|semantics"):
        fixture.commit_bound_observation(status="reported-failed")


@_xfail("B4 AB-010: one application cannot accumulate arbitrary second completion observations")
def test_ab_010_same_application_cannot_accumulate_second_completion() -> None:
    module = importlib.import_module(
        "portable_runtime.workflows.recovery_application_observation"
    )
    fixture = module.ApplicationObservationAuditFixture.example()
    first = fixture.commit_bound_observation(
        status="reported-unknown",
        provenance_refs=("provider-report:1",),
    )
    with pytest.raises(ValueError, match="rebound|conflict|identity|semantics"):
        fixture.commit_bound_observation(
            status="reported-unknown",
            provenance_refs=("provider-report:2",),
        )
    assert fixture.bound_observation_count(first.recovery_application_ref) == 1


@_xfail("B4 AB-011: bound observation remains execution-level only")
def test_ab_011_bound_observation_is_not_outcome_or_recovery_decision() -> None:
    module = importlib.import_module(
        "portable_runtime.workflows.recovery_application_observation"
    )
    fixture = module.ApplicationObservationAuditFixture.example()
    observation = fixture.commit_bound_observation(status="reported-succeeded")
    assert observation.authoritative_outcome is False
    assert fixture.outcomes == 0
    assert fixture.recovery_dispositions == 0
    assert fixture.recovery_applications == 1


@_xfail("B4 AB-012: bound observation commit creates no follow-on recovery or fresh invocation authority")
def test_ab_012_bound_commit_has_no_follow_on_authority() -> None:
    module = importlib.import_module(
        "portable_runtime.workflows.recovery_application_observation"
    )
    fixture = module.ApplicationObservationAuditFixture.example()
    fixture.commit_bound_observation(status="reported-unknown")
    assert fixture.new_recovery_dispositions == 0
    assert fixture.new_recovery_applications == 0
    assert fixture.capability_requests == 0
    assert fixture.invocation_permits == 0
    assert fixture.attempts == 0
    assert fixture.dispatches == 0
    assert fixture.provider_calls == 0


@_xfail("B4 AB-013: direct application-bound RecoveryObservation event append remains closed")
def test_ab_013_direct_bound_event_append_is_denied() -> None:
    module = importlib.import_module(
        "portable_runtime.workflows.recovery_application_observation"
    )
    fixture = module.ApplicationObservationAuditFixture.example()
    forged = module.forged_bound_observation_event(
        recovery_application_ref=fixture.application_ref
    )
    with pytest.raises(ValueError, match="RecoveryObservation|commit|authority"):
        fixture.store.append_event(forged)


@_xfail("B4 AB-014: P5 import of application-bound observation authority remains unsupported")
def test_ab_014_serialized_bound_observation_import_fails_closed() -> None:
    module = importlib.import_module(
        "portable_runtime.workflows.recovery_application_observation"
    )
    fixture = module.ApplicationObservationAuditFixture.example()
    state = {
        "event": [
            module.forged_bound_observation_event(
                recovery_application_ref=fixture.application_ref
            ).model_dump(mode="json")
        ]
    }
    with pytest.raises(ValueError, match="P5|import|RecoveryObservation"):
        fixture.store.import_state(state)
