"""Authoritative RealityBoundary conformance (E001-E020).

These tests deliberately exercise the only supported side-effect path:

    CapabilityService.invoke -> RealityBoundary.execute -> ProviderRegistry
    -> CountingProvider.invoke

The negative cases assert both the stable boundary error code and that the
provider was never invoked. Helper-level checks (``is_authorized_for`` or
``validate_fencing``) are intentionally not used as conformance evidence.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from portable_runtime.core.boundary import RealityBoundary
from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    InvocationContext,
    ProviderDescriptor,
    ProviderHealth,
)
from portable_runtime.core.knowledge import classify
from portable_runtime.core.models import Checkpoint, KnowledgeItem, Run, Work, new_id
from portable_runtime.core.policies import PolicyDecision, approval_obligation
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.core.router import CapabilityService, ConstraintRouter
from portable_runtime.records.authorization import AuthorizationGrant, create_grant_for_approval
from portable_runtime.records.models import BaseRecord
from portable_runtime.records.open_validation import ClosedVerificationResult
from portable_runtime.records.relations import RecordRelation
from portable_runtime.stores.memory import InMemoryStateStore


InvokeHook = Callable[[CapabilityRequest, InvocationContext], Awaitable[None] | None]


class CountingProvider:
    """Provider used by every E-series test; its counter is the reality oracle."""

    def __init__(
        self,
        *,
        provider_id: str = "counter",
        capabilities: list[str] | None = None,
        constraints: dict[str, Any] | None = None,
        side_effect_class: str = "reconcilable",
        on_invoke: InvokeHook | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.invoke_count = 0
        self.on_invoke = on_invoke
        self._descriptor = ProviderDescriptor(
            id=provider_id,
            name=provider_id,
            version="1.0.0",
            capabilities=capabilities
            or [
                "test.side_effect",
                "test.deploy",
                "test.read",
                "test.write_remote",
            ],
            constraints=constraints or {},
            effect_semantics=side_effect_class,  # type: ignore[arg-type]
            side_effect_class=side_effect_class,  # type: ignore[arg-type]
            reversibility="compensatable" if side_effect_class != "pure" else "reversible",
            provider_family="counter-family",
            credential_domain="counter-credentials",
            evaluation_domain="counter-evaluation",
        )

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.provider_id, available=True)

    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        self.invoke_count += 1
        if self.on_invoke is not None:
            outcome = self.on_invoke(request, context)
            if inspect.isawaitable(outcome):
                await outcome
        return CapabilityResult(
            request_id=request.id,
            provider_id=self.provider_id,
            status="succeeded",
        )

    async def cancel(self, request_id: str) -> None:
        return None

    async def reconcile(self, request_id: str) -> CapabilityResult | None:
        return None


class ExplodingAuthorizationStore(InMemoryStateStore):
    def list_authorizations(self) -> list[Any]:
        raise RuntimeError("authorization backend unavailable")


class FailingPrecommitStore(InMemoryStateStore):
    def save_step(self, value: Any) -> None:
        raise RuntimeError("cannot persist execution intent")


class FailingResultCommitStore(InMemoryStateStore):
    def save_outcome(self, value: Any) -> None:
        raise RuntimeError("result journal unavailable")


class ExplodingPolicy:
    async def evaluate(self, context: Any) -> PolicyDecision:
        raise RuntimeError("policy engine unavailable")


class RequiringPolicy:
    async def evaluate(self, context: Any) -> PolicyDecision:
        return PolicyDecision(
            disposition="require",
            obligations=[approval_obligation(required_role="owner")],
            reason="approval proof required",
        )


class ExplodingReliability:
    def can_execute(self, *, side_effect: bool = False) -> bool:
        raise RuntimeError("reliability controller unavailable")

    def record_action(self, *, side_effect: bool = False) -> None:
        return None


class ExhaustedReliability:
    def can_execute(self, *, side_effect: bool = False) -> bool:
        return False

    def record_action(self, *, side_effect: bool = False) -> None:
        return None


class ClosedCircuit:
    def allow(self) -> bool:
        return False

    def record_success(self) -> None:
        return None

    def record_failure(self) -> None:
        return None


@pytest.fixture
def authoritative_runtime() -> dict[str, Any]:
    """Build the same registry/boundary/service path used by every E test."""
    store = InMemoryStateStore()
    provider = CountingProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    routing = ConstraintRouter(registry=registry)
    boundary = RealityBoundary(store=store, registry=registry, routing=routing)
    service = CapabilityService(registry=registry, boundary=boundary, store=store)
    return {
        "store": store,
        "provider": provider,
        "registry": registry,
        "routing": routing,
        "boundary": boundary,
        "service": service,
    }


def _request(capability: str = "test.side_effect", **kwargs: Any) -> CapabilityRequest:
    defaults: dict[str, Any] = {
        "id": new_id("request"),
        "capability": capability,
        "effect_class": "write-remote" if capability != "test.read" else "read",
        "subject_version_refs": ["patch:v1"],
    }
    defaults.update(kwargs)
    return CapabilityRequest(**defaults)


def _seed_work_run(store: InMemoryStateStore) -> tuple[Work, Run]:
    work = Work(
        id=new_id("work"),
        title="authoritative conformance",
        kind="generic-task",
        metadata={
            "purpose": "exercise the authoritative boundary",
            "execution_boundary": "provider",
            "result_confirmed": True,
            "candidate": ["counter"],
            "reviewed": True,
            # Qualification facts are stored below and carried only by refs.
            "procedure_proof_refs": [],
        },
    )
    run = Run(id=new_id("run"), work_id=work.id, status="running")
    store.save_work(work)
    store.save_run(run)

    failure_stop = BaseRecord(
        record_type="Policy",
        lifecycle_status="candidate",
        metadata={"qualification_kind": "failure-stop", "condition": "provider failure"},
    )
    evidence = BaseRecord(
        record_type="EvidenceArtifact",
        lifecycle_status="current",
        metadata={"qualification_kind": "evidence", "uri": "evidence:conformance"},
    )
    verification = BaseRecord(
        record_type="Assertion",
        lifecycle_status="current",
        epistemic_status="supported",
        metadata={
            "qualification_kind": "verification",
            "result": "pass",
            "target_refs": [work.id],
        },
    )
    decision = BaseRecord(
        record_type="Decision",
        lifecycle_status="current",
        metadata={"qualification_kind": "decision"},
    )
    relation = RecordRelation(relation_type="records", subject_ref=work.id, object_ref=evidence.id)
    verification_relation = RecordRelation(
        relation_type="validated-under", subject_ref=work.id, object_ref=verification.id
    )
    for record in (failure_stop, evidence, verification, decision):
        store.save_record(record)
    store.save_relation(relation)
    store.save_relation(verification_relation)
    checkpoint = Checkpoint(run_id=run.id, step_id=None)
    store.save_checkpoint(checkpoint)
    work.metadata["procedure_proof_refs"] = [
        {"id": failure_stop.id, "kind": "failure-stop"},
        {"id": evidence.id, "kind": "evidence"},
        {"id": verification.id, "kind": "verification"},
        {"id": decision.id, "kind": "decision"},
    ]
    work.metadata["relation_refs"] = [relation.id, verification_relation.id]
    work.metadata["checkpoint_refs"] = [checkpoint.id]
    store.save_work(work)
    return work, run


def _grant(
    store: InMemoryStateStore,
    *,
    capability: str,
    actor: str = "agent:runner",
    effect_ceiling: str | None = None,
    resource_scope: list[str] | None = None,
    subject_version_refs: list[str] | None = None,
) -> None:
    store.save_authorization(
        create_grant_for_approval(
            principal_ref="human:owner",
            grantee_ref=actor,
            allowed_capabilities=[capability],
            subject_version_refs=subject_version_refs or ["patch:v1"],
            effect_ceiling=effect_ceiling,
            resource_scope=resource_scope,
            ttl_seconds=3600,
        )
    )


def _error_code(result: CapabilityResult) -> str:
    assert result.error is not None, f"expected boundary error, got {result.model_dump()}"
    code = result.error.get("code")
    assert isinstance(code, str), f"missing stable error code: {result.model_dump()}"
    return code


@pytest.mark.asyncio
async def test_e001_no_grant_blocks_side_effect(authoritative_runtime: dict[str, Any]) -> None:
    result = await authoritative_runtime["service"].invoke(_request())

    assert _error_code(result) == "AuthorizationRequired"
    assert authoritative_runtime["provider"].invoke_count == 0


@pytest.mark.asyncio
async def test_e002_missing_actor_blocks_even_with_grant(authoritative_runtime: dict[str, Any]) -> None:
    store = authoritative_runtime["store"]
    _grant(store, capability="test.side_effect", actor="agent:runner")

    result = await authoritative_runtime["service"].invoke(_request(actor_ref=None))

    assert _error_code(result) == "AuthorizationRequired"
    assert authoritative_runtime["provider"].invoke_count == 0


@pytest.mark.asyncio
async def test_e003_authorization_store_failure_fails_closed() -> None:
    store = ExplodingAuthorizationStore()
    provider = CountingProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    boundary = RealityBoundary(store=store, registry=registry, routing=ConstraintRouter(registry=registry))
    service = CapabilityService(registry=registry, boundary=boundary, store=store)

    result = await service.invoke(_request())

    assert _error_code(result) == "AuthorizationUnavailable"
    assert provider.invoke_count == 0


@pytest.mark.asyncio
async def test_e004_policy_exception_fails_closed(authoritative_runtime: dict[str, Any]) -> None:
    authoritative_runtime["boundary"].policy_engine = ExplodingPolicy()

    result = await authoritative_runtime["service"].invoke(_request("test.read"))

    assert _error_code(result) == "PolicyUnavailable"
    assert authoritative_runtime["provider"].invoke_count == 0


@pytest.mark.asyncio
async def test_e005_procedure_exception_fails_closed(
    authoritative_runtime: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    store = authoritative_runtime["store"]
    work, run = _seed_work_run(store)

    def explode(*args: Any, **kwargs: Any) -> list[Any]:
        raise RuntimeError("procedure checker unavailable")

    monkeypatch.setattr("portable_runtime.workflows.procedure.check_procedure", explode)
    result = await authoritative_runtime["service"].invoke(
        _request("test.read", work_id=work.id, run_id=run.id)
    )

    assert _error_code(result) == "ProcedureUnavailable"
    assert authoritative_runtime["provider"].invoke_count == 0


@pytest.mark.asyncio
async def test_e006_open_procedure_blocks(authoritative_runtime: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    store = authoritative_runtime["store"]
    work, run = _seed_work_run(store)
    from portable_runtime.workflows.procedure import ObligationStatus

    monkeypatch.setattr(
        "portable_runtime.workflows.procedure.check_procedure",
        lambda *args, **kwargs: [ObligationStatus(obligation="authorization", status="open")],
    )
    result = await authoritative_runtime["service"].invoke(
        _request("test.read", work_id=work.id, run_id=run.id)
    )

    assert _error_code(result) == "ProcedureIncomplete"
    assert authoritative_runtime["provider"].invoke_count == 0


@pytest.mark.asyncio
async def test_e007_policy_require_without_proof_blocks(authoritative_runtime: dict[str, Any]) -> None:
    authoritative_runtime["boundary"].policy_engine = RequiringPolicy()

    result = await authoritative_runtime["service"].invoke(_request("test.read"))

    assert _error_code(result) == "ObligationUnsatisfied"
    assert authoritative_runtime["provider"].invoke_count == 0


@pytest.mark.asyncio
async def test_e008_caller_cannot_underreport_effect(authoritative_runtime: dict[str, Any]) -> None:
    store = authoritative_runtime["store"]
    _grant(
        store,
        capability="deploy.prod",
        actor="agent:runner",
        effect_ceiling="write-remote",
        resource_scope=["prod/app"],
        subject_version_refs=["v1"],
    )

    result = await authoritative_runtime["service"].invoke(
        _request(
            "deploy.prod",
            actor_ref="agent:runner",
            resource_ref="prod/app",
            subject_version_refs=["v1"],
            effect_class="read",
        )
    )

    assert _error_code(result) == "AuthorizationDenied"
    assert authoritative_runtime["provider"].invoke_count == 0


@pytest.mark.asyncio
async def test_e009_stale_generation_is_fenced(authoritative_runtime: dict[str, Any]) -> None:
    store = authoritative_runtime["store"]
    work, run = _seed_work_run(store)
    assert store.acquire_lease(run.id, owner="worker-a", ttl_seconds=30)
    stale_generation = store.get_run(run.id).lease_generation  # type: ignore[union-attr]
    assert store.release_lease(run.id, owner="worker-a")
    assert store.acquire_lease(run.id, owner="worker-b", ttl_seconds=30)

    result = await authoritative_runtime["service"].invoke(
        _request("test.read", work_id=work.id, run_id=run.id, lease_generation=stale_generation, lease_owner="worker-a")
    )

    assert _error_code(result) == "FencingRejected"
    assert authoritative_runtime["provider"].invoke_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", ["worker-a", None], ids=["wrong-owner", "missing-owner"])
async def test_e010_wrong_or_missing_owner_is_fenced(
    authoritative_runtime: dict[str, Any], owner: str | None
) -> None:
    store = authoritative_runtime["store"]
    work, run = _seed_work_run(store)
    assert store.acquire_lease(run.id, owner="worker-b", ttl_seconds=30)
    current = store.get_run(run.id)
    assert current is not None

    result = await authoritative_runtime["service"].invoke(
        _request("test.read", work_id=work.id, run_id=run.id, lease_generation=current.lease_generation, lease_owner=owner)
    )

    assert _error_code(result) == "FencingRejected"
    assert authoritative_runtime["provider"].invoke_count == 0


@pytest.mark.asyncio
async def test_e011_expired_lease_is_fenced(authoritative_runtime: dict[str, Any]) -> None:
    store = authoritative_runtime["store"]
    work, run = _seed_work_run(store)
    assert store.acquire_lease(run.id, owner="worker-a", ttl_seconds=30)
    current = store.get_run(run.id)
    assert current is not None
    current.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    store.save_run(current)

    result = await authoritative_runtime["service"].invoke(
        _request(
            "test.read",
            work_id=work.id,
            run_id=run.id,
            lease_generation=current.lease_generation,
            lease_owner="worker-a",
        )
    )

    assert _error_code(result) == "FencingRejected"
    assert authoritative_runtime["provider"].invoke_count == 0


@pytest.mark.asyncio
async def test_e012_precommit_failure_blocks_before_provider() -> None:
    store = FailingPrecommitStore()
    provider = CountingProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    boundary = RealityBoundary(store=store, registry=registry, routing=ConstraintRouter(registry=registry))
    service = CapabilityService(registry=registry, boundary=boundary, store=store)
    work, run = _seed_work_run(store)
    _grant(store, capability="test.side_effect", actor="agent:runner")

    result = await service.invoke(
        _request("test.side_effect", work_id=work.id, run_id=run.id, actor_ref="agent:runner")
    )

    assert _error_code(result) == "PrecommitFailed"
    assert provider.invoke_count == 0


@pytest.mark.asyncio
async def test_e013_reliability_exception_fails_closed(authoritative_runtime: dict[str, Any]) -> None:
    authoritative_runtime["boundary"].reliability = ExplodingReliability()

    result = await authoritative_runtime["service"].invoke(_request("test.read"))

    assert _error_code(result) == "ReliabilityUnavailable"
    assert authoritative_runtime["provider"].invoke_count == 0


@pytest.mark.asyncio
async def test_e014_exhausted_reliability_budget_blocks(authoritative_runtime: dict[str, Any]) -> None:
    authoritative_runtime["boundary"].reliability = ExhaustedReliability()

    result = await authoritative_runtime["service"].invoke(_request("test.read"))

    assert _error_code(result) == "ReliabilityBlocked"
    assert authoritative_runtime["provider"].invoke_count == 0


@pytest.mark.asyncio
async def test_e015_hard_constraints_with_no_eligible_provider(authoritative_runtime: dict[str, Any]) -> None:
    provider = authoritative_runtime["provider"]
    provider._descriptor = provider.descriptor.model_copy(update={"constraints": {"region": "earth"}})

    result = await authoritative_runtime["service"].invoke(
        _request("test.read", constraints={"region": "mars"})
    )

    assert _error_code(result) == "NoEligibleProvider"
    assert provider.invoke_count == 0


@pytest.mark.asyncio
async def test_e016_open_circuit_prevents_selection(
    authoritative_runtime: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("portable_runtime.core.boundary._circuit_for", lambda provider_id: ClosedCircuit())

    result = await authoritative_runtime["service"].invoke(_request("test.read"))

    assert _error_code(result) == "NoEligibleProvider"
    assert authoritative_runtime["provider"].invoke_count == 0


@pytest.mark.asyncio
async def test_e017_provider_success_does_not_create_epistemic_support(
    authoritative_runtime: dict[str, Any]
) -> None:
    store = authoritative_runtime["store"]

    result = await authoritative_runtime["service"].invoke(_request("test.read"))

    assert result.status == "succeeded"
    assert authoritative_runtime["provider"].invoke_count == 1
    assert store.list_evidence() == []
    assert store.list_records("Assertion") == []


@pytest.mark.asyncio
async def test_e018_unpromotable_knowledge_remains_candidate(
    authoritative_runtime: dict[str, Any]
) -> None:
    store = authoritative_runtime["store"]
    candidate = KnowledgeItem(
        id=new_id("knowledge"),
        kind="observation",
        title="unqualified candidate",
        content_ref="artifact:unqualified",
        status="candidate",
        evidence_refs=["evidence:1"],
    )
    store.save_knowledge(candidate)

    result = await authoritative_runtime["service"].invoke(_request("test.read"))

    assert result.status == "succeeded"
    assert authoritative_runtime["provider"].invoke_count == 1
    retained = store.get_knowledge(candidate.id)
    assert retained is not None
    assert retained.status == "candidate"
    assert classify(retained) == "retain-candidate"
    assert retained.status != "archived"


@pytest.mark.asyncio
async def test_e019_post_invoke_lease_takeover_rejects_result() -> None:
    store = InMemoryStateStore()
    work, run = _seed_work_run(store)

    async def takeover(request: CapabilityRequest, context: InvocationContext) -> None:
        assert store.release_lease(run.id, owner="worker-a")
        assert store.acquire_lease(run.id, owner="worker-b", ttl_seconds=30)

    provider = CountingProvider(on_invoke=takeover)
    registry = ProviderRegistry()
    registry.register(provider)
    boundary = RealityBoundary(store=store, registry=registry, routing=ConstraintRouter(registry=registry))
    service = CapabilityService(registry=registry, boundary=boundary, store=store)
    assert store.acquire_lease(run.id, owner="worker-a", ttl_seconds=30)
    current = store.get_run(run.id)
    assert current is not None
    _grant(store, capability="test.side_effect", actor="agent:runner")

    result = await service.invoke(
        _request(
            "test.side_effect",
            work_id=work.id,
            run_id=run.id,
            actor_ref="agent:runner",
            lease_generation=current.lease_generation,
            lease_owner="worker-a",
        )
    )

    assert provider.invoke_count == 1
    assert _error_code(result) == "PostFencingRejected"
    assert result.status != "succeeded"
    assert not getattr(store, "_records", {}).get("outcome", {})


@pytest.mark.asyncio
async def test_e020_result_commit_failure_never_projects_success() -> None:
    store = FailingResultCommitStore()
    work, run = _seed_work_run(store)
    provider = CountingProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    boundary = RealityBoundary(store=store, registry=registry, routing=ConstraintRouter(registry=registry))
    service = CapabilityService(registry=registry, boundary=boundary, store=store)
    _grant(store, capability="test.side_effect", actor="agent:runner")

    result = await service.invoke(
        _request("test.side_effect", work_id=work.id, run_id=run.id, actor_ref="agent:runner")
    )

    assert provider.invoke_count == 1
    assert _error_code(result) == "ResultCommitFailed"
    assert result.status in {"unknown", "unavailable", "failed"}
    assert result.status != "succeeded"
    assert not getattr(store, "_records", {}).get("outcome", {})


@pytest.mark.asyncio
async def test_e021_inline_qualification_facts_are_not_authoritative() -> None:
    store = InMemoryStateStore()
    provider = CountingProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    boundary = RealityBoundary(store=store, registry=registry, routing=ConstraintRouter(registry=registry))
    service = CapabilityService(registry=registry, boundary=boundary, store=store)
    work = Work(
        id=new_id("work"),
        title="fake proof",
        kind="generic-task",
        metadata={
            "purpose": "fake proof",
            "execution_boundary": "provider",
            "procedure_proofs": {
                "failure_stop_proofs": [{"condition": "caller claims stop"}],
                "verification_results": [ClosedVerificationResult(result="pass")],
            },
        },
    )
    run = Run(id=new_id("run"), work_id=work.id, status="running")
    store.save_work(work)
    store.save_run(run)
    _grant(store, capability="test.side_effect", actor="agent:runner")

    result = await service.invoke(
        _request(
            "test.side_effect",
            work_id=work.id,
            run_id=run.id,
            actor_ref="agent:runner",
        )
    )

    assert _error_code(result) == "QualificationUnavailable"
    assert provider.invoke_count == 0


@pytest.mark.asyncio
async def test_e022_expired_authorization_reference_fails_closed() -> None:
    store = InMemoryStateStore()
    provider = CountingProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    boundary = RealityBoundary(store=store, registry=registry, routing=ConstraintRouter(registry=registry))
    service = CapabilityService(registry=registry, boundary=boundary, store=store)
    grant = AuthorizationGrant(
        principal_ref="human:owner",
        grantee_ref="agent:runner",
        allowed_capabilities=["test.side_effect"],
        subject_version_refs=["patch:v1"],
        valid_from=datetime.now(UTC) - timedelta(seconds=30),
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    store.save_authorization(grant)

    result = await service.invoke(
        _request(
            "test.side_effect",
            actor_ref="agent:runner",
            metadata={"authorization_refs": [grant.id]},
        )
    )

    assert _error_code(result) == "QualificationUnavailable"
    assert provider.invoke_count == 0


@pytest.mark.asyncio
async def test_e023_version_mismatched_qualification_reference_fails_closed() -> None:
    store = InMemoryStateStore()
    provider = CountingProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    boundary = RealityBoundary(store=store, registry=registry, routing=ConstraintRouter(registry=registry))
    service = CapabilityService(registry=registry, boundary=boundary, store=store)
    evidence = BaseRecord(
        record_type="EvidenceArtifact",
        lifecycle_status="current",
        version=2,
        metadata={"qualification_kind": "evidence"},
    )
    store.save_record(evidence)

    result = await service.invoke(
        _request(
            "test.read",
            metadata={
                "evidence_refs": [
                    {"id": evidence.id, "kind": "EvidenceArtifact", "version": 1}
                ]
            },
        )
    )

    assert _error_code(result) == "QualificationUnavailable"
    assert provider.invoke_count == 0
