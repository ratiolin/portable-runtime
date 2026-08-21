from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from portable_runtime.core.boundary import RealityBoundary
from portable_runtime.core.capabilities import CapabilityRequest, CapabilityResult, InvocationContext, ProviderDescriptor, ProviderHealth
from portable_runtime.core.capability_contract import (
    CapabilityContractRegistry,
    EffectContractMissing,
    compute_effective_procedure_profile,
)
from portable_runtime.core.invocation import InvocationFactory
from portable_runtime.core.models import Run, Work
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.records.authorization import AuthorizationGrant
from portable_runtime.stores.memory import InMemoryStateStore


class _Provider:
    def __init__(self) -> None:
        self._descriptor = ProviderDescriptor(
            id="procedure-floor-provider",
            name="procedure floor provider",
            version="1.0.0",
            capabilities=["code.edit"],
            side_effect_class="idempotent",
            effect_semantics="idempotent",
            reversibility="reversible",
        )

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.descriptor.id, available=True)

    async def invoke(self, request: CapabilityRequest, context: InvocationContext) -> CapabilityResult:
        return CapabilityResult(request_id=request.id, provider_id=self.descriptor.id, status="succeeded")

    async def cancel(self, request_id: str) -> None:
        return None

    async def reconcile(self, request_id: str) -> CapabilityResult | None:
        return None


def test_procedure_profile_floor_is_monotonic_and_unknown_fails_closed() -> None:
    assert compute_effective_procedure_profile("standard", "minimal") == "standard"
    assert compute_effective_procedure_profile("minimal", "enhanced") == "enhanced"
    assert compute_effective_procedure_profile("standard", None, "enhanced") == "enhanced"
    with pytest.raises(ValueError, match="unknown procedure profile"):
        compute_effective_procedure_profile("standard", "untrusted")


def test_builtin_code_contracts_and_unknown_code_actions_are_not_reads() -> None:
    registry = CapabilityContractRegistry()

    assert registry.resolve("code.read").minimum_impact_class == "read"
    assert registry.resolve("code.read").authorization_requirement == "none"
    assert registry.resolve("code.test").minimum_procedure_profile == "standard"
    assert registry.resolve("code.test").subject_version_required is True
    assert registry.resolve("shell.exec").authorization_requirement == "required"
    assert registry.resolve("git.diff").minimum_impact_class == "read"
    assert registry.resolve("metrics.read").minimum_impact_class == "read"

    with pytest.raises(EffectContractMissing):
        registry.resolve("code.delete")


def test_invocation_factory_preserves_stricter_requested_profile() -> None:
    registry = CapabilityContractRegistry()
    factory = InvocationFactory(contract_registry=registry)

    enhanced = factory.build(
        "code.edit",
        metadata={"procedure_profile": "enhanced"},
        parameters={"repo": "repo"},
    )
    minimal = factory.build(
        "code.edit",
        metadata={"procedure_profile": "minimal"},
        parameters={"repo": "repo"},
    )

    assert enhanced.metadata["procedure_profile"] == "enhanced"
    assert minimal.metadata["procedure_profile"] == "standard"


@pytest.mark.asyncio
async def test_reality_boundary_does_not_downgrade_work_run_request_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryStateStore()
    work = Work(
        id="work-floor",
        title="procedure floor",
        metadata={"procedure_profile": "minimal"},
    )
    run = Run(
        id="run-floor",
        work_id=work.id,
        metadata={"procedure_profile": "minimal"},
        lease_owner="agent:test",
        lease_generation=1,
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    store.save_work(work)
    store.save_run(run)
    store.save_authorization(
        AuthorizationGrant(
            id="grant-floor",
            principal_ref="human:owner",
            grantee_ref="agent:test",
            allowed_capabilities=["code.edit"],
            resource_scope=["repo:floor"],
            effect_ceiling="write-local",
            subject_version_refs=["git:v1"],
        )
    )
    provider_registry = ProviderRegistry()
    provider_registry.register(_Provider())
    observed_profiles: list[str] = []

    from portable_runtime.workflows import procedure

    def capture_profile(work_value, run_value, profile, **kwargs):
        observed_profiles.append(str(profile))
        return []

    monkeypatch.setattr(procedure, "check_procedure", capture_profile)
    boundary = RealityBoundary(store=store, registry=provider_registry)
    result = await boundary.execute(
        CapabilityRequest(
            id="request-floor",
            capability="code.edit",
            work_id=work.id,
            run_id=run.id,
            actor_ref="agent:test",
            resource_ref="repo:floor",
            subject_version_refs=["git:v1"],
            effect_class="write-local",
            lease_generation=1,
            lease_owner="agent:test",
            metadata={"procedure_profile": "minimal"},
        )
    )

    assert result.status == "succeeded", result.model_dump()
    assert observed_profiles and observed_profiles[0] == "standard"
