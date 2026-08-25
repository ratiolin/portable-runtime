from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
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
from portable_runtime.core.models import Event
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.governance.canonical import (
    GOVERNANCE_STATE_SEEDED,
    state_payload,
)
from portable_runtime.governance.distinction import (
    DISTINCTION_GOVERNANCE_CONTRACT_VERSION,
    DistinctionState,
    ReviewObligation,
    UseContext,
)
from portable_runtime.governance.history_epoch import detect_governance_history_epoch
from portable_runtime.governance.persistence import (
    GOVERNANCE_APPLICATION_KIND,
    GOVERNANCE_STATE_KIND,
    DistinctionGovernancePersistence,
    InMemoryDistinctionGovernancePersistence,
    PersistedDistinctionState,
    PersistedGovernedApplication,
    SQLiteDistinctionGovernancePersistence,
)
from portable_runtime.governance.use_admission import GovernanceUseRequirement
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore

BACKENDS = ("memory", "sqlite")


class _CountingProvider:
    def __init__(self) -> None:
        self.calls = 0
        self._descriptor = ProviderDescriptor(
            id="e1-provider",
            name="E1 counting provider",
            version="1",
            capabilities=["test.read"],
            side_effect_class="pure",
            effect_semantics="pure",
            reversibility="reversible",
        )

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.descriptor.id, available=True)

    async def invoke(
        self,
        request: CapabilityRequest,
        context: InvocationContext,
    ) -> CapabilityResult:
        self.calls += 1
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


@dataclass(frozen=True)
class _AllowDecision:
    disposition: str = "allow"
    status: str = "allow"
    obligations: tuple[object, ...] = ()
    reason: str = "allow"


class _AllowPolicy:
    def __init__(self) -> None:
        self.calls = 0

    async def evaluate(self, _context: object) -> _AllowDecision:
        self.calls += 1
        return _AllowDecision()


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
    store = SQLiteStateStore(tmp_path / f"e1-{backend}-{suffix}.db")
    try:
        yield store, SQLiteDistinctionGovernancePersistence(store)
    finally:
        store.close()


def _state(
    *,
    qualification: str = "qualified",
    activation: str = "active",
) -> DistinctionState:
    return DistinctionState(
        qualification=qualification,
        activation=activation,
        scope=frozenset({"a", "b"}),
        partition=(frozenset({"a"}), frozenset({"b"})),
        version=1,
    )


def _requirement(*, requested_scope: frozenset[str] = frozenset({"a"})) -> GovernanceUseRequirement:
    return GovernanceUseRequirement(
        scheme_id="d",
        use_context=UseContext("ctx", requested_scope),
    )


def _boundary(
    store: Any,
    provider: _CountingProvider,
    *,
    requirement: GovernanceUseRequirement | None,
    policy_engine: Any | None = None,
) -> RealityBoundary:
    registry = ProviderRegistry()
    registry.register(provider)
    return RealityBoundary(
        store=store,
        registry=registry,
        policy_engine=policy_engine,
        governance_requirement_resolver=lambda _request: requirement,
    )


def _request(test_id: str) -> CapabilityRequest:
    return CapabilityRequest(id=f"req-{test_id}", capability="test.read")


def _blocking_obligation(test_id: str) -> ReviewObligation:
    return ReviewObligation(
        id=f"q-{test_id}",
        target="d",
        trigger_ref=f"event-{test_id}",
        basis_refs=("basis-e1",),
        context="ctx",
        blocking=True,
    )


def _clear_sidecar(backend: str, store: Any) -> None:
    if backend == "memory":
        records = vars(store)["_distinction_governance_records"]
        for values in records.values():
            values.clear()
        return
    connection = vars(store)["_connection"]
    connection.execute("DELETE FROM runtime_governance_records")


def _inject_legacy_incomplete(persistence: DistinctionGovernancePersistence) -> None:
    state = _state()
    with persistence._transaction():
        persistence._put_model(
            GOVERNANCE_STATE_KIND,
            PersistedDistinctionState(
                id="d",
                scheme_id="d",
                qualification=state.qualification,
                activation=state.activation,
                scope=state.scope,
                partition=state.partition,
                version=state.version,
            ),
        )
        persistence._put_model(
            GOVERNANCE_APPLICATION_KIND,
            PersistedGovernedApplication(
                id="legacy-discharge",
                actor="closer",
                operation="apply_review_discharge",
                scheme_id="d",
                target="review_obligation:q-old",
                decision_ref="dec-old",
                context="ctx",
                review_obligation_id="q-old",
                effect_kind="review_discharge",
                pre_anchor="q-old",
                post_anchor="",
            ),
        )


@pytest.mark.parametrize("backend", BACKENDS)
async def test_e1_001_canonical_blocker_with_empty_sidecar_stops_provider(
    backend: str,
    tmp_path: Path,
) -> None:
    with _backend(backend, tmp_path, suffix="001") as (store, persistence):
        persistence.seed_state("d", _state())
        persistence.open_obligation(_blocking_obligation("e1-001"))
        _clear_sidecar(backend, store)
        assert persistence.list_states() == {}
        assert persistence.list_obligations() == {}

        provider = _CountingProvider()
        result = await _boundary(store, provider, requirement=_requirement()).execute(
            _request("e1-001")
        )

        assert provider.calls == 0
        assert result.error is not None
        assert result.error.get("code") == "GovernanceBlocked"


@pytest.mark.parametrize("backend", BACKENDS)
async def test_e1_002_canonical_usable_state_allows_provider(
    backend: str,
    tmp_path: Path,
) -> None:
    with _backend(backend, tmp_path, suffix="002") as (store, persistence):
        persistence.seed_state("d", _state())
        _clear_sidecar(backend, store)

        provider = _CountingProvider()
        result = await _boundary(store, provider, requirement=_requirement()).execute(
            _request("e1-002")
        )

        assert result.status == "succeeded"
        assert result.error is None
        assert provider.calls == 1


