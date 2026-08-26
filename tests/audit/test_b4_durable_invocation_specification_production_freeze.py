"""B4 DurableInvocationSpecification production counterexample freeze.

Audit only. The next production slice may implement local semantic projection
and durable specification authority, but this file authorizes no Runtime
consumption, dispatch integration, retry materialization, or provider call.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect

import pytest

from portable_runtime.core.capabilities import CapabilityRequest, InvocationContext, ProviderDescriptor
from portable_runtime.governance.dispatch import GovernanceDispatchCommitter
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore


def _xfail(reason: str) -> pytest.MarkDecorator:
    return pytest.mark.xfail(strict=True, reason=reason)


def test_dis_freeze_no_production_specification_module_exists_yet() -> None:
    assert importlib.util.find_spec("portable_runtime.workflows.invocation_specification") is None
    assert importlib.util.find_spec("portable_runtime.core.provider_semantics") is None


def test_dis_freeze_stores_do_not_own_specification_commit_yet() -> None:
    assert not hasattr(InMemoryStateStore, "commit_invocation_specification")
    assert not hasattr(SQLiteStateStore, "commit_invocation_specification")


def test_dis_freeze_dispatch_has_no_specification_binding_yet() -> None:
    source = inspect.getsource(GovernanceDispatchCommitter.commit)
    assert "invocation_spec_ref" not in source
    assert "InvocationSpecificationRecorded" not in source


def test_dis_freeze_runtime_has_no_specification_consumption() -> None:
    source = inspect.getsource(importlib.import_module("portable_runtime.core.runtime"))
    assert "DurableInvocationSpecification" not in source
    assert "commit_invocation_specification" not in source
    assert "invocation_spec_ref" not in source


def test_dis_freeze_request_and_context_still_have_mixed_surfaces() -> None:
    request_fields = set(CapabilityRequest.model_fields)
    context_fields = set(InvocationContext.model_fields)
    assert {"metadata", "lease_generation", "idempotency_key"} <= request_fields
    assert {"metadata", "lease_generation", "idempotency_key"} <= context_fields
    assert CapabilityRequest.model_config.get("extra") == "allow"


def test_dis_freeze_provider_descriptor_still_lacks_stable_replay_binding() -> None:
    fields = set(ProviderDescriptor.model_fields)
    assert "version" in fields
    assert "provider_binding_id" not in fields
    assert "semantic_contract_digest" not in fields
    assert "idempotency_domain" not in fields


@_xfail("DIS production: action-critical capture requires explicit provider semantic contract")
def test_dis_001_explicit_provider_semantic_contract_required() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    request = CapabilityRequest(id="request:no-contract", capability="example.write", effect_class="write-remote")
    context = InvocationContext(runtime_id="runtime")
    with pytest.raises(ValueError, match="semantic|contract|required"):
        module.prepare_invocation_specification(request, context, provider_descriptor=None, semantic_contract=None)


@_xfail("DIS production: unknown provider-visible extensions must prevent specification capture")
def test_dis_002_unknown_provider_visible_extension_fails_closed() -> None:
    semantics = importlib.import_module("portable_runtime.core.provider_semantics")
    request = CapabilityRequest(
        id="request:unknown",
        capability="example.write",
        opaque_provider_extension={"meaning": "unclassified"},
    )
    contract = semantics.ProviderSemanticContract.example_action_critical()
    with pytest.raises(ValueError, match="unknown|unclassified|extension|provider-visible"):
        semantics.project_provider_semantics(request, InvocationContext(runtime_id="runtime"), contract)


@_xfail("DIS production: runtime-ephemeral authority must not define reusable semantic identity")
def test_dis_003_runtime_ephemeral_changes_do_not_change_semantic_identity() -> None:
    semantics = importlib.import_module("portable_runtime.core.provider_semantics")
    contract = semantics.ProviderSemanticContract.example_action_critical()
    first = CapabilityRequest(
        id="request:one",
        capability="example.write",
        instruction="same operation",
        lease_generation=1,
        lease_owner="worker:a",
        metadata={"authorization_refs": ["grant:old"]},
    )
    second = first.model_copy(
        update={
            "id": "request:two",
            "lease_generation": 2,
            "lease_owner": "worker:b",
            "metadata": {"authorization_refs": ["grant:new"]},
        }
    )
    a = semantics.project_provider_semantics(first, InvocationContext(runtime_id="runtime"), contract)
    b = semantics.project_provider_semantics(second, InvocationContext(runtime_id="runtime"), contract)
    assert a.identity == b.identity


@_xfail("DIS production: declared provider-semantic changes must change canonical identity")
def test_dis_004_semantic_change_changes_identity() -> None:
    semantics = importlib.import_module("portable_runtime.core.provider_semantics")
    contract = semantics.ProviderSemanticContract.example_action_critical()
    first = CapabilityRequest(id="request:a", capability="example.write", instruction="write A")
    second = CapabilityRequest(id="request:b", capability="example.write", instruction="write B")
    a = semantics.project_provider_semantics(first, InvocationContext(runtime_id="runtime"), contract)
    b = semantics.project_provider_semantics(second, InvocationContext(runtime_id="runtime"), contract)
    assert a.identity != b.identity


@_xfail("DIS production: semantic-contract drift cannot reinterpret the same specification identity")
def test_dis_005_contract_drift_changes_identity() -> None:
    semantics = importlib.import_module("portable_runtime.core.provider_semantics")
    request = CapabilityRequest(id="request:contract", capability="example.write", instruction="same")
    v1 = semantics.ProviderSemanticContract.example_action_critical(version="1")
    v2 = semantics.ProviderSemanticContract.example_action_critical(version="2")
    a = semantics.project_provider_semantics(request, InvocationContext(runtime_id="runtime"), v1)
    b = semantics.project_provider_semantics(request, InvocationContext(runtime_id="runtime"), v2)
    assert a.contract_digest != b.contract_digest
    assert a.identity != b.identity


@_xfail("DIS production: provider-id string alone is insufficient replay binding")
def test_dis_006_provider_binding_must_be_stronger_than_provider_id() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    descriptor = ProviderDescriptor(id="provider:a", name="a", version="1", capabilities=["example.write"])
    with pytest.raises(ValueError, match="provider|binding|stable|identity"):
        module.provider_replay_binding(descriptor, semantic_contract_digest="semantic:v1", binding_id=None)


@_xfail("DIS production: retry-eligible side effect specification retains exact idempotency identity")
def test_dis_007_side_effect_spec_requires_idempotency_identity() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    fixture = module.InvocationSpecificationAuditFixture.example()
    with pytest.raises(ValueError, match="idempotency|replay|identity"):
        fixture.capture(effect_semantics="idempotent", idempotency_key=None)


@_xfail("DIS production: identical semantic/provenance input deterministically replays same spec")
def test_dis_008_same_input_replays_same_specification() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    fixture = module.InvocationSpecificationAuditFixture.example()
    first = fixture.commit()
    second = fixture.commit()
    assert first == second
    assert first.id == second.id


@_xfail("DIS production: same specification identity cannot be rebound to changed immutable semantics")
def test_dis_009_specification_rebound_is_rejected() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    fixture = module.InvocationSpecificationAuditFixture.example()
    first = fixture.commit(instruction="operation A")
    with pytest.raises(ValueError, match="rebound|identity|semantics|immutable"):
        fixture.force_same_identity_commit(identity=first.id, instruction="operation B")


@_xfail("DIS production: Memory specification authority is store-owned")
def test_dis_010_memory_commit_owns_authority_and_direct_event_append_fails() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    store = InMemoryStateStore()
    fixture = module.InvocationSpecificationAuditFixture.for_store(store)
    spec = fixture.commit()
    assert spec is not None
    with pytest.raises(ValueError, match="commit_invocation_specification|authority|direct"):
        store.append_event(fixture.forged_event_for(spec))


@_xfail("DIS production: SQLite specification survives close/reopen and replays deterministically")
def test_dis_011_sqlite_close_reopen_replays_same_specification(tmp_path) -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    path = tmp_path / "invocation-spec.sqlite"
    first_store = SQLiteStateStore(str(path))
    fixture = module.InvocationSpecificationAuditFixture.for_store(first_store)
    first = fixture.commit()
    first_store.close()
    second_store = SQLiteStateStore(str(path))
    replay = module.InvocationSpecificationAuditFixture.for_store(second_store).replay(first.id)
    assert replay == first
    second_store.close()


@_xfail("P5: serialized invocation specification authority remains fail closed")
def test_dis_012_serialized_specification_import_is_unsupported() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    store = InMemoryStateStore()
    event = module.InvocationSpecificationAuditFixture.example().forged_serialized_event()
    with pytest.raises(ValueError, match="P5|import|unsupported|invocation specification"):
        store.import_state({"event": [event]})


@_xfail("DIS production: initial capture binds exact source request identity")
def test_dis_013_specification_binds_source_request_and_rejects_request_ref_only_reconstruction() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    fixture = module.InvocationSpecificationAuditFixture.example(source_request_id="request:source")
    spec = fixture.commit()
    assert spec.source_request_ref == "request:source"
    with pytest.raises(ValueError, match="historical|request_ref|insufficient|specification"):
        module.reconstruct_from_request_ref_only("request:source")


@_xfail("DIS production: specification capture remains non-executing authority")
def test_dis_014_specification_capture_creates_no_execution_authority() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    fixture = module.InvocationSpecificationAuditFixture.example()
    spec = fixture.commit()
    assert spec is not None
    assert fixture.qualifications == 0
    assert fixture.authorizations == 0
    assert fixture.invocation_permits == 0
    assert fixture.attempts == 0
    assert fixture.dispatches == 0
    assert fixture.provider_calls == 0


@_xfail("DIS integration blocker: action-critical dispatch must bind exact invocation_spec_ref")
def test_dis_015_dispatch_requires_exact_specification_binding() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    result = module.InvocationSpecificationAuditFixture.dispatch_without_spec_binding()
    assert result.status in {"blocked", "unavailable"}
    assert "invocation_spec" in result.reason


@_xfail("DIS production: historical request/dispatch history cannot be backfilled into authoritative spec")
def test_dis_016_historical_specification_backfill_remains_forbidden() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    with pytest.raises(ValueError, match="historical|backfill|unsupported|authoritative"):
        module.backfill_historical_specification(
            request_ref="request:old",
            dispatch_ref="dispatch:old",
            current_provider_binding="provider-binding:current",
        )


@_xfail("DIS production: provider replay binding drift cannot silently replay old specification")
def test_dis_017_provider_binding_drift_is_rejected() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    fixture = module.InvocationSpecificationAuditFixture.example(provider_binding="provider-binding:v1")
    first = fixture.commit()
    with pytest.raises(ValueError, match="provider|binding|drift|rebound"):
        fixture.replay_with_provider_binding(first.id, "provider-binding:v2")


@_xfail("DIS minimal production: no API may directly materialize authorized retry execution")
def test_dis_018_retry_materialization_remains_absent() -> None:
    module = importlib.import_module("portable_runtime.workflows.invocation_specification")
    assert not hasattr(module, "materialize_authorized_retry")
    assert not hasattr(module, "consume_recovery_application")
    assert not hasattr(module, "issue_retry_permit")
