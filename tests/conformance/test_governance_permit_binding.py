from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
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
from portable_runtime.core.qualification import (
    GOVERNANCE_NOT_APPLICABLE_DIGEST,
    InvocationPermit,
)
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.governance.canonical import state_seed_event
from portable_runtime.governance.distinction import DistinctionState, ReviewObligation, UseContext
from portable_runtime.governance.persistence import (
    DistinctionGovernancePersistence,
    InMemoryDistinctionGovernancePersistence,
    SQLiteDistinctionGovernancePersistence,
)
from portable_runtime.governance.use_admission import (
    GovernanceUseAdmission,
    GovernanceUseRequirement,
    governance_not_applicable_digest,
)
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore

BACKENDS = ("memory", "sqlite")


@contextmanager
def _backend(
    backend: str,
    tmp_path: Path,
    *,
    suffix: str,
) -> Iterator[tuple[Any, DistinctionGovernancePersistence]]:
    if backend == "memory":
        store = InMemoryStateStore()
        yield store, InMemoryDistinctionGovernancePersistence(store)
        return
    store = SQLiteStateStore(tmp_path / f"e2a-{suffix}.db")
    try:
        yield store, SQLiteDistinctionGovernancePersistence(store)
    finally:
        store.close()


def _state(
    *,
    scope: frozenset[str] = frozenset({"a"}),
    qualification: str = "qualified",
    activation: str = "active",
    version: int = 1,
) -> DistinctionState:
    partition = tuple(frozenset({item}) for item in sorted(scope))
    return DistinctionState(
        qualification=qualification,
        activation=activation,
        scope=scope,
        partition=partition,
        version=version,
    )


def _requirement(
    requested_scope: frozenset[str] = frozenset({"a"}),
    *,
    context: str = "ctx",
) -> GovernanceUseRequirement:
    return GovernanceUseRequirement(
        scheme_id="d",
        use_context=UseContext(context, requested_scope),
    )


def _request(suffix: str, *, capability: str = "test.read") -> CapabilityRequest:
    return CapabilityRequest(id=f"req-{suffix}", capability=capability)


def _append_state_projection(store: Any, state: DistinctionState, *, suffix: str) -> None:
    event = state_seed_event("d", state).model_copy(update={"id": f"gov_e2_{suffix}"})
    store.append_event(event)


class _CountingProvider:
    def __init__(
        self,
        *,
        mutation: Callable[[], None] | None = None,
        capability: str = "test.read",
        side_effect_class: str = "pure",
        effect_semantics: str = "pure",
        reversibility: str = "reversible",
    ) -> None:
        self.calls = 0
        self.last_context: InvocationContext | None = None
        self._mutation = mutation
        self._mutated = False
        self._descriptor = ProviderDescriptor(
            id="e2-provider",
            name="E2 counting provider",
            version="1",
            capabilities=[capability],
            side_effect_class=side_effect_class,
            effect_semantics=effect_semantics,
            reversibility=reversibility,
        )

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    async def health(self) -> ProviderHealth:
        if self._mutation is not None and not self._mutated:
            self._mutation()
            self._mutated = True
        return ProviderHealth(provider_id=self.descriptor.id, available=True)

    async def invoke(
        self,
        request: CapabilityRequest,
        context: InvocationContext,
    ) -> CapabilityResult:
        self.calls += 1
        self.last_context = context
        return CapabilityResult(
            request_id=request.id,
            provider_id=self.descriptor.id,
            status="succeeded",
            message="invoked",
        )

    async def cancel(self, request_id: str) -> None:
        return None

    async def reconcile(self, request_id: str) -> CapabilityResult | None:
        return None


def _boundary(
    store: Any,
    provider: _CountingProvider,
    *,
    requirement: GovernanceUseRequirement | None,
    policy_engine: Any | None = None,
) -> RealityBoundary:
    registry = ProviderRegistry()
    registry.register(provider)
    resolver = (
        (lambda _request: requirement)
        if requirement is not None
        else (lambda _request: None)
    )
    return RealityBoundary(
        store=store,
        registry=registry,
        policy_engine=policy_engine,
        governance_requirement_resolver=resolver,
    )


@pytest.mark.parametrize("backend", BACKENDS)
async def test_e2_001_new_blocking_q_after_initial_admission_stops_provider(
    backend: str,
    tmp_path: Path,
) -> None:
    with _backend(backend, tmp_path, suffix=f"001-{backend}") as (store, persistence):
        persistence.seed_state("d", _state())

        def open_blocker() -> None:
            persistence.open_obligation(
                ReviewObligation(
                    id="q-e2-001",
                    target="d",
                    trigger_ref="event-e2-001",
                    basis_refs=("basis-e2",),
                    context="ctx",
                    blocking=True,
                )
            )

        provider = _CountingProvider(mutation=open_blocker)
        result = await _boundary(
            store,
            provider,
            requirement=_requirement(),
        ).execute(_request("e2-001"))

        assert provider.calls == 0
        assert result.error is not None
        assert result.error.get("code") == "GovernanceChanged"


