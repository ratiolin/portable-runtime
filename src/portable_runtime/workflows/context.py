"""Workflow context bridging Runtime and providers (portable, provider-agnostic).

Hardened: idempotent invoke deduplication + Run state-machine with explicit
transition contract. Same (run, capability, params) re-invoked is deduped;
waiting/blocked states are resumable with validated transitions.
V1.1: Step/Checkpoint/Lease + fencing support.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from dataclasses import dataclass, field

from portable_runtime.core.capabilities import CapabilityResult
from portable_runtime.core.models import Checkpoint, Run, Step, Work, utcnow
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.core.router import CapabilityService
from portable_runtime.interfaces.store import StateStore

# ---------------------------------------------------------------------------
# Run state machine — explicit contract, unit-testable
# ---------------------------------------------------------------------------

_RUN_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "cancelled"},
    "running": {"waiting", "blocked", "failed", "succeeded", "cancelled", "interrupted"},
    "waiting": {"running", "failed", "cancelled", "blocked", "succeeded"},
    "blocked": {"running", "failed", "cancelled", "succeeded"},
    "failed": set(),
    "succeeded": set(),
    "cancelled": set(),
    "interrupted": {"running", "failed", "cancelled"},
}

_RUN_TERMINAL = {"failed", "succeeded", "cancelled"}


def is_valid_run_transition(from_status: str, to_status: str) -> bool:
    if from_status == to_status:
        return True
    return to_status in _RUN_ALLOWED_TRANSITIONS.get(from_status, set())


def is_terminal_run_status(status: str) -> bool:
    return status in _RUN_TERMINAL


def validate_run_transition(from_status: str, to_status: str) -> None:
    if not is_valid_run_transition(from_status, to_status):
        raise ValueError(f"invalid Run transition {from_status!r} -> {to_status!r}")


@dataclass(slots=True)
class WorkflowContext:
    work: Work
    run: Run
    store: StateStore
    capabilities: CapabilityService
    registry: ProviderRegistry
    _invocation_cache: dict[str, CapabilityResult] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        with contextlib.suppress(Exception):
            cached_meta = self.run.metadata.get("_invocation_cache_sizes", None)  # noqa: F841
        meta_cache = self.run.metadata.get("_workflow_cache_keys", {}) if isinstance(self.run.metadata, dict) else {}
        _ = meta_cache

    def _cache_key(self, capability: str, instruction: str | None, parameters: dict[str, object]) -> str:
        payload = json.dumps(
            {"cap": capability, "inst": instruction, "params": parameters}, sort_keys=True, default=str
        )
        h = hashlib.sha256(payload.encode()).hexdigest()[:16]
        return f"{capability}:{h}"

    def _lookup_cache(self, key: str) -> CapabilityResult | None:
        return self._invocation_cache.get(key)

    def _store_cache(self, key: str, result: CapabilityResult) -> None:
        self._invocation_cache[key] = result
        with contextlib.suppress(Exception):
            cache_keys = dict(self.run.metadata.get("_workflow_cache_keys", {}))
            cache_keys[key] = result.status
            self.run.metadata["_workflow_cache_keys"] = cache_keys
            self.store.save_run(self.run)

    async def invoke(
        self, capability: str, *, instruction: str | None = None, **parameters: object
    ) -> CapabilityResult:
        key = self._cache_key(capability, instruction, parameters)
        cached = self._lookup_cache(key)
        if cached is not None:
            return cached
        from portable_runtime.core.invocation import InvocationFactory  # type: ignore[import-untyped]
        contract_registry = None
        try:
            b = getattr(self.capabilities, "boundary", None)
            if b is not None and hasattr(b, "contract_registry"):
                contract_registry = b.contract_registry
        except Exception:
            pass
        factory = InvocationFactory(store=self.store, registry=self.registry, contract_registry=contract_registry, runtime_id=getattr(self.capabilities, "runtime_id", "runtime"))
        req = factory.build(
            capability,
            work_id=self.work.id,
            run_id=self.run.id,
            instruction=instruction,
            parameters=dict(parameters),  # type: ignore[arg-type]
            idempotency_key=f"{self.run.id}:{key}",
            step_key=key,
            request_id=f"req_{self.run.id}_{capability}_{len(self._invocation_cache)}",
        )
        result = await self.capabilities.invoke(req)
        self._store_cache(key, result)
        return result

    # --- Step helpers V1.1 ---

    def step(self, step_key: str, kind: str = "generic") -> Step:
        """Get or create durable Step; ensures stable key."""
        try:
            steps = self.store.list_steps(self.run.id)  # type: ignore
            existing = next((s for s in steps if s.step_key == step_key), None)
            if existing:
                return existing
        except Exception:
            pass
        from portable_runtime.core.models import new_id

        s = Step(id=new_id("step"), run_id=self.run.id, step_key=step_key, kind=kind, status="pending")
        try:
            self.store.save_step(s)  # type: ignore
        except Exception:
            pass
        return s

    def checkpoint(self, step_id: str | None = None, payload: dict | None = None) -> Checkpoint:
        from portable_runtime.core.models import new_id

        cp = Checkpoint(
            id=new_id("checkpoint"),
            run_id=self.run.id,
            step_id=step_id,
            payload=payload,
            state_digest=hashlib.sha256(json.dumps(payload or {}, sort_keys=True).encode()).hexdigest()[:16] if payload else None,
        )
        try:
            self.store.save_checkpoint(cp)  # type: ignore
        except Exception:
            pass
        return cp

    # --- Run status helpers ---

    def can_transition(self, to_status: str) -> bool:
        return is_valid_run_transition(self.run.status, to_status)

    def transition_run(self, to_status: str, *, current_step: str | None = None) -> Run:
        validate_run_transition(self.run.status, to_status)
        update: dict[str, object] = {"status": to_status}
        if current_step is not None:
            update["current_step"] = current_step
        if to_status in _RUN_TERMINAL:
            update["ended_at"] = utcnow()
        if self.run.status == "queued" and to_status == "running" and self.run.started_at is None:
            update["started_at"] = utcnow()
        new_run = self.run.model_copy(update=update)
        self.run = new_run
        self.store.save_run(new_run)
        return new_run

    def set_step(self, step: str) -> Run:
        new_run = self.run.model_copy(update={"current_step": step})
        self.run = new_run
        self.store.save_run(new_run)
        return new_run

    def has_completed_step(self, step: str) -> bool:
        keys = self.run.metadata.get("_workflow_cache_keys", {}) if isinstance(self.run.metadata, dict) else {}
        return any(step in k for k in keys) if isinstance(keys, dict) else False

    def is_resumable(self) -> bool:
        return self.run.status in ("waiting", "blocked", "interrupted", "running")

    def resume(self) -> Run:
        if self.run.status in ("waiting", "blocked", "interrupted"):
            return self.transition_run("running")
        return self.run

    def clear_cache(self) -> None:
        self._invocation_cache.clear()
        if isinstance(self.run.metadata, dict) and "_workflow_cache_keys" in self.run.metadata:
            self.run.metadata.pop("_workflow_cache_keys", None)
            self.store.save_run(self.run)
