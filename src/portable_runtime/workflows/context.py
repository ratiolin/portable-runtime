"""Workflow context bridging Runtime and providers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from portable_runtime.core.capabilities import CapabilityResult
from portable_runtime.core.models import Checkpoint, Run, Step, Work, utcnow
from portable_runtime.core.registry import ProviderRegistry
from portable_runtime.core.router import CapabilityService
from portable_runtime.interfaces.store import StateStore

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

    def _cache_key(
        self,
        capability: str,
        instruction: str | None,
        parameters: dict[str, object],
    ) -> str:
        payload = json.dumps(
            {"cap": capability, "inst": instruction, "params": parameters},
            sort_keys=True,
            default=str,
        )
        return f"{capability}:{hashlib.sha256(payload.encode()).hexdigest()[:16]}"

    def _lookup_cache(self, key: str) -> CapabilityResult | None:
        return self._invocation_cache.get(key)

    def _store_cache(self, key: str, result: CapabilityResult) -> None:
        self._invocation_cache[key] = result
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

        from portable_runtime.core.invocation import InvocationFactory

        boundary = getattr(self.capabilities, "boundary", None)
        contract_registry = getattr(boundary, "contract_registry", None)
        factory = InvocationFactory(
            store=self.store,
            registry=self.registry,
            contract_registry=contract_registry,
            runtime_id=getattr(self.capabilities, "runtime_id", "runtime"),
        )
        governance_keys = {
            "actor_ref",
            "resource_ref",
            "resource_scope",
            "subject_version_refs",
            "subject_refs",
            "procedure_profile",
            "procedure_required",
            "procedure_applicability",
            "procedure_proofs",
            "obligation_proofs",
            "policy_obligations",
            "obligations",
            "independence_constraints",
            "reference_descriptors",
            "lease_owner",
            "lease_generation",
            "authorization_grant_id",
            "required_gates",
        }
        governance_metadata: dict[str, object] = {}
        for source in (self.work.metadata, self.run.metadata):
            governance_metadata.update(
                {key: source[key] for key in governance_keys if key in source}
            )
        subject_versions = governance_metadata.get("subject_version_refs")
        if isinstance(subject_versions, str):
            subject_versions = [subject_versions]
        elif not isinstance(subject_versions, list):
            subject_versions = None
        request = factory.build(
            capability,
            work_id=self.work.id,
            run_id=self.run.id,
            instruction=instruction,
            parameters=dict(parameters),
            idempotency_key=f"{self.run.id}:{key}",
            step_key=key,
            request_id=f"req_{self.run.id}_{capability}_{len(self._invocation_cache)}",
            metadata=governance_metadata,
            actor_ref=governance_metadata.get("actor_ref"),
            resource_ref=governance_metadata.get("resource_ref"),
            subject_version_refs=subject_versions,
        )
        result = await self.capabilities.invoke(request)
        self._store_cache(key, result)
        return result

    def step(self, step_key: str, kind: str = "generic") -> Step:
        """Get or create a durable Step with a stable key."""
        existing = next(
            (step for step in self.store.list_steps(self.run.id) if step.step_key == step_key),
            None,
        )
        if existing is not None:
            return existing

        from portable_runtime.core.models import new_id

        step = Step(
            id=new_id("step"),
            run_id=self.run.id,
            step_key=step_key,
            kind=kind,
            status="pending",
        )
        self.store.save_step(step)
        return step

    def checkpoint(
        self, step_id: str | None = None, payload: dict | None = None
    ) -> Checkpoint:
        from portable_runtime.core.models import new_id

        checkpoint = Checkpoint(
            id=new_id("checkpoint"),
            run_id=self.run.id,
            step_id=step_id,
            payload=payload,
            state_digest=(
                hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
                if payload
                else None
            ),
        )
        self.store.save_checkpoint(checkpoint)
        return checkpoint

    def can_transition(self, to_status: str) -> bool:
        return is_valid_run_transition(self.run.status, to_status)

    def transition_run(self, to_status: str, *, current_step: str | None = None) -> Run:
        if to_status == "succeeded":
            raise ValueError("terminal succeeded transition requires complete_with_proofs()")
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

    def complete_with_proofs(self, verification_refs: list[str]) -> Run:
        """Authorize ``succeeded`` using the shared completion primitive."""
        from portable_runtime.workflows.completion import CompletionAuthority

        self.run = CompletionAuthority(self.store).authorize(
            work=self.work,
            run=self.run,
            verification_refs=verification_refs,
        )
        self.work = self.store.get_work(self.work.id) or self.work
        return self.run

    def set_step(self, step: str) -> Run:
        new_run = self.run.model_copy(update={"current_step": step})
        self.run = new_run
        self.store.save_run(new_run)
        return new_run

    def has_completed_step(self, step: str) -> bool:
        keys = self.run.metadata.get("_workflow_cache_keys", {})
        return any(step in key for key in keys) if isinstance(keys, dict) else False

    def is_resumable(self) -> bool:
        return self.run.status in ("waiting", "blocked", "interrupted", "running")

    def resume(self) -> Run:
        if self.run.status in ("waiting", "blocked", "interrupted"):
            return self.transition_run("running")
        return self.run

    def clear_cache(self) -> None:
        self._invocation_cache.clear()
        if "_workflow_cache_keys" in self.run.metadata:
            self.run.metadata.pop("_workflow_cache_keys")
            self.store.save_run(self.run)
