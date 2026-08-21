from __future__ import annotations

import pytest

from portable_runtime.core.capabilities import CapabilityRequest, ProviderDescriptor
from portable_runtime.core.router import ConstraintRouter
from portable_runtime.core.registry import ProviderRegistry


class _Provider:
    def __init__(self, descriptor: ProviderDescriptor) -> None:
        self._descriptor = descriptor

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    async def health(self):
        from portable_runtime.core.capabilities import ProviderHealth

        return ProviderHealth(provider_id=self._descriptor.id, available=True)


@pytest.mark.asyncio
async def test_required_failure_domains_are_hard_constraints() -> None:
    registry = ProviderRegistry()
    good = ProviderDescriptor(
        id="good",
        name="good",
        version="1",
        capabilities=["verify.test"],
        constraints={"region": "eu"},
        provider_family="family-b",
        credential_domain="cred-b",
    )
    bad = good.model_copy(update={"id": "bad", "provider_family": "family-a"})
    registry.register(_Provider(good))
    registry.register(_Provider(bad))
    request = CapabilityRequest(
        id="request",
        capability="verify.test",
        constraints={"required_failure_domains": {"provider_family": "family-b"}},
    )

    selected = await ConstraintRouter(registry=registry).select(request, [good, bad])

    assert selected is not None and selected.id == "good"


@pytest.mark.asyncio
async def test_inline_reference_descriptors_cannot_prove_independence() -> None:
    descriptor = ProviderDescriptor(
        id="candidate",
        name="candidate",
        version="1",
        capabilities=["verify.test"],
        provider_family="candidate-family",
        credential_domain="candidate-cred",
    )
    request = CapabilityRequest(
        id="request",
        capability="verify.test",
        metadata={
            "independence_constraints": {
                "reference_provider_refs": ["executor"],
                "independent_on": ["provider_family"],
            },
            "reference_descriptors": [
                {"id": "executor", "provider_family": "executor-family"}
            ],
        },
    )

    selected = await ConstraintRouter().select(request, [descriptor])

    assert selected is None
