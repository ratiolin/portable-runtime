"""B4 durable invocation specification substrate design/counterexamples.

Audit only. No test in this file authorizes retry materialization, provider
execution, Runtime consumption, or serialized invocation-spec authority.
"""

from __future__ import annotations

import importlib
import inspect

import pytest

from portable_runtime.core.boundary_stages import BoundaryStagePlan
from portable_runtime.core.capabilities import CapabilityRequest, ProviderDescriptor
from portable_runtime.core.qualification import InvocationPermit
from portable_runtime.governance.dispatch import GovernanceDispatchCommitter


def _xfail(reason: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(strict=True, reason=reason)


def test_invocation_spec_audit_request_currently_mixes_responsibility_classes() -> None:
    fields = set(CapabilityRequest.model_fields)
    operation = {
        "capability",
        "instruction",
        "input_artifact_refs",
        "parameters",
        "constraints",
        "resource_ref",
        "subject_version_refs",
    }
    replay = {"idempotency_key", "step_key"}
    fresh_execution = {"id", "lease_generation", "lease_owner"}
    orchestration = {"work_id", "run_id"}
    mixed = {"metadata", "effect_class", "preferred_provider_ids", "excluded_provider_ids"}
    assert operation <= fields
    assert replay <= fields
    assert fresh_execution <= fields
    assert orchestration <= fields
    assert mixed <= fields


def test_invocation_spec_audit_permit_snapshot_is_not_durable_dispatch_specification() -> None:
    permit_source = inspect.getsource(InvocationPermit)
    dispatch_source = inspect.getsource(GovernanceDispatchCommitter.commit)
    assert "request_snapshot" in permit_source
    assert "materialize_request" in permit_source
    assert '"invocation_permit_digest"' in dispatch_source
    assert '"qualification_digest"' in dispatch_source
    assert '"governance_snapshot_digest"' in dispatch_source
    assert '"request_snapshot"' not in dispatch_source
    assert "invocation_spec_ref" not in dispatch_source


def test_invocation_spec_audit_existing_execution_boundary_must_be_reused() -> None:
    plan = BoundaryStagePlan()
    assert plan.names.index("qualification") < plan.names.index("authorization")
    assert plan.names.index("authorization") < plan.names.index("precommit")
    assert plan.names.index("precommit") < plan.names.index("invocation")

    boundary_source = inspect.getsource(
        importlib.import_module("portable_runtime.core.boundary").RealityBoundary.execute
    )
    permit = boundary_source.index("InvocationPermit.issue(")
    precommit = boundary_source.index("precommit_execution_records(")
    dispatch = boundary_source.index("GovernanceDispatchCommitter(store).commit(")
    invoke = boundary_source.index("provider.invoke(")
    assert permit < precommit < dispatch < invoke


def test_invocation_spec_audit_p4a_has_no_retry_materializer() -> None:
    module = importlib.import_module("portable_runtime.workflows.recovery_application")
    source = inspect.getsource(module)
    assert not hasattr(module, "prepare_recovery_retry_request")
    assert "InvocationPermit.issue" not in source
    assert "GovernanceDispatchCommitter" not in source
    assert "provider.invoke" not in source
    assert "provider.reconcile" not in source


def test_invocation_spec_audit_provider_has_no_explicit_idempotency_domain() -> None:
    fields = set(ProviderDescriptor.model_fields)
    assert "idempotency_domain" not in fields
    assert "deduplication_domain" not in fields
    assert "replay_domain" not in fields


def test_invocation_spec_audit_runtime_does_not_consume_specification_authority() -> None:
    source = inspect.getsource(importlib.import_module("portable_runtime.core.runtime"))
    assert "DurableInvocationSpecification" not in source
    assert "InvocationSpecificationRecorded" not in source
    assert "invocation_spec_ref" not in source


def test_invocation_spec_audit_qualification_metadata_contains_authority_transport() -> None:
    qualification = importlib.import_module("portable_runtime.core.qualification")
    ref_keys = dict(qualification._REF_KEYS)
    assert {
        "authorization_refs",
        "evidence_refs",
        "verification_refs",
        "checkpoint_refs",
        "decision_refs",
        "qualification_refs",
    } <= set(ref_keys)


@_xfail("B4 invocation-spec production: request_ref alone must never reconstruct operation semantics")
def test_is_001_request_ref_is_not_invocation_specification() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    with pytest.raises(ValueError, match="request_ref|specification|insufficient"):
        module.reconstruct_from_request_ref_only("request:historical")


@_xfail("B4 invocation-spec production: permit/dispatch digest is not reconstructable request authority")
def test_is_002_digest_only_dispatch_cannot_materialize_specification() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    with pytest.raises(ValueError, match="digest|snapshot|specification"):
        module.materialize_from_permit_digest("permit-digest-only")


@_xfail("B4 invocation-spec production: caller memory cannot become durable specification authority")
def test_is_003_in_memory_capability_request_is_not_durable_authority() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    request = CapabilityRequest(id="request:memory", capability="example.write")
    with pytest.raises(ValueError, match="durable|store|authority"):
        module.authorize_retry_from_caller_request(request)


@_xfail("B4 invocation-spec production: same content identity with changed canonical operation semantics must rebound")
def test_is_004_specification_identity_cannot_rebind_operation_semantics() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    fixture = module.InvocationSpecificationAuditFixture.example()
    first = fixture.commit(parameters={"value": 1})
    with pytest.raises(ValueError, match="rebound|identity|semantics"):
        fixture.force_same_identity_commit(parameters={"value": 2}, identity=first.id)


@_xfail("B4 invocation-spec production: durable spec cannot restore old admission/execution authority")
def test_is_005_specification_carries_no_old_permit_lease_or_qualification_authority() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    spec = module.InvocationSpecificationAuditFixture.example().specification()
    forbidden = {
        "request_id",
        "lease_owner",
        "lease_generation",
        "selected_provider_id",
        "qualification_digest",
        "governance_requirement_digest",
        "governance_snapshot_digest",
        "invocation_permit_ref",
        "attempt_ref",
        "dispatch_commit_ref",
    }
    assert forbidden.isdisjoint(set(spec.model_fields))


@_xfail("B4 invocation-spec production: retry must mint fresh request identity while preserving exact spec/replay identity")
def test_is_006_retry_materialization_fresh_request_same_spec_and_idempotency() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    result = module.InvocationSpecificationAuditFixture.materialize_retry(
        source_request_ref="request:old",
        specification_ref="invocation_spec:exact",
        idempotency_key="idem:exact",
    )
    assert result.request.id != "request:old"
    assert result.specification_ref == "invocation_spec:exact"
    assert result.request.idempotency_key == "idem:exact"
    assert result.request.lease_generation != result.source_lease_generation


@_xfail("B4 invocation-spec production: action-critical dispatch must bind exact durable specification identity")
def test_is_007_dispatch_requires_exact_invocation_spec_binding() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    result = module.InvocationSpecificationAuditFixture.dispatch_without_spec_binding()
    assert result.status in {"blocked", "unavailable"}
    assert "invocation_spec" in result.reason


@_xfail("B4 invocation-spec production: specification persistence is never provider execution authority")
def test_is_008_specification_exists_but_provider_call_remains_unauthorized() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    fixture = module.InvocationSpecificationAuditFixture.example()
    spec = fixture.commit()
    assert spec is not None
    assert fixture.provider_calls == 0
    assert fixture.invocation_permits == 0
    assert fixture.new_attempts == 0


@_xfail("B4 invocation-spec production: provider-visible metadata must be explicitly partitioned or fail closed")
def test_is_009_unpartitioned_metadata_cannot_become_retry_semantics() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    with pytest.raises(ValueError, match="metadata|partition|unknown"):
        module.InvocationSpecificationAuditFixture.commit_request(
            CapabilityRequest(
                id="request:metadata",
                capability="example.write",
                metadata={"opaque_provider_semantic": "unclassified"},
            )
        )


@_xfail("B4 invocation-spec production: idempotency key cannot cross an unproven provider/dedup domain")
def test_is_010_retry_idempotency_requires_exact_domain_binding() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    with pytest.raises(ValueError, match="idempotency|dedup|domain|provider"):
        module.InvocationSpecificationAuditFixture.materialize_cross_provider_retry(
            source_provider="provider:a",
            target_provider="provider:b",
            idempotency_key="idem:shared-looking",
        )


@_xfail("B4 invocation-spec production: historical dispatches without spec binding cannot be auto-backfilled")
def test_is_011_historical_dispatch_without_spec_ref_remains_fail_closed() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    with pytest.raises(ValueError, match="historical|backfill|specification"):
        module.InvocationSpecificationAuditFixture.backfill_from_request_and_permit_digest(
            request_ref="request:old",
            permit_digest="digest:old",
        )


@_xfail("P5: serialized invocation-specification authority remains unproven")
def test_is_012_serialized_invocation_specification_authority_is_not_importable() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    store = module.InvocationSpecificationAuditFixture.example_store()
    with pytest.raises(ValueError, match="P5|import|unsupported"):
        store.import_state(
            {
                "event": [
                    {
                        "id": "invocation_spec:imported",
                        "type": "InvocationSpecificationRecorded",
                        "subject_ref": "request:imported",
                        "payload": {"schema": "invocation-specification-v1"},
                    }
                ]
            }
        )
