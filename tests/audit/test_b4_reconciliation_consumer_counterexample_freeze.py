"""B4 reconciliation consumer counterexample freeze.

Audit only. This file freezes consumer responsibility boundaries after A/B/C
substrates are production-supported. It authorizes no consumer production,
provider call, Runtime integration, RealityBoundary change, retry, P5 import,
or Experience Governance work.

Names used for hypothetical future consumer helpers are audit vocabulary, not a
production API naming requirement. The semantic obligations are the contract.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect

import pytest

from portable_runtime.core.boundary import RealityBoundary
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.core.runtime import Runtime
from portable_runtime.interfaces.provider import CapabilityProvider
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.recovery_application_observation import (
    RecoveryApplicationObservationInMemoryStateStore,
    RecoveryApplicationObservationSQLiteStateStore,
)
from portable_runtime.workflows.recovery_application_observation import (
    RecoveryApplicationObservationCommitRequest,
)
from portable_runtime.workflows.recovery_observation import RecoveryObservationCommitRequest


def _xfail(reason: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(strict=True, reason=reason)


def _consumer_module():  # type: ignore[no-untyped-def]
    return importlib.import_module("portable_runtime.workflows.recovery_reconciliation")


# ---------------------------------------------------------------------------
# Current-state facts. These pass now and prevent audit text from drifting away
# from the production substrate that the future consumer must consume.
# ---------------------------------------------------------------------------


def test_consumer_audit_baseline_runtime_reconcile_is_step_attempt_bypass() -> None:
    signature = inspect.signature(Runtime.reconcile)
    source = inspect.getsource(Runtime.reconcile)
    assert list(signature.parameters) == ["self", "step_id"]
    assert "list_attempts(step_id)" in source
    assert "self.capabilities.reconcile(last.request_ref, last.provider_id)" in source
    assert "RecoveryApplication" not in source


def test_consumer_audit_baseline_boundary_reconcile_re_resolves_provider_id() -> None:
    signature = inspect.signature(RealityBoundary.reconcile)
    source = inspect.getsource(RealityBoundary.reconcile)
    assert {"request_id", "provider_id"} <= set(signature.parameters)
    assert "registry.get(provider_id)" in source
    assert "await reconcile(request_id)" in source


def test_consumer_audit_a_authority_is_opt_in_store_capability() -> None:
    assert hasattr(
        RecoveryApplicationObservationInMemoryStateStore,
        "get_recovery_application_observation",
    )
    assert hasattr(
        RecoveryApplicationObservationInMemoryStateStore,
        "commit_recovery_application_observation",
    )
    assert hasattr(
        RecoveryApplicationObservationSQLiteStateStore,
        "get_recovery_application_observation",
    )
    assert hasattr(
        RecoveryApplicationObservationSQLiteStateStore,
        "commit_recovery_application_observation",
    )
    assert not hasattr(InMemoryStateStore, "get_recovery_application_observation")
    assert not hasattr(InMemoryStateStore, "commit_recovery_application_observation")


def test_consumer_audit_a_commit_request_does_not_accept_source_graph_identity() -> None:
    fields = set(RecoveryApplicationObservationCommitRequest.__dataclass_fields__)
    assert fields == {
        "recovery_application_ref",
        "observation_source",
        "reported_status",
        "provenance_refs",
    }
    for forbidden in (
        "dispatch_commit_ref",
        "request_id",
        "provider_id",
        "provider_execution_binding_ref",
        "repeatability_authority_ref",
        "observation_ref",
    ):
        assert forbidden not in fields


def test_consumer_audit_generic_observation_commit_is_not_application_completion_surface() -> None:
    fields = set(RecoveryObservationCommitRequest.__dataclass_fields__)
    assert "recovery_application_ref" not in fields
    assert "dispatch_commit_ref" in fields
    assert "observation_instance_ref" in fields


def test_consumer_audit_b_registry_resolution_is_exact_not_same_id_fallback() -> None:
    source = inspect.getsource(ProviderRegistry.resolve_execution_binding)
    assert "capture_execution_target(historical.provider_id)" in source
    assert "if current != historical" in source
    assert "return None" in source


def test_consumer_audit_c_registry_eligibility_requires_exact_historical_binding() -> None:
    source = inspect.getsource(ProviderRegistry.reconciliation_repeatability_eligibility)
    assert "resolve_execution_binding(historical_binding)" in source
    assert "required_subject_identity" in source
    assert "current_contract" not in inspect.signature(
        ProviderRegistry.reconciliation_repeatability_eligibility
    ).parameters


def test_consumer_audit_provider_reconcile_protocol_remains_request_id_only() -> None:
    signature = inspect.signature(CapabilityProvider.reconcile)
    assert list(signature.parameters) == ["self", "request_id"]


def test_consumer_audit_no_authoritative_consumer_production_module_exists() -> None:
    assert importlib.util.find_spec("portable_runtime.workflows.recovery_reconciliation") is None


# ---------------------------------------------------------------------------
# RCX-001..025. Strict xfails are counterexample obligations, not production
# authorization. They graduate only in a separately authorized consumer slice.
# ---------------------------------------------------------------------------


@_xfail("RCX-001: step/latest Attempt identity is not RecoveryApplication authority")
def test_rcx_001_consumer_must_start_from_exact_recovery_application() -> None:
    module = _consumer_module()
    fields = set(module.RecoveryReconciliationRequest.__dataclass_fields__)
    assert fields == {"recovery_application_ref"}


@_xfail("RCX-002: absent RecoveryApplication must produce zero provider calls")
def test_rcx_002_missing_application_zero_calls() -> None:
    module = _consumer_module()
    fixture = module.ReconciliationConsumerAuditFixture.missing_application()
    result = fixture.consume()
    assert result.status in {"unavailable", "ineligible"}
    assert fixture.reconcile_calls == 0


@_xfail("RCX-003: non-reconciliation application kind must produce zero provider calls")
def test_rcx_003_wrong_application_kind_zero_calls() -> None:
    module = _consumer_module()
    for kind in (
        "hold",
        "retry-request",
        "manual-resolution-handoff",
        "objective-resolution-acceptance",
    ):
        fixture = module.ReconciliationConsumerAuditFixture.example(application_kind=kind)
        result = fixture.consume()
        assert result.status in {"unavailable", "ineligible"}
        assert fixture.reconcile_calls == 0


@_xfail("RCX-004: application/disposition/dispatch source-graph rebound fails before reality exit")
def test_rcx_004_source_graph_mismatch_zero_calls() -> None:
    module = _consumer_module()
    fixture = module.ReconciliationConsumerAuditFixture.example(graph_rebound=True)
    with pytest.raises(ValueError, match="graph|binding|rebound|mismatch"):
        fixture.consume()
    assert fixture.reconcile_calls == 0


@_xfail("RCX-005: existing A completion must replay before B/C/current-registry resolution")
def test_rcx_005_a_first_short_circuits_all_current_state_resolution() -> None:
    module = _consumer_module()
    fixture = module.ReconciliationConsumerAuditFixture.example(
        bound_observation_exists=True,
        current_target_available=False,
        current_repeatability_available=False,
    )
    result = fixture.consume()
    assert result.replayed is True
    assert fixture.reconcile_calls == 0
    assert fixture.execution_binding_resolutions == 0
    assert fixture.repeatability_evaluations == 0


@_xfail("RCX-006: generic/unbound RecoveryObservation is not application completion")
def test_rcx_006_generic_observation_does_not_satisfy_a() -> None:
    module = _consumer_module()
    fixture = module.ReconciliationConsumerAuditFixture.example(
        generic_observation_exists=True,
        bound_observation_exists=False,
    )
    assert fixture.a_completion_exists() is False


@_xfail("RCX-007: historical dispatch without B is ineligible and never backfilled")
def test_rcx_007_missing_historical_b_zero_calls() -> None:
    module = _consumer_module()
    fixture = module.ReconciliationConsumerAuditFixture.example(historical_binding=None)
    result = fixture.consume()
    assert result.status in {"unavailable", "ineligible"}
    assert fixture.reconcile_calls == 0


@_xfail("RCX-008: same provider_id with different B cannot retarget historical reconciliation")
def test_rcx_008_same_id_different_b_zero_calls() -> None:
    module = _consumer_module()
    fixture = module.ReconciliationConsumerAuditFixture.example(
        same_provider_id=True,
        current_binding_matches=False,
    )
    result = fixture.consume()
    assert result.status in {"unavailable", "ineligible"}
    assert fixture.reconcile_calls == 0


@_xfail("RCX-009: unavailable exact historical B target must produce zero provider calls")
def test_rcx_009_historical_target_unavailable_zero_calls() -> None:
    module = _consumer_module()
    fixture = module.ReconciliationConsumerAuditFixture.example(current_target_available=False)
    result = fixture.consume()
    assert result.status in {"unavailable", "ineligible"}
    assert fixture.reconcile_calls == 0


@_xfail("RCX-010: historical C absent must produce zero provider calls")
def test_rcx_010_missing_historical_c_zero_calls() -> None:
    module = _consumer_module()
    fixture = module.ReconciliationConsumerAuditFixture.example(historical_repeatability=None)
    result = fixture.consume()
    assert result.status in {"unavailable", "ineligible"}
    assert fixture.reconcile_calls == 0


@_xfail("RCX-011: C subject must equal exact historical dispatch request_id")
def test_rcx_011_c_subject_mismatch_zero_calls() -> None:
    module = _consumer_module()
    fixture = module.ReconciliationConsumerAuditFixture.example(
        historical_request_id="request:A",
        c_subject_identity="request:B",
    )
    result = fixture.consume()
    assert result.status in {"unavailable", "ineligible"}
    assert fixture.reconcile_calls == 0


@_xfail("RCX-012: C protocol/version/contract drift must produce zero provider calls")
def test_rcx_012_c_drift_zero_calls() -> None:
    module = _consumer_module()
    for drift in ("protocol", "protocol-version", "contract-version", "contract-digest"):
        fixture = module.ReconciliationConsumerAuditFixture.example(c_drift=drift)
        result = fixture.consume()
        assert result.status in {"unavailable", "ineligible"}
        assert fixture.reconcile_calls == 0


@_xfail("RCX-013: current-only repeat-safe configuration cannot manufacture historical C")
def test_rcx_013_current_only_c_is_not_historical_authority() -> None:
    module = _consumer_module()
    fixture = module.ReconciliationConsumerAuditFixture.example(
        historical_repeatability=None,
        current_repeatability="repeat-safe",
    )
    result = fixture.consume()
    assert result.status in {"unavailable", "ineligible"}
    assert fixture.reconcile_calls == 0


@_xfail("RCX-014: A+B+C may cross only reconciliation boundary and never provider.invoke")
def test_rcx_014_exact_substrates_never_authorize_provider_invoke() -> None:
    module = _consumer_module()
    fixture = module.ReconciliationConsumerAuditFixture.example(exact_abc=True)
    fixture.consume()
    assert fixture.reconcile_calls == 1
    assert fixture.provider_invocations == 0


@_xfail("RCX-015: reality exit must receive exact request-id and exact B-resolved provider target")
def test_rcx_015_exact_request_and_exact_target_cross_reality_boundary() -> None:
    module = _consumer_module()
    fixture = module.ReconciliationConsumerAuditFixture.example(
        exact_abc=True,
        historical_request_id="request:exact",
    )
    fixture.consume()
    assert fixture.reality_exit_request_id == "request:exact"
    assert fixture.reality_exit_provider is fixture.exact_resolved_provider
    assert fixture.provider_id_relookups_after_b == 0


@_xfail("RCX-016: provider result must commit through application-bound A, not generic observation")
def test_rcx_016_provider_result_commits_application_bound_observation() -> None:
    module = _consumer_module()
    fixture = module.ReconciliationConsumerAuditFixture.example(exact_abc=True)
    result = fixture.consume(provider_status="succeeded")
    assert result.observation.recovery_application_ref == fixture.application.id
    assert fixture.application_observation_commits == 1
    assert fixture.generic_observation_commits == 0


@_xfail("RCX-017: provider return plus failed A commit is not durable completion")
def test_rcx_017_a_commit_failure_returns_unknown_without_higher_authority() -> None:
    module = _consumer_module()
    fixture = module.ReconciliationConsumerAuditFixture.example(
        exact_abc=True,
        fail_application_observation_commit=True,
    )
    result = fixture.consume(provider_status="succeeded")
    assert result.status in {"unknown", "unavailable"}
    assert result.durable_completion is False
    assert fixture.confirmed_outcomes == 0
    assert fixture.new_recovery_dispositions == 0
    assert fixture.new_recovery_applications == 0


@_xfail("RCX-018: exact C permits re-entry while an earlier identical reconciliation query may still be in flight")
def test_rcx_018_pre_a_crash_repeat_safe_allows_overlapping_exact_query() -> None:
    module = _consumer_module()
    fixture = module.ReconciliationConsumerAuditFixture.example(
        exact_abc=True,
        bound_observation_exists=False,
        earlier_reconciliation_may_still_be_in_flight=True,
    )
    result = fixture.consume()
    assert result.status not in {"ineligible", "blocked"}
    assert fixture.reconcile_calls == 1


@_xfail("RCX-019: after A durability every same-application call is a zero-call replay")
def test_rcx_019_post_a_calls_zero_even_if_b_or_c_later_drift() -> None:
    module = _consumer_module()
    fixture = module.ReconciliationConsumerAuditFixture.example(
        bound_observation_exists=True,
        current_target_available=False,
        c_drift="contract-digest",
    )
    first = fixture.consume()
    second = fixture.consume()
    assert first.replayed is True and second.replayed is True
    assert fixture.reconcile_calls == 0


@_xfail("RCX-020: consumer creates no fresh request/permit/attempt/dispatch or provider.invoke")
def test_rcx_020_no_fresh_invocation_chain() -> None:
    module = _consumer_module()
    fixture = module.ReconciliationConsumerAuditFixture.example(exact_abc=True)
    fixture.consume()
    assert fixture.fresh_capability_requests == 0
    assert fixture.invocation_permits == 0
    assert fixture.fresh_attempts == 0
    assert fixture.dispatch_commits == 0
    assert fixture.provider_invocations == 0


@_xfail("RCX-021: consumer creates no Outcome/RecoveryDisposition/RecoveryApplication automatically")
def test_rcx_021_no_automatic_decision_or_new_application_chain() -> None:
    module = _consumer_module()
    fixture = module.ReconciliationConsumerAuditFixture.example(exact_abc=True)
    fixture.consume()
    assert fixture.confirmed_outcomes == 0
    assert fixture.new_recovery_dispositions == 0
    assert fixture.new_recovery_applications == 0


@_xfail("RCX-022: RecoveryReconciliationAttemptRecorded remains unnecessary for repeat-safe-only v1")
def test_rcx_022_no_new_durable_reconciliation_attempt_fact() -> None:
    module = _consumer_module()
    fixture = module.ReconciliationConsumerAuditFixture.example(exact_abc=True)
    fixture.consume()
    assert fixture.recovery_reconciliation_attempt_records == 0


@_xfail("RCX-023: RecoveryApplicationConsumed remains unnecessary")
def test_rcx_023_no_generic_application_consumed_fact() -> None:
    module = _consumer_module()
    fixture = module.ReconciliationConsumerAuditFixture.example(exact_abc=True)
    fixture.consume()
    assert fixture.recovery_application_consumed_records == 0


@_xfail("RCX-024: legacy Runtime.reconcile(step_id) cannot remain an automated authority bypass")
def test_rcx_024_legacy_runtime_reconcile_cannot_reach_provider_without_application_abc() -> None:
    source = inspect.getsource(Runtime.reconcile)
    assert "self.capabilities.reconcile(last.request_ref, last.provider_id)" not in source
    assert "recovery_application" in source.lower() or "authoritative consumer" in source.lower()


@_xfail("RCX-025: P5/import/history cannot manufacture reconciliation consumer authority")
def test_rcx_025_serialized_or_assembled_authority_is_rejected() -> None:
    module = _consumer_module()
    with pytest.raises(ValueError, match="P5|import|historical|authority|unsupported"):
        module.consume_serialized_reconciliation_authority(
            {
                "recovery_application_ref": "application:caller",
                "provider_execution_binding_ref": "binding:caller",
                "repeatability_authority_ref": "repeatability:caller",
            }
        )
