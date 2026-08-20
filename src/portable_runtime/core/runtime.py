from __future__ import annotations

from pathlib import Path
from typing import Any

from portable_runtime.core.capabilities import CapabilityRequest, CapabilityResult
from portable_runtime.core.models import Run, Work, new_id, utcnow
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
        return run

    async def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        return await self.capabilities.invoke(request)

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
        return {"runtime_id": self.runtime_id, "providers": providers}
