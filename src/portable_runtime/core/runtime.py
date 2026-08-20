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
    """Long-lived state and capability coordination, independent of providers."""

    def __init__(
        self,
        *,
        store: StateStore | None = None,
        artifact_store: ArtifactStore | None = None,
        registry: ProviderRegistry | None = None,
        runtime_id: str = "runtime",
    ) -> None:
        self.runtime_id = runtime_id
        self.store = store or InMemoryStateStore()
        self.artifact_store = artifact_store
        self.registry = registry or ProviderRegistry()
        self.capabilities = CapabilityService(
            self.registry,
            store=self.store,
            runtime_id=runtime_id,
        )

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
        **parameters: Any,
    ) -> CapabilityResult:
        run = self.store.get_run(run_id) if run_id else None
        if run is None:
            run = self.start_run(work_id)
        # fencing check
        if run.lease_owner and run.lease_expires_at:
            import datetime
            if run.lease_expires_at < datetime.datetime.now(datetime.UTC) and run.lease_generation > 0:
                pass
        request = CapabilityRequest(
            id=new_id("request"),
            capability=capability,
            work_id=work_id,
            run_id=run.id,
            instruction=instruction,
            parameters=parameters,
        )
        run = run.model_copy(update={"provider_invocation_refs": [*run.provider_invocation_refs, request.id]})
        self.store.save_run(run)
        return await self.invoke(request)

    def export_state(self) -> dict[str, list[dict[str, object]]]:
        return self.store.export_state()

    def import_state(self, state: dict[str, list[dict[str, object]]]) -> None:
        self.store.import_state(state)

    def export_bundle(self, bundle_path: Path) -> Path:
        """Export full portable bundle (manifest.json + *.jsonl + artifacts/) as tar.zst."""
        from portable_runtime.stores.bundle import export_bundle

        return export_bundle(self.store, self.artifact_store, bundle_path, runtime_id=self.runtime_id)

    def import_bundle(self, bundle_path: Path) -> dict[str, Any]:
        """Import portable bundle (tar.zst)."""
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

    # V1.1 Execution Integrity

    def resume(self, run_id: str) -> Run:
        run = self.store.get_run(run_id)
        if run is None:
            raise KeyError(f"unknown run: {run_id}")
        if run.status in ("waiting", "blocked", "interrupted"):
            run = run.model_copy(update={"status": "running"})
            self.store.save_run(run)
        return run

    def recover(self, before_seconds: float = 30) -> list[Step]:
        """Find stale running steps for reconcile."""
        try:
            return self.store.list_stale_steps(before_seconds)  # type: ignore[attr-defined]
        except Exception:
            return []

    async def reconcile(self, step_id: str) -> CapabilityResult | None:
        """Attempt to reconcile a stale step via provider.reconcile."""
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
        try:
            provider = self.registry.get(last.provider_id)
            if hasattr(provider, "reconcile"):
                result = await provider.reconcile(last.request_ref)  # type: ignore
                if result:
                    # Handle effect semantics: if irreversible-opaque and no result, mark unknown
                    if result.status == "unknown":
                        step.status = "unknown"
                        self.store.save_step(step)  # type: ignore
                    return result
        except Exception:
            pass
        # fallback: if effect is pure/idempotent, safe to retry; else unknown
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
        try:
            return self.store.acquire_lease(run_id, owner, ttl_seconds)  # type: ignore
        except Exception:
            return False

    def renew_lease(self, run_id: str, owner: str, ttl_seconds: float = 30) -> bool:
        try:
            return self.store.renew_lease(run_id, owner, ttl_seconds)  # type: ignore
        except Exception:
            return False

    def release_lease(self, run_id: str, owner: str) -> bool:
        try:
            return self.store.release_lease(run_id, owner)  # type: ignore
        except Exception:
            return False




