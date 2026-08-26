"""B4 provider-visible request semantic partition audit/counterexamples.

Audit only. This file authorizes no production invocation specification,
provider semantic contract, retry materializer, Runtime consumption, or
provider/reconciliation call.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect

import pytest

from portable_runtime.core.capabilities import CapabilityRequest, InvocationContext, ProviderDescriptor
from portable_runtime.interfaces.provider import CapabilityProvider
from portable_runtime.protocol.messages import InvokeMessage
from portable_runtime.providers.codex.provider import CodexProvider
from portable_runtime.providers.stdio import StdioJsonlProvider
from portable_runtime.interactions.feishu.provider import FeishuHumanProvider, FeishuNotificationProvider


def _xfail(reason: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(strict=True, reason=reason)


def test_partition_audit_capability_request_allows_provider_visible_extras() -> None:
    assert CapabilityRequest.model_config.get("extra") == "allow"
    value = CapabilityRequest(
        id="request:audit",
        capability="example.write",
        opaque_provider_extension="changes-behavior",
    )
    assert getattr(value, "opaque_provider_extension") == "changes-behavior"


def test_partition_audit_python_provider_receives_full_request_and_context() -> None:
    signature = inspect.signature(CapabilityProvider.invoke)
    assert list(signature.parameters) == ["self", "request", "context"]
    assert {
        "runtime_id",
        "work_id",
        "run_id",
        "metadata",
        "lease_generation",
        "idempotency_key",
    } <= set(InvocationContext.model_fields)


def test_partition_audit_stdio_is_a_narrow_provider_specific_projection() -> None:
    assert set(InvokeMessage.model_fields) == {
        "type",
        "id",
        "capability",
        "work_id",
        "run_id",
        "instruction",
        "input_artifact_refs",
        "parameters",
    }
    assert set(InvokeMessage.model_fields) < set(CapabilityRequest.model_fields) | {"type"}
    source = inspect.getsource(StdioJsonlProvider.invoke)
    for field in (
        "request.id",
        "request.capability",
        "request.work_id",
        "request.run_id",
        "request.instruction",
        "request.input_artifact_refs",
        "request.parameters",
    ):
        assert field in source
    assert "request.metadata" not in source
    assert "request.constraints" not in source
    assert "request.lease_generation" not in source


def test_partition_audit_codex_observes_a_different_projection() -> None:
    source = inspect.getsource(CodexProvider.invoke)
    for field in (
        "request.instruction",
        "request.parameters",
        "request.capability",
        "request.timeout_seconds",
        "request.run_id",
        "request.id",
    ):
        assert field in source
    assert 'request.parameters.get("model"' in source
    assert 'request.parameters.get("repo"' in source


def test_partition_audit_feishu_observes_narrower_request_values() -> None:
    human = inspect.getsource(FeishuHumanProvider.invoke)
    notification = inspect.getsource(FeishuNotificationProvider.invoke)
    assert "request.capability" in human
    assert "request.instruction" in human
    assert "request.instruction" in notification
    assert "request.parameters" not in human
    assert "request.metadata" not in human
    assert "request.parameters" not in notification
    assert "request.metadata" not in notification


def test_partition_audit_provider_descriptor_has_no_semantic_contract_authority() -> None:
    fields = set(ProviderDescriptor.model_fields)
    assert "semantic_contract" not in fields
    assert "semantic_contract_version" not in fields
    assert "semantic_contract_digest" not in fields
    assert "request_semantic_fields" not in fields
    assert "context_semantic_fields" not in fields


def test_partition_audit_no_production_semantic_projection_module_exists() -> None:
    assert importlib.util.find_spec("portable_runtime.workflows.invocation_semantics") is None
    assert importlib.util.find_spec("portable_runtime.core.provider_semantics") is None


@_xfail("B4 provider partition production: unknown provider-visible request extras must fail closed")
def test_pvp_001_unknown_provider_visible_request_extra_is_not_silently_ignored() -> None:
    module = importlib.import_module("portable_runtime.core.provider_semantics")
    request = CapabilityRequest(
        id="request:unknown-extra",
        capability="example.write",
        opaque_provider_extension={"mode": "dangerous-difference"},
    )
    contract = module.ProviderSemanticContract.example_action_critical()
    with pytest.raises(ValueError, match="unknown|unclassified|provider-visible|extension"):
        module.project_request_semantics(request, InvocationContext(runtime_id="runtime"), contract)


@_xfail("B4 provider partition production: arbitrary metadata must be typed/partitioned or fail closed")
def test_pvp_002_unpartitioned_metadata_cannot_enter_or_disappear_from_identity() -> None:
    module = importlib.import_module("portable_runtime.core.provider_semantics")
    request = CapabilityRequest(
        id="request:metadata",
        capability="example.write",
        metadata={"provider_mode": "semantic-but-unclassified"},
    )
    contract = module.ProviderSemanticContract.example_action_critical()
    with pytest.raises(ValueError, match="metadata|partition|unclassified"):
        module.project_request_semantics(request, InvocationContext(runtime_id="runtime"), contract)


@_xfail("B4 provider partition production: typed provider semantic extensions must affect canonical identity")
def test_pvp_003_declared_semantic_extension_changes_canonical_identity() -> None:
    module = importlib.import_module("portable_runtime.core.provider_semantics")
    contract = module.ProviderSemanticContract.example_with_extension(
        extension_name="provider_mode",
        schema={"type": "string"},
    )
    a = CapabilityRequest(
        id="request:a",
        capability="example.write",
        metadata={"provider_mode": "alpha"},
    )
    b = a.model_copy(update={"id": "request:b", "metadata": {"provider_mode": "beta"}})
    pa = module.project_request_semantics(a, InvocationContext(runtime_id="runtime"), contract)
    pb = module.project_request_semantics(b, InvocationContext(runtime_id="runtime"), contract)
    assert pa.identity != pb.identity


@_xfail("B4 provider partition production: qualification transport must never become reusable provider authority")
def test_pvp_004_qualification_refs_are_excluded_and_re_resolved_fresh() -> None:
    module = importlib.import_module("portable_runtime.core.provider_semantics")
    request = CapabilityRequest(
        id="request:qualification",
        capability="example.write",
        metadata={
            "authorization_refs": ["grant:old"],
            "verification_refs": ["verification:old"],
            "qualification_refs": ["qualification:old"],
        },
    )
    contract = module.ProviderSemanticContract.example_action_critical()
    projection = module.project_request_semantics(
        request,
        InvocationContext(runtime_id="runtime"),
        contract,
    )
    serialized = projection.canonical_payload
    assert "grant:old" not in serialized
    assert "verification:old" not in serialized
    assert "qualification:old" not in serialized


@_xfail("B4 provider partition production: runtime-ephemeral authority must be excluded from reusable semantics")
def test_pvp_005_runtime_ephemeral_fields_do_not_define_reusable_operation_identity() -> None:
    module = importlib.import_module("portable_runtime.core.provider_semantics")
    contract = module.ProviderSemanticContract.example_action_critical()
    first = CapabilityRequest(
        id="request:first",
        capability="example.write",
        instruction="same operation",
        lease_generation=1,
        lease_owner="worker:a",
    )
    second = first.model_copy(
        update={
            "id": "request:second",
            "lease_generation": 2,
            "lease_owner": "worker:b",
        }
    )
    a = module.project_request_semantics(first, InvocationContext(runtime_id="runtime"), contract)
    b = module.project_request_semantics(second, InvocationContext(runtime_id="runtime"), contract)
    assert a.identity == b.identity


@_xfail("B4 provider partition production: semantic projection must bind stable contract identity/version")
def test_pvp_006_projection_binds_provider_semantic_contract_identity() -> None:
    module = importlib.import_module("portable_runtime.core.provider_semantics")
    request = CapabilityRequest(id="request:contract", capability="example.write")
    v1 = module.ProviderSemanticContract.example_action_critical(version="1")
    v2 = module.ProviderSemanticContract.example_action_critical(version="2")
    p1 = module.project_request_semantics(request, InvocationContext(runtime_id="runtime"), v1)
    p2 = module.project_request_semantics(request, InvocationContext(runtime_id="runtime"), v2)
    assert p1.contract_digest != p2.contract_digest
    assert p1.identity != p2.identity


@_xfail("B4 provider partition production: transport must preserve every declared provider-semantic value")
def test_pvp_007_transport_missing_declared_semantic_field_fails_closed() -> None:
    module = importlib.import_module("portable_runtime.core.provider_semantics")
    contract = module.ProviderSemanticContract.example_with_request_field("constraints")
    request = CapabilityRequest(
        id="request:transport-gap",
        capability="example.write",
        constraints={"semantic_target": "cluster-a"},
    )
    with pytest.raises(ValueError, match="transport|semantic|constraints|missing"):
        module.assert_transport_complete("stdio-jsonl", request, InvocationContext(runtime_id="runtime"), contract)


@_xfail("B4 provider partition production: provider-visible InvocationContext semantics require explicit classification")
def test_pvp_008_context_semantic_dependency_is_not_silently_ignored() -> None:
    module = importlib.import_module("portable_runtime.core.provider_semantics")
    contract = module.ProviderSemanticContract.example_action_critical()
    context = InvocationContext(
        runtime_id="runtime:a",
        metadata={"provider_tenant": "tenant-a"},
    )
    request = CapabilityRequest(id="request:context", capability="example.write")
    with pytest.raises(ValueError, match="context|metadata|unclassified|provider-visible"):
        module.project_request_semantics(request, context, contract)


@_xfail("B4 provider partition production: fresh request ids cannot silently become operation semantics")
def test_pvp_009_request_id_semantic_dependency_makes_exact_retry_ineligible() -> None:
    module = importlib.import_module("portable_runtime.core.provider_semantics")
    contract = module.ProviderSemanticContract.example_with_request_id_as_semantic()
    eligibility = module.exact_retry_eligibility(contract)
    assert eligibility.allowed is False
    assert "request" in eligibility.reason.lower()
    assert "id" in eligibility.reason.lower()


@_xfail("B4 provider partition production: implementation semantic drift requires contract change/revalidation")
def test_pvp_010_provider_semantic_dependency_drift_cannot_reuse_old_contract_digest() -> None:
    module = importlib.import_module("portable_runtime.core.provider_semantics")
    fixture = module.ProviderSemanticAuditFixture.example()
    old = fixture.freeze_contract(reads={"instruction"})
    with pytest.raises(ValueError, match="drift|contract|semantic|revalidation"):
        fixture.assert_implementation_compatible(old, reads={"instruction", "parameters.model"})


@_xfail("B4 provider partition production: source-code introspection is not semantic authority")
def test_pvp_011_core_canonicalizer_does_not_infer_contract_from_provider_source() -> None:
    module = importlib.import_module("portable_runtime.core.provider_semantics")
    with pytest.raises(ValueError, match="explicit|contract|source|introspection"):
        module.infer_semantic_contract_from_provider(CodexProvider)


@_xfail("B4 provider partition production: semantic contract existence cannot authorize retry or provider execution")
def test_pvp_012_partition_contract_is_non_executing_authority() -> None:
    module = importlib.import_module("portable_runtime.core.provider_semantics")
    fixture = module.ProviderSemanticAuditFixture.example()
    contract = fixture.commit_contract()
    assert contract is not None
    assert fixture.invocation_specifications == 0
    assert fixture.retry_materializations == 0
    assert fixture.invocation_permits == 0
    assert fixture.attempts == 0
    assert fixture.dispatches == 0
    assert fixture.provider_calls == 0