@pytest.mark.parametrize("backend", BACKENDS)
async def test_e1_003_scope_outside_projection_is_blocked(
    backend: str,
    tmp_path: Path,
) -> None:
    with _backend(backend, tmp_path, suffix="003") as (store, persistence):
        persistence.seed_state("d", _state())
        _clear_sidecar(backend, store)

        provider = _CountingProvider()
        result = await _boundary(
            store,
            provider,
            requirement=_requirement(requested_scope=frozenset({"c"})),
        ).execute(_request("e1-003"))

        assert provider.calls == 0
        assert result.error is not None
        assert result.error.get("code") == "GovernanceBlocked"


@pytest.mark.parametrize("backend", BACKENDS)
async def test_e1_004_disqualified_projection_is_blocked(
    backend: str,
    tmp_path: Path,
) -> None:
    with _backend(backend, tmp_path, suffix="004") as (store, persistence):
        persistence.seed_state(
            "d",
            _state(qualification="disqualified", activation="suspended"),
        )
        _clear_sidecar(backend, store)

        provider = _CountingProvider()
        result = await _boundary(store, provider, requirement=_requirement()).execute(
            _request("e1-004")
        )

        assert provider.calls == 0
        assert result.error is not None
        assert result.error.get("code") == "GovernanceBlocked"


@pytest.mark.parametrize("backend", BACKENDS)
async def test_e1_005_suspended_projection_is_blocked(
    backend: str,
    tmp_path: Path,
) -> None:
    with _backend(backend, tmp_path, suffix="005") as (store, persistence):
        persistence.seed_state("d", _state(activation="suspended"))
        _clear_sidecar(backend, store)

        provider = _CountingProvider()
        result = await _boundary(store, provider, requirement=_requirement()).execute(
            _request("e1-005")
        )

        assert provider.calls == 0
        assert result.error is not None
        assert result.error.get("code") == "GovernanceBlocked"


@pytest.mark.parametrize("backend", BACKENDS)
async def test_e1_006_governed_requirement_with_empty_history_fails_closed(
    backend: str,
    tmp_path: Path,
) -> None:
    with _backend(backend, tmp_path, suffix="006") as (store, persistence):
        assert detect_governance_history_epoch(persistence).epoch == "EMPTY"

        provider = _CountingProvider()
        result = await _boundary(store, provider, requirement=_requirement()).execute(
            _request("e1-006")
        )

        assert provider.calls == 0
        assert result.error is not None
        assert result.error.get("code") == "GovernanceUnavailable"


@pytest.mark.parametrize("backend", BACKENDS)
async def test_e1_007_legacy_incomplete_history_fails_closed(
    backend: str,
    tmp_path: Path,
) -> None:
    with _backend(backend, tmp_path, suffix="007") as (store, persistence):
        _inject_legacy_incomplete(persistence)
        assert detect_governance_history_epoch(persistence).epoch == "LEGACY_INCOMPLETE"

        provider = _CountingProvider()
        result = await _boundary(store, provider, requirement=_requirement()).execute(
            _request("e1-007")
        )

        assert provider.calls == 0
        assert result.error is not None
        assert result.error.get("code") == "GovernanceUnavailable"


@pytest.mark.parametrize("backend", BACKENDS)
async def test_e1_008_incompatible_canonical_history_is_unavailable(
    backend: str,
    tmp_path: Path,
) -> None:
    with _backend(backend, tmp_path, suffix="008") as (store, persistence):
        state = _state()
        persistence.seed_state("d", state)
        store.append_event(
            Event(
                id=f"bad-governance-history-{backend}",
                type=GOVERNANCE_STATE_SEEDED,
                subject_ref="d",
                payload={
                    "schema_version": "distinction-governance-history-v999",
                    "contract_version": DISTINCTION_GOVERNANCE_CONTRACT_VERSION,
                    "state": state_payload("d", state),
                },
            )
        )
        _clear_sidecar(backend, store)

        provider = _CountingProvider()
        result = await _boundary(store, provider, requirement=_requirement()).execute(
            _request("e1-008")
        )

        assert provider.calls == 0
        assert result.error is not None
        assert result.error.get("code") == "GovernanceUnavailable"


@pytest.mark.parametrize("backend", BACKENDS)
async def test_e1_009_no_governance_requirement_preserves_existing_behavior(
    backend: str,
    tmp_path: Path,
) -> None:
    with _backend(backend, tmp_path, suffix="009") as (store, _persistence):
        provider = _CountingProvider()
        result = await _boundary(store, provider, requirement=None).execute(
            _request("e1-009")
        )

        assert result.status == "succeeded"
        assert result.error is None
        assert provider.calls == 1


@pytest.mark.parametrize("backend", BACKENDS)
async def test_e1_010_policy_allow_cannot_override_governance_blocker(
    backend: str,
    tmp_path: Path,
) -> None:
    with _backend(backend, tmp_path, suffix="010") as (store, persistence):
        persistence.seed_state("d", _state())
        persistence.open_obligation(_blocking_obligation("e1-010"))
        _clear_sidecar(backend, store)

        provider = _CountingProvider()
        policy = _AllowPolicy()
        result = await _boundary(
            store,
            provider,
            requirement=_requirement(),
            policy_engine=policy,
        ).execute(_request("e1-010"))

        assert provider.calls == 0
        assert policy.calls == 0
        assert result.error is not None
        assert result.error.get("code") == "GovernanceBlocked"
