from __future__ import annotations

import asyncio
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from portable_runtime.core.boundary import RealityBoundary
from portable_runtime.core.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    InvocationContext,
    ProviderDescriptor,
    ProviderHealth,
)
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.governance.distinction import DistinctionState, ReviewObligation, UseContext
from portable_runtime.governance.persistence import (
    InMemoryDistinctionGovernancePersistence,
    SQLiteDistinctionGovernancePersistence,
)
from portable_runtime.governance.use_admission import (
    GovernanceUseAdmission,
    GovernanceUseRequirement,
)
from portable_runtime.stores.memory import InMemoryStateStore
from portable_runtime.stores.sqlite import SQLiteStateStore

"""E2b necessity audit: falsification-only, no production semantics.

A passing test in this file means the current E2a runtime permits a controlled
interleaving where canonical governance is observably blocking before the
provider's simulated *effect dispatch commitment* occurs.  These tests do not
define ``provider.invoke()`` entry as reality exit; the explicit
``effect-dispatched`` marker is the linearization candidate under audit.
"""


def _state() -> DistinctionState:
    return DistinctionState(
        qualification="qualified",
        activation="active",
        scope=frozenset({"a"}),
        partition=(frozenset({"a"}),),
        version=1,
    )


def _requirement() -> GovernanceUseRequirement:
    return GovernanceUseRequirement(
        scheme_id="d",
        use_context=UseContext("ctx", frozenset({"a"})),
    )


def _resolver(_request: CapabilityRequest) -> GovernanceUseRequirement:
    return _requirement()


def _request(suffix: str) -> CapabilityRequest:
    return CapabilityRequest(id=f"audit-{suffix}", capability="test.read")


def _blocker(suffix: str) -> ReviewObligation:
    return ReviewObligation(
        id=f"q-{suffix}",
        target="d",
        trigger_ref=f"event-{suffix}",
        basis_refs=(f"basis-{suffix}",),
        context="ctx",
        blocking=True,
    )


