"""B4 provider-visible request semantic partition audit graduation.

The local semantic-contract/projection substrate now exists.  Transport
completeness remains a later provider/dispatch integration obligation.
"""

from __future__ import annotations

import inspect

import pytest

from portable_runtime.core.capabilities import CapabilityRequest, InvocationContext, ProviderDescriptor
from portable_runtime.core.provider_semantics import (
    ProviderSemanticContract,
    build_provider_replay_binding,
    project_provider_semantics,
)
from portable_runtime.interactions.feishu.provider import FeishuHumanProvider, FeishuNotificationProvider
from portable_runtime.interfaces.provider import CapabilityProvider
from portable_runtime.protocol.messages import InvokeMessage
from portable_runtime.providers.codex.provider import CodexProvider
from portable_runtime.providers.stdio import StdioJsonlProvider


def _contract(*, version: str = "1", **updates: object) -> ProviderSemanticContract:
    values: dict[str, object] = {
        "id": "semantic:provider-a",
        "version": version,
        "provider_id": "provider:a",
        "request_semantic_fields": ("capability", "instruction", "parameters"),
    }
    values.update(updates)
    return ProviderSemanticContract.model_validate(values)


def test_partition_audit_capability_request_allows_provider_visible_extras() -> None:
    assert CapabilityRequest.model_config.get("extra") == "allow"
    value = CapabilityRequest(
        id="request:audit",
        capability="example.write",
        opaque_provider_extension="changes-behavior",
    )
    assert value.opaque_provider_extension == "changes-behavior"


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
    source = inspect.getsource(StdioJsonlProvider.invoke)
    assert "request.parameters" in source
    assert "request.metadata" not in source
    assert "request.constraints" not in source


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


def test_partition_audit_feishu_observes_narrower_request_values() -> None:
    human = inspect.getsource(FeishuHumanProvider.invoke)
    notification = inspect.getsource(FeishuNotificationProvider.invoke)
    assert "request.capability" in human
    assert "request.instruction" in human
    assert "request.instruction" in notification
    assert "request.metadata" not in human
    assert "request.metadata" not in notification


def test_partition_audit_provider_descriptor_does_not_embed_semantic_authority() -> None:
    fields = set(ProviderDescriptor.model_fields)
    assert "semantic_contract" not in fields
    assert "semantic_contract_digest" not in fields
    assert "request_semantic_fields" not in fields


def test_partition_audit_production_projection_is_explicit_and_non_executing() -> None:
    contract = _contract()
    assert contract.provider_id == "provider:a"
    assert contract.digest


def test_pvp_001_unknown_provider_visible_request_extra_is_rejected() -> None:
    request = CapabilityRequest(
        id="request:unknown-extra",
        capability="example.write",
        opaque_provider_extension={"mode": "dangerous-difference"},
    )
    with pytest.raises(ValueError, match="unknown|unclassified|provider-visible|extension"):
        project_provider_semantics(request, InvocationContext(runtime_id="runtime"), _contract())


def test_pvp_002_unpartitioned_metadata_is_rejected() -> None:
    request = CapabilityRequest(
        id="request:metadata",
        capability="example.write",
        metadata={"provider_mode": "semantic-but-unclassified"},
    )
    with pytest.raises(ValueError, match="metadata|unclassified"):
        project_provider_semantics(request, InvocationContext(runtime_id="runtime"), _contract())


def test_pvp_003_typed_semantic_extension_changes_canonical_identity() -> None:
    contract = _contract(request_metadata_extensions={"provider_mode": "str"})
    a = CapabilityRequest(
        id="request:a",
        capability="example.write",
        metadata={"provider_mode": "alpha"},
    )
    b = a.model_copy(update={"id": "request:b", "metadata": {"provider_mode": "beta"}})
    pa = project_provider_semantics(a, InvocationContext(runtime_id="runtime"), contract)
    pb = project_provider_semantics(b, InvocationContext(runtime_id="runtime"), contract)
    assert pa.identity != pb.identity


