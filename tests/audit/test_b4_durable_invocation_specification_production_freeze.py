"""B4 DurableInvocationSpecification production graduation.

Local semantic projection and durable specification authority are production
conformance. Dispatch/spec integration remains a strict later blocker.
"""

from __future__ import annotations

import hashlib
import inspect
import json

import pytest
from pydantic import ValidationError

from portable_runtime.core.capabilities import CapabilityRequest, InvocationContext, ProviderDescriptor
from portable_runtime.core.models import Event
from portable_runtime.core.provider_semantics import (
    ProviderSemanticContract,
    build_provider_replay_binding,
    project_provider_semantics,
)
from portable_runtime.governance.dispatch import GovernanceDispatchCommitter
from portable_runtime.stores.invocation_specification import (
    InvocationSpecificationInMemoryStateStore,
    InvocationSpecificationSQLiteStateStore,
)
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore
from portable_runtime.workflows.invocation_specification import (
    DurableInvocationSpecification,
    InvocationSpecificationCommitRequest,
    build_invocation_specification,
    invocation_specification_event,
    invocation_specification_from_event,
    reject_historical_specification_backfill,
)


def _contract(*, provider_id: str = "provider:a", version: str = "1") -> ProviderSemanticContract:
    return ProviderSemanticContract(
        id=f"semantic:{provider_id}",
        version=version,
        provider_id=provider_id,
        request_semantic_fields=("capability", "instruction", "parameters"),
    )


def _descriptor(
    *,
    provider_id: str = "provider:a",
    version: str = "1",
    effect_semantics: str = "pure",
) -> ProviderDescriptor:
    return ProviderDescriptor(
        id=provider_id,
        name=provider_id,
        version=version,
        capabilities=["example.write"],
        effect_semantics=effect_semantics,
        side_effect_class=effect_semantics,
    )


def _request(
    *,
    request_id: str = "request:source",
    instruction: str = "perform operation",
    idempotency_key: str | None = None,
    metadata: dict[str, object] | None = None,
    **extra: object,
) -> CapabilityRequest:
    return CapabilityRequest(
        id=request_id,
        capability="example.write",
        work_id="work:a",
        run_id="run:a",
        instruction=instruction,
        idempotency_key=idempotency_key,
        metadata=dict(metadata or {}),
        **extra,
    )


def _context() -> InvocationContext:
    return InvocationContext(runtime_id="runtime:a", work_id="work:a", run_id="run:a")