class _DispatchBarrierProvider:
    def __init__(self, suffix: str, trace: list[str]) -> None:
        self.calls = 0
        self.trace = trace
        self.entered = asyncio.Event()
        self.thread_entered = threading.Event()
        self.release = asyncio.Event()
        self._descriptor = ProviderDescriptor(
            id=f"audit-provider-{suffix}",
            name=f"E2b audit provider {suffix}",
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
        del context
        self.calls += 1
        self.trace.append("provider-entered")
        self.thread_entered.set()
        self.entered.set()
        await self.release.wait()
        # This marker intentionally models the point at which an effect attempt
        # becomes irrevocably dispatched to the outside world.
        self.trace.append("effect-dispatched")
        return CapabilityResult(
            request_id=request.id,
            provider_id=self.descriptor.id,
            status="succeeded",
        )

    async def cancel(self, request_id: str) -> None:
        del request_id

    async def reconcile(self, request_id: str) -> CapabilityResult | None:
        del request_id
        return None


def _boundary(store: Any, provider: _DispatchBarrierProvider) -> RealityBoundary:
    registry = ProviderRegistry()
    registry.register(provider)
    return RealityBoundary(
        store=store,
        registry=registry,
        governance_requirement_resolver=_resolver,
    )


def _assert_blocked(store: Any, request: CapabilityRequest) -> None:
    decision = GovernanceUseAdmission(store).evaluate(request, _resolver)
    assert decision.status == "blocked"
    assert "blocking governance review" in decision.reason


async def test_c1_same_event_loop_can_commit_blocker_before_effect_dispatch() -> None:
    trace: list[str] = []
    store = InMemoryStateStore()
    persistence = InMemoryDistinctionGovernancePersistence(store)
    persistence.seed_state("d", _state())
    provider = _DispatchBarrierProvider("c1", trace)
    request = _request("c1")

    execution = asyncio.create_task(_boundary(store, provider).execute(request))
    await provider.entered.wait()

    # Same event loop: the runtime has entered provider.invoke(), which then
    # suspends before the audited effect-dispatch commitment.
    persistence.open_obligation(_blocker("c1"))
    trace.append("q-committed")
    _assert_blocked(store, request)
    trace.append("q-observed-blocking")

    provider.release.set()
    result = await execution

    assert result.status == "succeeded"
    assert provider.calls == 1
    assert trace.index("q-committed") < trace.index("effect-dispatched")
    assert trace.index("q-observed-blocking") < trace.index("effect-dispatched")


async def test_c2_second_thread_same_store_can_commit_blocker_before_effect_dispatch() -> None:
    trace: list[str] = []
    store = InMemoryStateStore()
    persistence = InMemoryDistinctionGovernancePersistence(store)
    persistence.seed_state("d", _state())
    provider = _DispatchBarrierProvider("c2", trace)
    request = _request("c2")
    committed = threading.Event()
    errors: list[BaseException] = []

    def mutate_from_thread() -> None:
        try:
            if not provider.thread_entered.wait(timeout=5):
                raise TimeoutError("provider did not enter before thread audit timeout")
            persistence.open_obligation(_blocker("c2"))
            trace.append("q-committed")
        except BaseException as exc:  # audit must surface worker failure
            errors.append(exc)
        finally:
            committed.set()

    worker = threading.Thread(target=mutate_from_thread, name="e2b-c2-mutator")
    worker.start()
    execution = asyncio.create_task(_boundary(store, provider).execute(request))

    assert await asyncio.to_thread(committed.wait, 5)
    assert not errors
    _assert_blocked(store, request)
    trace.append("q-observed-blocking")

    provider.release.set()
    result = await execution
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert result.status == "succeeded"
    assert provider.calls == 1
    assert trace.index("q-committed") < trace.index("effect-dispatched")
    assert trace.index("q-observed-blocking") < trace.index("effect-dispatched")


async def test_c3_second_sqlite_connection_can_commit_blocker_before_effect_dispatch(
    tmp_path: Path,
) -> None:
    trace: list[str] = []
    db_path = tmp_path / "e2b-c3.db"
    store_a = SQLiteStateStore(db_path)
    store_b = SQLiteStateStore(db_path)
    try:
        persistence_a = SQLiteDistinctionGovernancePersistence(store_a)
        persistence_b = SQLiteDistinctionGovernancePersistence(store_b)
        persistence_a.seed_state("d", _state())
        provider = _DispatchBarrierProvider("c3", trace)
        request = _request("c3")

        execution = asyncio.create_task(_boundary(store_a, provider).execute(request))
        await provider.entered.wait()

        await asyncio.to_thread(persistence_b.open_obligation, _blocker("c3"))
        trace.append("q-committed")
        _assert_blocked(store_a, request)
        trace.append("q-observed-blocking")

        provider.release.set()
        result = await execution

        assert result.status == "succeeded"
        assert provider.calls == 1
        assert trace.index("q-committed") < trace.index("effect-dispatched")
        assert trace.index("q-observed-blocking") < trace.index("effect-dispatched")
    finally:
        store_b.close()
        store_a.close()


def _wait_for_process_marker(done_path: Path, error_path: Path, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if error_path.exists():
            raise AssertionError(error_path.read_text(encoding="utf-8"))
        if done_path.exists():
            return
        time.sleep(0.01)
    raise TimeoutError("independent process did not commit governance blocker")


async def test_c4_independent_process_same_sqlite_db_can_commit_before_effect_dispatch(
    tmp_path: Path,
) -> None:
    trace: list[str] = []
    db_path = tmp_path / "e2b-c4.db"
    start_path = tmp_path / "c4.start"
    done_path = tmp_path / "c4.done"
    error_path = tmp_path / "c4.error"
    store_a = SQLiteStateStore(db_path)
    process: subprocess.Popen[str] | None = None
    try:
        persistence_a = SQLiteDistinctionGovernancePersistence(store_a)
        persistence_a.seed_state("d", _state())
        provider = _DispatchBarrierProvider("c4", trace)
        request = _request("c4")

        child = r'''
import sys
import time
from pathlib import Path
from portable_runtime.governance.distinction import ReviewObligation
from portable_runtime.governance.persistence import SQLiteDistinctionGovernancePersistence
from portable_runtime.stores.sqlite import SQLiteStateStore

db_path = Path(sys.argv[1])
start_path = Path(sys.argv[2])
done_path = Path(sys.argv[3])
error_path = Path(sys.argv[4])
store = None
try:
    deadline = time.monotonic() + 10
    while not start_path.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("parent did not release C4 process barrier")
        time.sleep(0.01)
    store = SQLiteStateStore(db_path)
    persistence = SQLiteDistinctionGovernancePersistence(store)
    persistence.open_obligation(
        ReviewObligation(
            id="q-c4",
            target="d",
            trigger_ref="event-c4",
            basis_refs=("basis-c4",),
            context="ctx",
            blocking=True,
        )
    )
    done_path.write_text("committed", encoding="utf-8")
except BaseException as exc:
    error_path.write_text(repr(exc), encoding="utf-8")
    raise
finally:
    if store is not None:
        store.close()
'''
        process = subprocess.Popen(  # noqa: S603 - controlled audit child, no user input
            [
                sys.executable,
                "-c",
                child,
                str(db_path),
                str(start_path),
                str(done_path),
                str(error_path),
            ],
            text=True,
        )

        execution = asyncio.create_task(_boundary(store_a, provider).execute(request))
        await provider.entered.wait()
        start_path.write_text("go", encoding="utf-8")
        await asyncio.to_thread(_wait_for_process_marker, done_path, error_path, 10)
        trace.append("q-committed")
        _assert_blocked(store_a, request)
        trace.append("q-observed-blocking")

        provider.release.set()
        result = await execution
        return_code = await asyncio.to_thread(process.wait, 5)

        assert return_code == 0
        assert result.status == "succeeded"
        assert provider.calls == 1
        assert trace.index("q-committed") < trace.index("effect-dispatched")
        assert trace.index("q-observed-blocking") < trace.index("effect-dispatched")
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        store_a.close()
