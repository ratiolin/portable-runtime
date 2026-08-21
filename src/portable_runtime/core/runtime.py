from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from portable_runtime.core.capabilities import CapabilityRequest, CapabilityResult
from portable_runtime.core.models import Run, Step, Work, new_id, utcnow
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.core.router import CapabilityService
from portable_runtime.interfaces.artifact_store import ArtifactStore
from portable_runtime.interfaces.store import StateStore
from portable_runtime.stores.memory import InMemoryStateStore


class Runtime:
    def __init__(
        self,
        *,
        store: StateStore | None = None,
        artifact_store: ArtifactStore | None = None,
        registry: ProviderRegistry | None = None,
        runtime_id: str = "runtime",
        policy_engine: Any | None = None,
        contract_registry: Any | None = None,
        reliability: Any | None = None,
    ) -> None:
        from portable_runtime.core.boundary import RealityBoundary
        from portable_runtime.core.capability_contract import CapabilityContractRegistry
        from portable_runtime.core.router import ConstraintRouter
        self.runtime_id = runtime_id
        self.store = store or InMemoryStateStore()
        self.artifact_store = artifact_store
        self.registry = registry or ProviderRegistry()
        self.contract_registry = contract_registry or CapabilityContractRegistry()
        self.routing = ConstraintRouter()
        self.policy_engine = policy_engine
        self.boundary = RealityBoundary(
            store=self.store,
            registry=self.registry,
            routing=self.routing,
            policy_engine=self.policy_engine,
            reliability=reliability,
            runtime_id=self.runtime_id,
            contract_registry=self.contract_registry,  # type: ignore[call-arg]
        )
        self.capabilities = CapabilityService(boundary=self.boundary)

    def create_work(self, *, title: str, description: str = "", kind: str = "generic-task", **fields: Any) -> Work:
        work = Work(id=new_id("work"), title=title, description=description, kind=kind, **fields)
        self.store.save_work(work)
        with contextlib.suppress(Exception):
            from portable_runtime.core import metrics as _metrics
            _metrics.inc_work(kind=work.kind, status=work.status)
            _metrics.inc_event("work_created")
        return work

    def get_work(self, work_id: str) -> Work | None:
        return self.store.get_work(work_id)

    def list_work(self, status: str | None = None) -> list[Work]:
        return self.store.list_work(status)

    def start_run(self, work_id: str, workflow_id: str = "generic-task") -> Run:
        work = self.store.get_work(work_id)
        if work is None:
            raise KeyError(f"unknown work: {work_id}")
        now = utcnow()
        run = Run(
            id=new_id("run"),
            work_id=work_id,
            workflow_id=workflow_id,
            status="running",
            started_at=now,
        )
        self.store.save_run(run)
        self.store.save_work(work.model_copy(update={"status": "running", "updated_at": now}))
        with contextlib.suppress(Exception):
            from portable_runtime.core import metrics as _metrics
            _metrics.inc_run(workflow_id=workflow_id, status="running")
            _metrics.inc_event("run_started")
        return run

    async def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        result = await self.capabilities.invoke(request)
        with contextlib.suppress(Exception):
            from portable_runtime.core import metrics as _metrics
            _metrics.inc_provider_invocation(result.provider_id or "none", request.capability, result.status)
        return result

    async def run_capability(
        self,
        work_id: str,
        capability: str,
        *,
        instruction: str | None = None,
        run_id: str | None = None,
        actor_ref: str | None = None,
        resource_ref: str | None = None,
        subject_version_refs: list[str] | None = None,
        **parameters: Any,
    ) -> CapabilityResult:
        from portable_runtime.core.invocation import InvocationFactory
        run = self.store.get_run(run_id) if run_id else None
        if run is None:
            run = self.start_run(work_id)
        factory = InvocationFactory(store=self.store, registry=self.registry, contract_registry=self.contract_registry, runtime_id=self.runtime_id)
        request = factory.build(
            capability,
            work_id=work_id,
            run_id=run.id,
            instruction=instruction,
            parameters=parameters,
            actor_ref=actor_ref,
            resource_ref=resource_ref,
            subject_version_refs=subject_version_refs,
        )
        run = run.model_copy(update={"provider_invocation_refs": [*run.provider_invocation_refs, request.id]})
        self.store.save_run(run)
        return await self.invoke(request)

    def export_state(self) -> dict[str, list[dict[str, object]]]:
        return self.store.export_state()

    def import_state(self, state: dict[str, list[dict[str, object]]]) -> None:
        self.store.import_state(state)

    def export_bundle(self, bundle_path: Path) -> Path:
        from portable_runtime.stores.bundle import export_bundle
        return export_bundle(self.store, self.artifact_store, bundle_path, runtime_id=self.runtime_id)

    def import_bundle(self, bundle_path: Path) -> dict[str, Any]:
        from portable_runtime.stores.bundle import import_bundle
        return import_bundle(self.store, self.artifact_store, bundle_path)

    async def health(self) -> dict[str, Any]:
        providers = []
        for descriptor in self.registry.list():
            health = await self.registry.health(descriptor.id)
            providers.append(health.model_dump(mode="json"))
            with contextlib.suppress(Exception):
                from portable_runtime.core import metrics as _metrics
                _metrics.set_provider_health(descriptor.id, health.available)
        return {"runtime_id": self.runtime_id, "providers": providers}

    def metrics_snapshot(self) -> dict[str, Any]:
        from portable_runtime.core.metrics import metrics_snapshot
        return metrics_snapshot(self.store)

    def resume(self, run_id: str) -> Run:
        run = self.store.get_run(run_id)
        if run is None:
            raise KeyError(f"unknown run: {run_id}")
        if run.status in ("waiting", "blocked", "interrupted"):
            run = run.model_copy(update={"status": "running"})
            self.store.save_run(run)
        return run

    def recover(self, before_seconds: float = 30) -> list[Step]:
        try:
            return self.store.list_stale_steps(before_seconds)  # type: ignore[attr-defined]
        except Exception:
            return []

    async def reconcile(self, step_id: str) -> CapabilityResult | None:
        try:
            step = self.store.get_step(step_id)  # type: ignore[attr-defined]
        except Exception:
            return None
        if not step:
            return None
        attempts = []
        try:
            attempts = self.store.list_attempts(step_id)  # type: ignore[attr-defined]
        except Exception:
            pass
        if not attempts:
            return None
        last = sorted(attempts, key=lambda a: a.attempt_no)[-1]
        if not last.request_ref or not last.provider_id:
            return None
        result = await self.capabilities.reconcile(last.request_ref, last.provider_id)
        if result:
            if result.status == "unknown":
                step.status = "unknown"
                self.store.save_step(step)  # type: ignore
            return result
        if step.effect_semantics in ("irreversible-opaque", "reconcilable"):
            step.status = "unknown"
            self.store.save_step(step)  # type: ignore
            return CapabilityResult(request_id=last.request_ref, provider_id=last.provider_id, status="unknown", message="reconcile failed, marked unknown")
        return None

    def interrupt(self, run_id: str) -> Run:
        run = self.store.get_run(run_id)
        if run is None:
            raise KeyError(f"unknown run: {run_id}")
        run = run.model_copy(update={"status": "interrupted"})
        self.store.save_run(run)
        return run

    def cancel(self, run_id: str) -> Run:
        run = self.store.get_run(run_id)
        if run is None:
            raise KeyError(f"unknown run: {run_id}")
        run = run.model_copy(update={"status": "cancelled", "ended_at": utcnow()})
        self.store.save_run(run)
        return run

    def acquire_lease(self, run_id: str, owner: str, ttl_seconds: float = 30) -> bool:
        previous_owner = None
        try:
            current = self.store.get_run(run_id)
            previous_owner = getattr(current, "lease_owner", None) if current is not None else None
        except Exception:
            previous_owner = None
        try:
            acquired = self.store.acquire_lease(run_id, owner, ttl_seconds)  # type: ignore
        except Exception:
            return False
        try:
            from portable_runtime.core.models import Event, new_id
            event_type = "LeaseTakenOver" if acquired and previous_owner not in (None, owner) else "LeaseAcquired"
            if not acquired:
                event_type = "FencingRejected"
            self.store.append_event(Event(id=new_id("event"), type=event_type, subject_ref=run_id, payload={"owner": owner, "previous_owner": previous_owner, "acquired": acquired}))  # type: ignore[attr-defined]
        except Exception:
            # Lease state remains authoritative; journal availability is
            # surfaced by boundary transitions and conformance evidence.
            pass
        return acquired

    def renew_lease(self, run_id: str, owner: str, ttl_seconds: float = 30) -> bool:
        try:
            renewed = self.store.renew_lease(run_id, owner, ttl_seconds)  # type: ignore
        except Exception:
            return False
        try:
            from portable_runtime.core.models import Event, new_id
            self.store.append_event(Event(id=new_id("event"), type="LeaseRenewed" if renewed else "FencingRejected", subject_ref=run_id, payload={"owner": owner, "renewed": renewed}))  # type: ignore[attr-defined]
        except Exception:
            pass
        return renewed

    def release_lease(self, run_id: str, owner: str) -> bool:
        try:
            released = self.store.release_lease(run_id, owner)  # type: ignore
        except Exception:
            return False
        try:
            from portable_runtime.core.models import Event, new_id
            self.store.append_event(Event(id=new_id("event"), type="LeaseReleased" if released else "FencingRejected", subject_ref=run_id, payload={"owner": owner, "released": released}))  # type: ignore[attr-defined]
        except Exception:
            pass
        return released