@pytest.mark.parametrize("backend", BACKENDS)
async def test_e2_002_scope_shrink_after_initial_admission_stops_provider(
    backend: str,
    tmp_path: Path,
) -> None:
    with _backend(backend, tmp_path, suffix=f"002-{backend}") as (store, persistence):
        persistence.seed_state("d", _state(scope=frozenset({"a", "b"})))

        def shrink_scope() -> None:
            _append_state_projection(
                store,
                _state(scope=frozenset({"a"}), version=2),
                suffix=f"scope-{backend}",
            )

        provider = _CountingProvider(mutation=shrink_scope)
        result = await _boundary(
            store,
            provider,
            requirement=_requirement(frozenset({"b"})),
        ).execute(_request("e2-002"))

        assert provider.calls == 0
        assert result.error is not None
        assert result.error.get("code") == "GovernanceChanged"


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize(
    ("qualification", "activation"),
    (("candidate", "suspended"), ("qualified", "suspended")),
)
async def test_e2_003_projection_change_after_initial_admission_stops_provider(
    backend: str,
    tmp_path: Path,
    qualification: str,
    activation: str,
) -> None:
    with _backend(backend, tmp_path, suffix=f"003-{backend}-{qualification}") as (store, persistence):
        persistence.seed_state("d", _state())

        def change_projection() -> None:
            _append_state_projection(
                store,
                _state(
                    qualification=qualification,
                    activation=activation,
                    version=2,
                ),
                suffix=f"projection-{backend}-{qualification}-{activation}",
            )

        provider = _CountingProvider(mutation=change_projection)
        result = await _boundary(
            store,
            provider,
            requirement=_requirement(),
        ).execute(_request("e2-003"))

        assert provider.calls == 0
        assert result.error is not None
        assert result.error.get("code") == "GovernanceChanged"


@pytest.mark.parametrize("backend", BACKENDS)
async def test_e2_004_unrelated_nonblocking_q_does_not_false_stale(
    backend: str,
    tmp_path: Path,
) -> None:
    with _backend(backend, tmp_path, suffix=f"004-{backend}") as (store, persistence):
        persistence.seed_state("d", _state())

        def open_nonblocking_review() -> None:
            persistence.open_obligation(
                ReviewObligation(
                    id="q-e2-004",
                    target="d",
                    trigger_ref="event-e2-004",
                    basis_refs=("basis-e2",),
                    context="other-context",
                    blocking=False,
                )
            )

        provider = _CountingProvider(mutation=open_nonblocking_review)
        result = await _boundary(
            store,
            provider,
            requirement=_requirement(),
        ).execute(_request("e2-004"))

        assert result.status == "succeeded"
        assert provider.calls == 1
        assert result.error is None


def test_e2_005_governed_permit_binds_nonempty_governance_digests() -> None:
    store = InMemoryStateStore()
    persistence = InMemoryDistinctionGovernancePersistence(store)
    persistence.seed_state("d", _state())
    request = _request("e2-005")
    requirement = _requirement()
    admission = GovernanceUseAdmission(store).evaluate(
        request,
        lambda _request: requirement,
    )

    assert admission.status == "allowed"
    assert admission.requirement_digest
    assert admission.snapshot_digest

    permit = InvocationPermit.issue(
        request,
        provider_id="e2-provider",
        qualification_digest="qualification-e2-005",
        lease_generation=0,
        governance_applicable=True,
        governance_requirement_digest=admission.requirement_digest,
        governance_snapshot_digest=admission.snapshot_digest,
    )

    assert permit.governance_applicable is True
    assert permit.governance_requirement_digest == admission.requirement_digest
    assert permit.governance_snapshot_digest == admission.snapshot_digest
    assert permit.snapshot_payload()["authority"]["governance"] == {
        "applicable": True,
        "requirement_digest": admission.requirement_digest,
        "snapshot_digest": admission.snapshot_digest,
    }


async def test_e2_006_non_governed_permit_explicitly_binds_not_applicable() -> None:
    request = _request("e2-006")
    permit = InvocationPermit.issue(
        request,
        provider_id="e2-provider",
        qualification_digest="qualification-e2-006",
        lease_generation=0,
    )

    assert GOVERNANCE_NOT_APPLICABLE_DIGEST == governance_not_applicable_digest()
    assert permit.governance_applicable is False
    assert permit.governance_requirement_digest == GOVERNANCE_NOT_APPLICABLE_DIGEST
    assert permit.governance_snapshot_digest == GOVERNANCE_NOT_APPLICABLE_DIGEST
    assert permit.snapshot_payload()["authority"]["governance"] == {
        "applicable": False,
        "requirement_digest": GOVERNANCE_NOT_APPLICABLE_DIGEST,
        "snapshot_digest": GOVERNANCE_NOT_APPLICABLE_DIGEST,
    }

    store = InMemoryStateStore()
    provider = _CountingProvider()
    result = await _boundary(store, provider, requirement=None).execute(request)

    assert result.status == "succeeded"
    assert provider.calls == 1
    assert provider.last_context is not None
    assert provider.last_context.metadata["governance_applicable"] is False
    assert (
        provider.last_context.metadata["governance_requirement_digest"]
        == GOVERNANCE_NOT_APPLICABLE_DIGEST
    )
    assert (
        provider.last_context.metadata["governance_snapshot_digest"]
        == GOVERNANCE_NOT_APPLICABLE_DIGEST
    )


async def test_e2_007_tampered_permit_governance_digest_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryStateStore()
    persistence = InMemoryDistinctionGovernancePersistence(store)
    persistence.seed_state("d", _state())
    provider = _CountingProvider()
    original_issue = InvocationPermit.issue

    def tampered_issue(
        cls: type[InvocationPermit],
        request: Any,
        **kwargs: Any,
    ) -> InvocationPermit:
        del cls
        permit = original_issue(request, **kwargs)
        return replace(permit, governance_snapshot_digest="tampered-governance-digest")

    monkeypatch.setattr(InvocationPermit, "issue", classmethod(tampered_issue))
    result = await _boundary(
        store,
        provider,
        requirement=_requirement(),
    ).execute(_request("e2-007"))

    assert provider.calls == 0
    assert result.error is not None
    assert result.error.get("code") == "GovernanceChanged"
