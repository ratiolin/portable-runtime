"""B4 exact-source-provider retry pin / idempotency-domain audit.

Audit only. This file authorizes no retry materialization, provider pin
production API, cross-provider idempotency domain, Runtime consumption, or
provider execution.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect

import pytest

from portable_runtime.core.capabilities import CapabilityRequest, ProviderDescriptor
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.core.router import DeterministicPriorityRouting
from portable_runtime.governance.dispatch import dispatch_recovery_mode
from portable_runtime.workflows.recovery_application import RecoveryApplication


def _xfail(reason: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(strict=True, reason=reason)


def test_exact_pin_audit_recovery_application_retains_provider_and_idempotency() -> None:
    fields = set(RecoveryApplication.__dataclass_fields__)
    assert {"source_provider_id", "idempotency_key", "source_dispatch_ref", "source_request_ref"} <= fields


def test_exact_pin_audit_retry_classification_is_narrow() -> None:
    class Step:
        def __init__(self, effect_semantics: str) -> None:
            self.effect_semantics = effect_semantics

    class Attempt:
        metadata = {"dispatch_commit_ref": "dispatch:1"}

    attempt = Attempt()
    assert dispatch_recovery_mode(Step("pure"), attempt) == "idempotent-retry"
    assert dispatch_recovery_mode(Step("idempotent"), attempt) == "idempotent-retry"
    assert dispatch_recovery_mode(Step("deduplicatable"), attempt) == "idempotent-retry"
    assert dispatch_recovery_mode(Step("reconcilable"), attempt) == "reconcile"
    assert dispatch_recovery_mode(Step("irreversible-opaque"), attempt) == "unknown"


def test_exact_pin_audit_provider_descriptor_has_version_but_no_idempotency_domain() -> None:
    fields = set(ProviderDescriptor.model_fields)
    assert "version" in fields
    assert "idempotency_domain" not in fields
    assert "deduplication_domain" not in fields
    assert "replay_domain" not in fields


def test_exact_pin_audit_dispatch_does_not_bind_provider_version() -> None:
    module = importlib.import_module("portable_runtime.governance.dispatch")
    source = inspect.getsource(module.GovernanceDispatchCommitter.commit)
    assert '"provider_id"' in source
    assert '"provider_version"' not in source
    assert '"provider_binding"' not in source
    assert '"semantic_contract_digest"' not in source


def test_exact_pin_audit_registry_can_replace_same_provider_id_after_unregister() -> None:
    source = inspect.getsource(ProviderRegistry.register)
    unregister_source = inspect.getsource(ProviderRegistry.unregister)
    assert "provider already registered" in source
    assert "_providers.pop(provider_id" in unregister_source
    assert "_CIRCUITS.pop(descriptor.id" in source


def test_exact_pin_audit_preferred_provider_is_soft_routing_not_hard_pin() -> None:
    source = inspect.getsource(DeterministicPriorityRouting.select)
    assert "preferred_provider_ids" in source
    assert "sorted(" in source
    assert "matching" in source
    assert "exact_source_provider" not in source


def test_exact_pin_audit_no_production_retry_pin_module_exists() -> None:
    assert importlib.util.find_spec("portable_runtime.workflows.retry_provider_binding") is None
    assert importlib.util.find_spec("portable_runtime.core.idempotency_domain") is None


@_xfail("B4 exact-provider production: v1 retry target provider id must equal source provider id")
def test_epp_001_changed_provider_id_fails_closed() -> None:
    module = importlib.import_module("portable_runtime.workflows.retry_provider_binding")
    source = module.ProviderReplayBinding.example(provider_id="provider:a")
    with pytest.raises(ValueError, match="provider|source|pin|mismatch"):
        module.assert_exact_retry_target(source, target_provider_id="provider:b")


@_xfail("B4 exact-provider production: same provider id after replacement is not stable provider identity")
def test_epp_002_same_id_replaced_provider_identity_fails_closed() -> None:
    module = importlib.import_module("portable_runtime.workflows.retry_provider_binding")
    source = module.ProviderReplayBinding.example(
        provider_id="provider:a",
        provider_binding_digest="binding:old",
    )
    current = module.ProviderReplayBinding.example(
        provider_id="provider:a",
        provider_binding_digest="binding:new",
    )
    with pytest.raises(ValueError, match="binding|identity|provider|drift"):
        module.assert_same_provider_execution_identity(source, current)


@_xfail("B4 exact-provider production: historical provider identity cannot be backfilled from current registry")
def test_epp_003_missing_historical_provider_binding_is_not_retry_eligible() -> None:
    module = importlib.import_module("portable_runtime.workflows.retry_provider_binding")
    with pytest.raises(ValueError, match="historical|binding|missing|backfill"):
        module.retry_binding_from_historical_dispatch(
            dispatch_ref="dispatch:old-with-provider-id-only",
            current_provider_id="provider:a",
            current_provider_version="2",
        )


@_xfail("B4 exact-provider production: retry requires exact source idempotency identity")
def test_epp_004_missing_source_idempotency_identity_is_ineligible() -> None:
    module = importlib.import_module("portable_runtime.workflows.retry_provider_binding")
    binding = module.ProviderReplayBinding.example(idempotency_key=None)
    eligibility = module.exact_retry_eligibility(binding)
    assert eligibility.allowed is False
    assert "idempotency" in eligibility.reason.lower()


@_xfail("B4 exact-provider production: changing idempotency identity must fail closed")
def test_epp_005_changed_idempotency_identity_fails_closed() -> None:
    module = importlib.import_module("portable_runtime.workflows.retry_provider_binding")
    source = module.ProviderReplayBinding.example(idempotency_key="idem:source")
    with pytest.raises(ValueError, match="idempotency|replay|identity"):
        module.assert_retry_idempotency(source, retry_idempotency_key="idem:new")


@_xfail("B4 exact-provider production: reconcile/opaque semantics cannot be promoted to idempotent retry")
def test_epp_006_non_retryable_effect_semantics_remain_ineligible() -> None:
    module = importlib.import_module("portable_runtime.workflows.retry_provider_binding")
    for semantics in ("reconcilable", "irreversible-opaque"):
        binding = module.ProviderReplayBinding.example(effect_semantics=semantics)
        eligibility = module.exact_retry_eligibility(binding)
        assert eligibility.allowed is False


@_xfail("B4 exact-provider production: exact provider unavailable must STOP, never fallback")
def test_epp_007_exact_source_provider_unavailable_has_no_fallback() -> None:
    module = importlib.import_module("portable_runtime.workflows.retry_provider_binding")
    source = module.ProviderReplayBinding.example(provider_id="provider:a")
    result = module.select_exact_retry_provider(
        source,
        current_candidates=["provider:b", "provider:c"],
    )
    assert result.provider is None
    assert result.status in {"blocked", "unavailable"}
    assert "fallback" not in result.reason.lower() or "no fallback" in result.reason.lower()


@_xfail("B4 exact-provider production: preferred_provider_ids is not a hard retry pin")
def test_epp_008_routing_preference_cannot_satisfy_exact_pin() -> None:
    module = importlib.import_module("portable_runtime.workflows.retry_provider_binding")
    request = CapabilityRequest(
        id="request:retry",
        capability="example.write",
        preferred_provider_ids=["provider:a"],
    )
    with pytest.raises(ValueError, match="preferred|pin|routing|exact"):
        module.assert_exact_pin_enforced_by_request(request, source_provider_id="provider:a")


@_xfail("B4 exact-provider production: provider replay eligibility is not execution authorization")
def test_epp_009_provider_pin_creates_no_execution_authority() -> None:
    module = importlib.import_module("portable_runtime.workflows.retry_provider_binding")
    fixture = module.ProviderReplayAuditFixture.example()
    binding = fixture.commit_binding()
    assert binding is not None
    assert fixture.qualifications == 0
    assert fixture.authorizations == 0
    assert fixture.invocation_permits == 0
    assert fixture.attempts == 0
    assert fixture.dispatches == 0
    assert fixture.provider_calls == 0


@_xfail("B4 exact-provider production: semantic/provider binding drift invalidates exact retry")
def test_epp_010_provider_semantic_binding_drift_requires_revalidation() -> None:
    module = importlib.import_module("portable_runtime.workflows.retry_provider_binding")
    source = module.ProviderReplayBinding.example(
        provider_id="provider:a",
        semantic_contract_digest="semantic:v1",
    )
    current = module.ProviderReplayBinding.example(
        provider_id="provider:a",
        semantic_contract_digest="semantic:v2",
    )
    with pytest.raises(ValueError, match="semantic|contract|binding|revalidation|drift"):
        module.assert_same_provider_execution_identity(source, current)


@_xfail("B4 exact-provider production: same-looking key across providers has no shared-domain authority")
def test_epp_011_cross_provider_same_key_remains_unsupported() -> None:
    module = importlib.import_module("portable_runtime.workflows.retry_provider_binding")
    with pytest.raises(ValueError, match="cross-provider|domain|idempotency|unsupported"):
        module.authorize_cross_provider_retry(
            source_provider_id="provider:a",
            target_provider_id="provider:b",
            idempotency_key="idem:same-text",
            shared_domain_proof=None,
        )


@_xfail("B4 exact-provider production: replay binding existence does not authorize retry execution")
def test_epp_012_binding_object_is_non_executing_authority() -> None:
    module = importlib.import_module("portable_runtime.workflows.retry_provider_binding")
    fixture = module.ProviderReplayAuditFixture.example()
    binding = fixture.commit_binding()
    assert binding is not None
    assert fixture.retry_materializations == 0
    assert fixture.provider_calls == 0