def _commit_request(
    *,
    request: CapabilityRequest | None = None,
    descriptor: ProviderDescriptor | None = None,
    contract: ProviderSemanticContract | None = None,
    provider_binding_id: str = "configured-provider-a:v1",
) -> InvocationSpecificationCommitRequest:
    return InvocationSpecificationCommitRequest(
        request=request or _request(),
        context=_context(),
        provider_descriptor=descriptor or _descriptor(),
        semantic_contract=contract or _contract(),
        provider_binding_id=provider_binding_id,
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _projection_identity(canonical_payload: str) -> str:
    return f"provider_semantics_{hashlib.sha256(canonical_payload.encode()).hexdigest()}"


def test_dis_production_is_opt_in_and_runtime_baseline_is_not_expanded() -> None:
    assert not hasattr(InMemoryStateStore, "commit_invocation_specification")
    assert not hasattr(SQLiteStateStore, "commit_invocation_specification")
    assert hasattr(InvocationSpecificationInMemoryStateStore, "commit_invocation_specification")
    assert hasattr(InvocationSpecificationSQLiteStateStore, "commit_invocation_specification")


def test_dis_dispatch_and_runtime_integration_remain_absent() -> None:
    source = inspect.getsource(GovernanceDispatchCommitter.commit)
    assert "invocation_spec_ref" not in source
    assert "InvocationSpecificationRecorded" not in source

    from portable_runtime.core import runtime

    runtime_source = inspect.getsource(runtime)
    assert "DurableInvocationSpecification" not in runtime_source
    assert "commit_invocation_specification" not in runtime_source


def test_dis_001_explicit_provider_semantic_contract_required() -> None:
    raw = _commit_request().model_dump(mode="python")
    raw.pop("semantic_contract")
    with pytest.raises(ValidationError, match="semantic_contract"):
        InvocationSpecificationCommitRequest.model_validate(raw)


def test_dis_002_unknown_provider_visible_extension_fails_closed() -> None:
    request = _request(opaque_provider_extension={"meaning": "unclassified"})
    with pytest.raises(ValueError, match="unknown|unclassified|extension|provider-visible"):
        build_invocation_specification(
            request,
            _context(),
            _descriptor(),
            _contract(),
            provider_binding_id="configured-provider-a:v1",
        )


def test_dis_003_runtime_authority_is_excluded_from_reusable_semantic_identity() -> None:
    first = _request(
        request_id="request:one",
        instruction="same operation",
        metadata={"authorization_refs": ["grant:old"]},
        lease_generation=1,
        lease_owner="worker:a",
    )
    second = _request(
        request_id="request:two",
        instruction="same operation",
        metadata={"authorization_refs": ["grant:new"]},
        lease_generation=2,
        lease_owner="worker:b",
    )
    a = build_invocation_specification(
        first, _context(), _descriptor(), _contract(), provider_binding_id="configured-provider-a:v1"
    )
    b = build_invocation_specification(
        second, _context(), _descriptor(), _contract(), provider_binding_id="configured-provider-a:v1"
    )
    assert a.semantic_identity == b.semantic_identity
    assert a.id != b.id  # source provenance remains a distinct durable fact


def test_dis_004_semantic_change_changes_identity() -> None:
    a = build_invocation_specification(
        _request(request_id="request:a", instruction="operation A"),
        _context(),
        _descriptor(),
        _contract(),
        provider_binding_id="configured-provider-a:v1",
    )
    b = build_invocation_specification(
        _request(request_id="request:b", instruction="operation B"),
        _context(),
        _descriptor(),
        _contract(),
        provider_binding_id="configured-provider-a:v1",
    )
    assert a.semantic_identity != b.semantic_identity


def test_dis_005_contract_drift_changes_semantic_and_specification_identity() -> None:
    request = _request()
    a = build_invocation_specification(
        request, _context(), _descriptor(), _contract(version="1"), provider_binding_id="configured-provider-a:v1"
    )
    b = build_invocation_specification(
        request, _context(), _descriptor(), _contract(version="2"), provider_binding_id="configured-provider-a:v1"
    )
    assert a.semantic_contract_digest != b.semantic_contract_digest
    assert a.semantic_identity != b.semantic_identity
    assert a.id != b.id


def test_dis_006_provider_binding_representation_is_stronger_than_provider_id() -> None:
    with pytest.raises(ValueError, match="stronger than provider id"):
        build_provider_replay_binding(
            _descriptor(),
            _contract(),
            provider_binding_id="provider:a",
        )
    binding = build_provider_replay_binding(
        _descriptor(),
        _contract(),
        provider_binding_id="configured-provider-a:v1",
    )
    assert binding.provider_binding_id != binding.provider_id
    assert binding.binding_digest


def test_dis_007_retry_eligible_spec_requires_exact_idempotency_identity() -> None:
    descriptor = _descriptor(effect_semantics="idempotent")
    with pytest.raises(ValueError, match="idempotency identity"):
        build_invocation_specification(
            _request(idempotency_key=None),
            _context(),
            descriptor,
            _contract(),
            provider_binding_id="configured-provider-a:v1",
        )
    spec = build_invocation_specification(
        _request(idempotency_key="effect:key:a"),
        _context(),
        descriptor,
        _contract(),
        provider_binding_id="configured-provider-a:v1",
    )
    assert spec.idempotency_key == "effect:key:a"


def test_dis_008_memory_same_input_replays_same_specification() -> None:
    store = InvocationSpecificationInMemoryStateStore()
    request = _commit_request()
    first = store.commit_invocation_specification(request)
    second = store.commit_invocation_specification(request)
    assert second == first
    assert second.id == first.id


def test_dis_009_same_spec_identity_cannot_rebind_changed_semantics() -> None:
    original = build_invocation_specification(
        _request(instruction="operation A"),
        _context(),
        _descriptor(),
        _contract(),
        provider_binding_id="configured-provider-a:v1",
    )
    changed_projection = project_provider_semantics(
        _request(instruction="operation B"),
        _context(),
        _contract(),
    )
    event_raw = invocation_specification_event(original).model_dump(mode="python")
    spec_raw = event_raw["payload"]["specification"]
    spec_raw["semantic_identity"] = changed_projection.identity
    spec_raw["canonical_semantic_payload"] = changed_projection.canonical_payload
    forged = Event.model_validate(event_raw)
    with pytest.raises(ValueError, match="deterministic identity rebound"):
        invocation_specification_from_event(forged)


def test_dis_010_memory_store_owns_authority_and_direct_event_append_fails() -> None:
    store = InvocationSpecificationInMemoryStateStore()
    spec = build_invocation_specification(
        _request(), _context(), _descriptor(), _contract(), provider_binding_id="configured-provider-a:v1"
    )
    with pytest.raises(ValueError, match="commit_invocation_specification"):
        store.append_event(invocation_specification_event(spec))
    committed = store.commit_invocation_specification(_commit_request())
    assert store.get_invocation_specification(committed.id) == committed


def test_dis_011_sqlite_close_reopen_replays_same_specification(tmp_path) -> None:
    path = tmp_path / "invocation-spec.sqlite"
    request = _commit_request()
    first_store = InvocationSpecificationSQLiteStateStore(path)
    first = first_store.commit_invocation_specification(request)
    first_store.close()

    second_store = InvocationSpecificationSQLiteStateStore(path)
    assert second_store.get_invocation_specification(first.id) == first
    assert second_store.commit_invocation_specification(request) == first
    second_store.close()


def test_dis_012_serialized_specification_import_is_closed() -> None:
    store = InvocationSpecificationInMemoryStateStore()
    spec = build_invocation_specification(
        _request(), _context(), _descriptor(), _contract(), provider_binding_id="configured-provider-a:v1"
    )
    event = invocation_specification_event(spec)
    with pytest.raises(ValueError, match="P5.*unsupported"):
        store.import_state({"event": [event.model_dump(mode="json")]})


def test_dis_013_specification_binds_exact_source_request() -> None:
    spec = build_invocation_specification(
        _request(request_id="request:source"),
        _context(),
        _descriptor(),
        _contract(),
        provider_binding_id="configured-provider-a:v1",
    )
    assert spec.source_request_ref == "request:source"


def test_dis_014_specification_capture_is_non_executing() -> None:
    store = InvocationSpecificationInMemoryStateStore()
    spec = store.commit_invocation_specification(_commit_request())
    state = store.export_state()
    assert spec is not None
    assert len(state["event"]) == 1
    assert state["attempt"] == []
    assert state["action"] == []


@pytest.mark.xfail(
    strict=True,
    reason="dispatch integration blocker: action-critical dispatch does not yet bind invocation_spec_ref",
)
def test_dis_015_dispatch_requires_exact_specification_binding() -> None:
    source = inspect.getsource(GovernanceDispatchCommitter.commit)
    assert "invocation_spec_ref" in source


def test_dis_016_historical_specification_backfill_is_permanently_closed() -> None:
    with pytest.raises(ValueError, match="historical.*backfill.*unsupported"):
        reject_historical_specification_backfill(
            request_ref="request:old",
            dispatch_ref="dispatch:old",
        )


def test_dis_017_provider_binding_drift_cannot_replay_old_specification_identity() -> None:
    descriptor = _descriptor()
    contract = _contract()
    original = build_invocation_specification(
        _request(),
        _context(),
        descriptor,
        contract,
        provider_binding_id="configured-provider-a:v1",
    )
    drifted_binding = build_provider_replay_binding(
        descriptor,
        contract,
        provider_binding_id="configured-provider-a:v2",
    )
    event_raw = invocation_specification_event(original).model_dump(mode="python")
    event_raw["payload"]["specification"]["provider_binding"] = drifted_binding.model_dump(mode="python")
    forged = Event.model_validate(event_raw)
    with pytest.raises(ValueError, match="deterministic identity rebound"):
        invocation_specification_from_event(forged)


def test_dis_018_retry_materialization_api_remains_absent() -> None:
    from portable_runtime.workflows import invocation_specification

    assert not hasattr(invocation_specification, "materialize_authorized_retry")
    assert not hasattr(invocation_specification, "consume_recovery_application")
    assert not hasattr(invocation_specification, "issue_retry_permit")


def test_dis_integrity_semantic_payload_recomputes_semantic_identity_at_decode_boundary() -> None:
    original = build_invocation_specification(
        _request(), _context(), _descriptor(), _contract(), provider_binding_id="configured-provider-a:v1"
    )
    raw = invocation_specification_event(original).model_dump(mode="python")
    canonical = json.loads(raw["payload"]["specification"]["canonical_semantic_payload"])
    canonical["request"]["instruction"] = "tampered operation"
    raw["payload"]["specification"]["canonical_semantic_payload"] = _canonical_json(canonical)
    forged = Event.model_validate(raw)
    with pytest.raises(ValueError, match="projection identity mismatch"):
        invocation_specification_from_event(forged)


def test_dis_integrity_projection_spec_and_binding_contracts_must_be_one_chain() -> None:
    descriptor = _descriptor()
    contract_a = _contract(version="1")
    contract_b = _contract(version="2")
    projection_b = project_provider_semantics(_request(), _context(), contract_b)
    binding_a = build_provider_replay_binding(
        descriptor,
        contract_a,
        provider_binding_id="configured-provider-a:v1",
    )
    with pytest.raises(ValueError, match="semantic contract.*provider replay binding"):
        DurableInvocationSpecification(
            id="invocation_spec:forged",
            semantic_identity=projection_b.identity,
            canonical_semantic_payload=projection_b.canonical_payload,
            semantic_contract_digest=projection_b.contract_digest,
            provider_binding=binding_a,
            source_request_ref="request:source",
            source_work_ref="work:a",
            source_run_ref="run:a",
            effect_semantics="pure",
        )


def test_dis_integrity_projection_provider_must_match_provider_binding_provider() -> None:
    contract_a = _contract()
    binding_a = build_provider_replay_binding(
        _descriptor(),
        contract_a,
        provider_binding_id="configured-provider-a:v1",
    )
    payload = {
        "schema": "provider-semantic-projection-v1",
        "provider_id": "provider:b",
        "contract_digest": contract_a.digest,
    }
    canonical = _canonical_json(payload)
    with pytest.raises(ValueError, match="semantic provider.*provider replay binding"):
        DurableInvocationSpecification(
            id="invocation_spec:forged",
            semantic_identity=_projection_identity(canonical),
            canonical_semantic_payload=canonical,
            semantic_contract_digest=contract_a.digest,
            provider_binding=binding_a,
            source_request_ref="request:source",
            effect_semantics="pure",
        )