def test_pvp_004_qualification_refs_are_excluded_from_reusable_semantics() -> None:
    request = CapabilityRequest(
        id="request:qualification",
        capability="example.write",
        metadata={
            "authorization_refs": ["grant:old"],
            "verification_refs": ["verification:old"],
            "qualification_refs": ["qualification:old"],
        },
    )
    projection = project_provider_semantics(
        request,
        InvocationContext(runtime_id="runtime"),
        _contract(),
    )
    assert "grant:old" not in projection.canonical_payload
    assert "verification:old" not in projection.canonical_payload
    assert "qualification:old" not in projection.canonical_payload


def test_pvp_005_runtime_ephemeral_fields_do_not_define_semantic_identity() -> None:
    first = CapabilityRequest(
        id="request:first",
        capability="example.write",
        instruction="same operation",
        lease_generation=1,
        lease_owner="worker:a",
    )
    second = first.model_copy(
        update={"id": "request:second", "lease_generation": 2, "lease_owner": "worker:b"}
    )
    a = project_provider_semantics(first, InvocationContext(runtime_id="runtime"), _contract())
    b = project_provider_semantics(second, InvocationContext(runtime_id="runtime"), _contract())
    assert a.identity == b.identity


def test_pvp_006_projection_binds_semantic_contract_version() -> None:
    request = CapabilityRequest(id="request:contract", capability="example.write")
    p1 = project_provider_semantics(request, InvocationContext(runtime_id="runtime"), _contract(version="1"))
    p2 = project_provider_semantics(request, InvocationContext(runtime_id="runtime"), _contract(version="2"))
    assert p1.contract_digest != p2.contract_digest
    assert p1.identity != p2.identity


@pytest.mark.xfail(
    strict=True,
    reason="dispatch/provider integration: transport completeness remains unimplemented",
)
def test_pvp_007_transport_missing_declared_semantic_field_fails_closed() -> None:
    from portable_runtime.core import provider_semantics

    provider_semantics.assert_transport_complete(  # type: ignore[attr-defined]
        "stdio-jsonl",
        CapabilityRequest(
            id="request:transport-gap",
            capability="example.write",
            constraints={"semantic_target": "cluster-a"},
        ),
        InvocationContext(runtime_id="runtime"),
        _contract(request_semantic_fields=("capability", "constraints")),
    )


def test_pvp_008_context_metadata_dependency_requires_explicit_classification() -> None:
    context = InvocationContext(runtime_id="runtime:a", metadata={"provider_tenant": "tenant-a"})
    request = CapabilityRequest(id="request:context", capability="example.write")
    with pytest.raises(ValueError, match="context.*metadata|unclassified"):
        project_provider_semantics(request, context, _contract())


def test_pvp_009_request_id_cannot_be_reclassified_as_reusable_semantics() -> None:
    with pytest.raises(ValueError, match="runtime/authority request fields"):
        _contract(request_semantic_fields=("capability", "id"))


def test_pvp_010_contract_drift_changes_provider_replay_binding() -> None:
    descriptor = ProviderDescriptor(
        id="provider:a",
        name="provider-a",
        version="1",
        capabilities=["example.write"],
    )
    first = build_provider_replay_binding(
        descriptor,
        _contract(version="1"),
        provider_binding_id="configured-provider-a",
    )
    second = build_provider_replay_binding(
        descriptor,
        _contract(version="2"),
        provider_binding_id="configured-provider-a",
    )
    assert first.binding_digest != second.binding_digest


def test_pvp_011_source_code_introspection_is_not_semantic_authority() -> None:
    from portable_runtime.core import provider_semantics

    assert not hasattr(provider_semantics, "infer_semantic_contract_from_provider")


def test_pvp_012_semantic_contract_is_non_executing_authority() -> None:
    from portable_runtime.core import provider_semantics

    contract = _contract()
    assert contract.digest
    assert not hasattr(provider_semantics, "materialize_retry")
    assert not hasattr(provider_semantics, "issue_invocation_permit")
    assert not hasattr(provider_semantics, "invoke_provider")
